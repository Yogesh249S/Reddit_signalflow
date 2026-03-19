#!/usr/bin/env python3
"""
SignalFlow Dashboard Performance Monitor
Runs inside Docker on the signalflow_prod network.
nano monitor.py
# POLL_INTERVAL_SECONDS = 30  →  POLL_INTERVAL_SECONDS = 10
Measures every 30s:
  1. Postgres  — direct query timing on your actual schema
  2. Redis     — scans DB1 for live cache keys + hit/miss timing
  3. Django    — cold vs warm to measure cache effectiveness
  4. Grafana   — dashboard HTTP response time

Stop with Ctrl+C — prints avg + p95 summary.
"""

import time
import json
import statistics
from datetime import datetime, timezone

import psycopg2
import redis
import requests
from requests.packages.urllib3.exceptions import InsecureRequestWarning
requests.packages.urllib3.disable_warnings(InsecureRequestWarning)

# ─────────────────────────────────────────────────────────────
# CONFIG — all hostnames are Docker service names
# ─────────────────────────────────────────────────────────────

PG_CONFIG = {
    "host":     "postgres",
    "port":     5432,
    "dbname":   "reddit",
    "user":     "reddit",
    "password": "reddit",
}

REDIS_CONFIG = {
    "host":     "redis",
    "port":     6379,
    "db":       1,       # DB1 = Django API response cache
    "password": None,
}

DJANGO_ENDPOINTS = [
    {"name": "trending", "url": "http://django:8000/api/v1/trending/"},
    {"name": "pulse",    "url": "http://django:8000/api/v1/pulse/"},
    {"name": "compare",  "url": "http://django:8000/api/v1/compare/"},
]

GRAFANA_PANELS = [
    {
        "name": "Multi-Platform",
        "url":  "http://grafana:3000/render/d/signalflow-platforms?width=1000&height=500&from=now-15m&to=now",
    },
    {
        "name": "Topic Intelligence",
        "url":  "http://grafana:3000/render/d/signalflow-topics?width=1000&height=500&from=now-1h&to=now",
    },
]
GRAFANA_AUTH = ("admin", "admin")

# Queries corrected to match your actual schema
PG_QUERIES = [
    {
        # Full table scan on 1M+ rows — likely your slowest
        "name": "signal_count_total",
        "sql":  "SELECT COUNT(*) FROM signals",
    },
    {
        # topic_timeseries: bucket (time col), max_trending, total_score, signal_count
        "name": "trending_topics_24h",
        "sql":  """
            SELECT topic, platform,
                   MAX(max_trending)   AS peak_trending,
                   SUM(signal_count)   AS total_signals
            FROM topic_timeseries
            WHERE bucket >= NOW() - INTERVAL '24 hours'
            GROUP BY topic, platform
            ORDER BY peak_trending DESC
            LIMIT 20
        """,
    },
    {
        # topic_timeseries last 2h — what Grafana top-topics panel runs
        "name": "top_topics_by_platform_2h",
        "sql":  """
            SELECT platform, topic,
                   SUM(total_score)  AS score,
                   SUM(signal_count) AS cnt
            FROM topic_timeseries
            WHERE bucket >= NOW() - INTERVAL '2 hours'
            GROUP BY platform, topic
            ORDER BY score DESC
            LIMIT 40
        """,
    },
    {
        # cross_platform_events: detected_at, avg_sentiment, peak_signal_count
        "name": "cross_platform_events_2h",
        "sql":  """
            SELECT topic, platforms, avg_sentiment, peak_signal_count, detected_at
            FROM cross_platform_events
            WHERE detected_at >= NOW() - INTERVAL '2 hours'
            ORDER BY peak_signal_count DESC
            LIMIT 20
        """,
    },
    {
        # signals table — last_updated_at is the recency column
        "name": "signals_last_15min",
        "sql":  """
            SELECT platform, COUNT(*) AS cnt
            FROM signals
            WHERE last_updated_at >= NOW() - INTERVAL '15 minutes'
            GROUP BY platform
        """,
    },
    {
        # signal_metrics_history is the TimescaleDB hypertable
        "name": "metrics_history_1h",
        "sql":  """
            SELECT signal_id, score_velocity, trending_score, captured_at
            FROM signal_metrics_history
            WHERE captured_at >= NOW() - INTERVAL '1 hour'
            ORDER BY trending_score DESC
            LIMIT 20
        """,
    },
]

POLL_INTERVAL_SECONDS = 10
LOG_FILE = "/tmp/perf_log.jsonl"   # /tmp always writable inside container

# ─────────────────────────────────────────────────────────────
# MEASUREMENT FUNCTIONS
# ─────────────────────────────────────────────────────────────

def measure_postgres(pg_conn):
    results = []
    cur = pg_conn.cursor()
    for q in PG_QUERIES:
        t0 = time.perf_counter()
        try:
            cur.execute(q["sql"])
            cur.fetchall()
            ms = round((time.perf_counter() - t0) * 1000, 2)
            results.append({"query": q["name"], "ms": ms, "error": None})
        except Exception as e:
            pg_conn.rollback()
            results.append({"query": q["name"], "ms": None, "error": str(e)})
    cur.close()
    return results


def measure_redis(redis_client):
    all_keys = [k.decode() for k in redis_client.scan_iter("signalflow:1:trending:*", count=20)][:5] + \
           [k.decode() for k in redis_client.scan_iter("signalflow:1:pulse:*", count=20)][:5] + \
           [k.decode() for k in redis_client.scan_iter("signalflow:1:stats:*", count=20)][:3]
    db_size  = redis_client.dbsize()

    # only GET string keys — Channels uses sets/hashes, GET fails on those
    string_keys = [k for k in all_keys if redis_client.type(k) == b"string"]

    results = []
    for key in string_keys[:5]:
        t0  = time.perf_counter()
        val = redis_client.get(key)
        ms  = round((time.perf_counter() - t0) * 1000, 2)
        if val is not None:
            results.append({"key": key[-50:], "status": "HIT",  "ms": ms,   "bytes": len(val)})
        else:
            results.append({"key": key[-50:], "status": "MISS", "ms": None, "bytes": 0})

    non_string = len(all_keys) - len(string_keys)
    return results, db_size, string_keys, non_string


def measure_django(session):
    """
    Two requests back to back per endpoint.
    Cold = first hit (Postgres if cache cold).
    Warm = second hit (should be Redis if cache is working).
    Negative gain = cache NOT working — warm is slower than cold.    """
    results = []
    for ep in DJANGO_ENDPOINTS:
        timings = []
        for i in range(2):
            t0 = time.perf_counter()
            try:
                r  = session.get(ep["url"], timeout=20, verify=False)
                ms = round((time.perf_counter() - t0) * 1000, 2)
                timings.append({"ms": ms, "status": r.status_code})
            except Exception as e:
                timings.append({"ms": None, "error": str(e)})
            time.sleep(0.1)

        cold = timings[0].get("ms")
        warm = timings[1].get("ms")
        gain = round(cold - warm, 2) if cold and warm else None
        results.append({
            "endpoint":      ep["name"],
            "cold_ms":       cold,
            "warm_ms":       warm,
            "cache_gain_ms": gain,
        })
    return results


def measure_grafana(session):
    results = []
    for panel in GRAFANA_PANELS:
        t0 = time.perf_counter()
        try:
            r  = session.get(panel["url"], auth=GRAFANA_AUTH, timeout=30, verify=False)
            ms = round((time.perf_counter() - t0) * 1000, 2)
            results.append({"panel": panel["name"], "ms": ms, "status": r.status_code, "error": None})
        except Exception as e:
            results.append({"panel": panel["name"], "ms": None, "error": str(e)})
    return results


# ─────────────────────────────────────────────────────────────
# DISPLAY
# ─────────────────────────────────────────────────────────────

def c(ms, warn=500, crit=2000):
    if ms is None:
        return "\033[90m     N/A\033[0m"
    if ms < warn:
        return f"\033[92m{ms:8.1f}ms\033[0m"
    if ms < crit:
        return f"\033[93m{ms:8.1f}ms\033[0m"
    return     f"\033[91m{ms:8.1f}ms\033[0m"

#def print_cycle(ts, pg, redis_res, db_size, all_keys, django, grafana):
def print_cycle(ts, pg, redis_res, db_size, all_keys, non_string, django, grafana):    
    print(f"\n{'─'*68}")
    print(f"  {ts}   Redis DB1 keys: {db_size}")
    print(f"{'─'*68}")

    print("\n  POSTGRES QUERIES")
    for r in pg:
        err = f"\n      \033[91m↳ {r['error'][:80]}\033[0m" if r["error"] else ""
        print(f"    {r['query']:<38} {c(r['ms'])}{err}")

    #print(f"\n  REDIS CACHE  (DB1 — {db_size} keys total)")
    print(f"\n  REDIS CACHE  (DB1 — {db_size} API cache keys)")
    if not redis_res:
        print("    \033[90m  no keys in DB1 yet — hit an API endpoint first\033[0m")
    for r in redis_res:
        hit = "\033[92m HIT \033[0m" if r["status"] == "HIT" else "\033[91mMISS\033[0m"
        ms  = c(r["ms"]) if r["ms"] else "          "
        sz  = f"  {r['bytes']}b" if r["bytes"] else ""
        print(f"    {hit}  ...{r['key']:<52} {ms}{sz}")
    if all_keys and not redis_res:
        print(f"    \033[90msample: {all_keys[0]}\033[0m")

    print("\n  DJANGO API  (cold → warm)")
    for r in django:
        gain = r["cache_gain_ms"]
        if gain and gain > 50:
            g_str = f"  \033[92m✓ cache saving {gain:.0f}ms\033[0m"
        elif gain and gain > 0:
            g_str = f"  \033[93m~ marginal {gain:.0f}ms\033[0m"
        elif gain and gain <= 0:
            g_str = f"  \033[91m✗ cache not helping ({gain}ms)\033[0m"
        else:
            g_str = ""
        print(f"    {r['endpoint']:<12} cold:{c(r['cold_ms'])}  warm:{c(r['warm_ms'])}{g_str}")

    print("\n  GRAFANA PANELS")
    for r in grafana:
        err = f"  \033[91m{r['error']}\033[0m" if r["error"] else ""
        print(f"    {r['panel']:<38} {c(r['ms'], warn=1000, crit=5000)}{err}")
    print()


# ─────────────────────────────────────────────────────────────
# SUMMARY
# ─────────────────────────────────────────────────────────────

history = {"pg": {}, "django": {}, "grafana": {}}

def record(pg, django, grafana):
    for r in pg:
        if r["ms"]:
            history["pg"].setdefault(r["query"], []).append(r["ms"])
    for r in django:
        if r["cold_ms"]: history["django"].setdefault(r["endpoint"]+"_cold", []).append(r["cold_ms"])
        if r["warm_ms"]: history["django"].setdefault(r["endpoint"]+"_warm", []).append(r["warm_ms"])
    for r in grafana:
        if r["ms"]:      history["grafana"].setdefault(r["panel"], []).append(r["ms"])

def print_summary():
    print(f"\n{'═'*68}")
    print("  SUMMARY — all cycles")
    print(f"{'═'*68}")
    for section, data in history.items():
        if not data:
            continue
        print(f"\n  {section.upper()}")
        for name, times in data.items():
            avg = statistics.mean(times)
            p95 = sorted(times)[max(0, int(len(times)*0.95)-1)]
            print(f"    {name:<42}  avg:{avg:7.1f}ms  p95:{p95:7.1f}ms  min:{min(times):7.1f}  max:{max(times):7.1f}  n={len(times)}")
    print()


# ─────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────

def main():
    print("SignalFlow Performance Monitor")
    print(f"Polling every {POLL_INTERVAL_SECONDS}s  |  log → {LOG_FILE}")
    print("Ctrl+C to stop and see summary\n")

    pg_conn      = psycopg2.connect(**PG_CONFIG)
    pg_conn.autocommit = True
    redis_client = redis.Redis(**REDIS_CONFIG, decode_responses=False)
    session      = requests.Session()

    try:
        while True:
            ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

            pg_res                          = measure_postgres(pg_conn)
            redis_res, db_size, all_keys, non_string = measure_redis(redis_client)
            django_res                      = measure_django(session)
            grafana_res                     = measure_grafana(session)

            
	    #print_cycle(ts, pg_res, redis_res, db_size, all_keys, django_res, grafana_res)
            print_cycle(ts, pg_res, redis_res, db_size, all_keys, non_string, django_res, grafana_res)
            record(pg_res, django_res, grafana_res)

            with open(LOG_FILE, "a") as f:
                f.write(json.dumps({
                    "ts":      ts,
                    "pg":      pg_res,
                    "redis":   redis_res,
                    "django":  django_res,
                    "grafana": grafana_res,
                }) + "\n")

            time.sleep(POLL_INTERVAL_SECONDS)

    except KeyboardInterrupt:
        print_summary()
        pg_conn.close()
        print("Monitor stopped.")

if __name__ == "__main__":
    main()
