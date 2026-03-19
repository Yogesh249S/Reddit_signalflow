"""
topic_summariser.py
-------------------
Async job that runs every 15 minutes.
Reads top trending topics from the DB, calls an LLM to generate:
  - summary_text:             3-sentence narrative of what's being discussed
  - divergence_explanation:   1-sentence explanation of why platforms diverge
Writes results to topic_summaries table.

Provider is controlled by LLM_PROVIDER env var:
  openai    → gpt-4o-mini      (~$0.015/hr at current volume)
  anthropic → claude-haiku-3-5 (comparable cost)
  groq      → llama-3.1-8b     (free tier, slower)

Architecture: sits OUTSIDE the hot path.
  Kafka → processing → signals table  (unchanged, no latency impact)
  topic_summariser job reads signals table every 15 min → writes topic_summaries

Run as a separate Docker service:
  docker compose -f docker-compose.hetzner.yml up -d topic-summariser
"""

import os
import json
import time
import logging
import asyncio
import httpx
import psycopg2
import psycopg2.extras
from datetime import datetime, timezone
from typing import Optional

# ── CONFIG ────────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [summariser] %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

PG = dict(
    host=os.getenv("POSTGRES_HOST", "postgres"),
    dbname=os.getenv("POSTGRES_DB", "reddit"),
    user=os.getenv("POSTGRES_USER", "reddit"),
    password=os.getenv("POSTGRES_PASSWORD", "reddit"),
    port=int(os.getenv("POSTGRES_PORT", 5432)),
)

#LLM_PROVIDER   = os.getenv("LLM_PROVIDER", "openai")          # openai | anthropic | groq
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "groq")
import itertools

OPENAI_KEY    = os.getenv("OPENAI_API_KEY", "")
ANTHROPIC_KEY = os.getenv("ANTHROPIC_API_KEY", "")

# ── Groq key pool — round-robin across multiple keys to multiply rate limit ──
# Add keys as GROQ_API_KEY_1, GROQ_API_KEY_2, GROQ_API_KEY_3 in .env
# Falls back to GROQ_API_KEY if no numbered keys found.
# Each free key = 30 req/min — 3 keys = 90 req/min combined.
def _load_groq_keys() -> list:
    keys = []
    i = 1
    while True:
        k = os.getenv(f"GROQ_API_KEY_{i}", "")
        if not k:
            break
        keys.append(k)
        i += 1
    if not keys:
        k = os.getenv("GROQ_API_KEY", "")
        if k:
            keys.append(k)
    return keys

GROQ_KEYS = _load_groq_keys()
_groq_key_cycle = itertools.cycle(GROQ_KEYS) if GROQ_KEYS else iter([])
GROQ_KEY  = GROQ_KEYS[0] if GROQ_KEYS else ""  # kept for validation check

POLL_INTERVAL  = int(os.getenv("SUMMARISER_INTERVAL_SECONDS", 900))   # 15 min
WINDOW_MINUTES = int(os.getenv("SUMMARISER_WINDOW_MINUTES", 60))
MIN_SIGNALS    = int(os.getenv("SUMMARISER_MIN_SIGNALS", 10))          # skip tiny topics
TOP_SIGNALS    = int(os.getenv("SUMMARISER_TOP_SIGNALS", 25))          # signals sent to LLM
MAX_TOPICS     = int(os.getenv("SUMMARISER_MAX_TOPICS", 50))           # topics per run
SUMMARY_TTL    = int(os.getenv("SUMMARISER_TTL_MINUTES", 30))          # skip if fresh


# ── DB SCHEMA ─────────────────────────────────────────────────────────────────

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS topic_summaries (
    id                      BIGSERIAL PRIMARY KEY,
    topic                   TEXT NOT NULL,
    window_minutes          INTEGER NOT NULL DEFAULT 60,
    generated_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- narrative fields
    summary_text            TEXT,           -- 3-sentence summary of discourse
    divergence_explanation  TEXT,           -- why platforms disagree (null if no divergence)
    dominant_narrative      TEXT,           -- 1 phrase: what most people are saying
    emerging_angle          TEXT,           -- 1 phrase: minority view / counter-narrative

    -- metadata
    signal_count            INTEGER,
    platform_count          INTEGER,
    platforms               JSONB,
    avg_sentiment           FLOAT,
    model_used              TEXT,
    prompt_tokens           INTEGER,
    completion_tokens       INTEGER,
    latency_ms              INTEGER,

    UNIQUE (topic, window_minutes)
);

CREATE INDEX IF NOT EXISTS idx_topic_summaries_topic_generated
    ON topic_summaries (topic, generated_at DESC);

CREATE INDEX IF NOT EXISTS idx_topic_summaries_generated
    ON topic_summaries (generated_at DESC);
"""


# ── LLM CLIENTS ───────────────────────────────────────────────────────────────

async def call_openai(prompt: str, client: httpx.AsyncClient) -> tuple[str, int, int]:
    """Returns (response_text, prompt_tokens, completion_tokens)"""
    resp = await client.post(
        "https://api.openai.com/v1/chat/completions",
        headers={"Authorization": f"Bearer {OPENAI_KEY}"},
        json={
            "model": "gpt-4o-mini",
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 300,
            "temperature": 0.3,
        },
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    text = data["choices"][0]["message"]["content"].strip()
    usage = data.get("usage", {})
    return text, usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0)


async def call_anthropic(prompt: str, client: httpx.AsyncClient) -> tuple[str, int, int]:
    resp = await client.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": ANTHROPIC_KEY,
            "anthropic-version": "2023-06-01",
        },
        json={
            "model": "claude-haiku-4-5-20251001",
            "max_tokens": 300,
            "messages": [{"role": "user", "content": prompt}],
        },
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    text = data["content"][0]["text"].strip()
    usage = data.get("usage", {})
    return text, usage.get("input_tokens", 0), usage.get("output_tokens", 0)


async def call_groq(
    prompt: str,
    client: httpx.AsyncClient,
    api_key: str = "",
) -> tuple[str, int, int]:
    key = api_key or (GROQ_KEYS[0] if GROQ_KEYS else "")
    resp = await client.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={"Authorization": f"Bearer {key}"},
        json={
            "model": "llama-3.1-8b-instant",
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 300,
            "temperature": 0.3,
        },
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    text = data["choices"][0]["message"]["content"].strip()
    usage = data.get("usage", {})
    return text, usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0)


async def call_llm(
    prompt: str,
    client: httpx.AsyncClient,
    api_key: str = "",
) -> tuple[str, int, int]:
    if LLM_PROVIDER == "anthropic":
        return await call_anthropic(prompt, client)
    elif LLM_PROVIDER == "groq":
        return await call_groq(prompt, client, api_key=api_key)
    else:
        return await call_openai(prompt, client)


# ── PROMPTS ───────────────────────────────────────────────────────────────────

def build_prompt(topic: str, signals: list[dict], platform_sentiment: dict) -> str:
    """
    Build a focused prompt. We send signal titles/bodies (not raw API responses)
    to the LLM. ~500 tokens input, ~150 tokens output per topic.
    """
    # Format signal snippets — keep it tight to save tokens
    # Noise patterns — single-word reactions and mention-heavy posts add
    # zero semantic value to the LLM prompt and waste tokens
    import re
    _noise_re = re.compile(
        r'^(lol|lmao|wow|wtf|omg|this|same|yes|no|ok|okay|true|facts?|thread|'
        r'breaking|watch|read|listen|check|see|look)[.!?\s]*$',
        re.IGNORECASE,
    )

    snippets = []
    for s in signals[:TOP_SIGNALS]:
        text = (s.get("title") or s.get("body") or "").strip()
        if not text:
            continue
        # Strip URLs
        text = re.sub(r'https?://\S+', '', text).strip()
        if len(text) < 8:
            continue
        # Skip pure reaction posts
        if _noise_re.match(text):
            continue
        # Skip posts that are mostly mentions/hashtags (Bluesky spam pattern)
        words = text.split()
        specials = len(re.findall(r'[@#]\w+', text))
        if len(words) > 0 and specials / len(words) > 0.6:
            continue
        pf = s.get("platform", "?")[:3].upper()
        snippets.append(f"[{pf}] {text[:200]}")

    if not snippets:
        return ""

    # Platform breakdown for divergence
    pf_lines = []
    for pf, data in platform_sentiment.items():
        pf_lines.append(
            f"  {pf}: {data['count']} signals, avg sentiment {data['sentiment']:+.2f}"
        )
    pf_block = "\n".join(pf_lines) if pf_lines else "  (single platform)"

    snippets_block = "\n".join(snippets[:20])

    prompt = f"""You are analysing social media signal data for the topic: "{topic}"

Platform breakdown:
{pf_block}

Top signals (platform prefix, then text):
{snippets_block}

Respond ONLY with valid JSON, no markdown, no explanation. Use this exact structure:
{{
  "summary": "3 sentences. What are people actually saying about {topic}? What's driving the volume? What's the overall mood?",
  "divergence": "1 sentence explaining why platforms differ in their coverage, OR null if all platforms cover it similarly.",
  "dominant_narrative": "5-8 words: the main thing most people are saying",
  "emerging_angle": "5-8 words: minority view or counter-narrative, OR null"
}}"""

    return prompt


# ── DB HELPERS ────────────────────────────────────────────────────────────────

def get_connection():
    return psycopg2.connect(**PG)


def ensure_schema(conn):
    with conn.cursor() as cur:
        cur.execute(SCHEMA_SQL)
    conn.commit()
    log.info("schema ok")


def get_trending_topics(conn) -> list[dict]:
    """
    Get topics with enough signals in the window.
    Mirrors the logic in topic_aggregator but reads directly from signals.
    """
    # Stopwords, abbreviations, and known garbage patterns spaCy extracts
    # as named entities but carry no topic signal value
    TOPIC_BLOCKLIST = (
        # single-token stopwords
        "un", "us", "uk", "eu", "it", "he", "she", "we", "me", "my",
        "the", "this", "that", "they", "them", "you", "your", "our",
        "am", "pm", "st", "nd", "rd", "th",
        "co", "inc", "ltd", "llc", "gov", "org",
        "rt", "via", "re", "cc",
        # known YouTube channel names that leak through
        "bbc news", "bbc newscast", "dw news", "al jazeera", "sky news",
        "abc news", "cnn", "msnbc", "fox news", "nbc news", "cbs news",
        "ryan exclusive:", "c - computerphile", "upfront",
        # weather bot boilerplate
        "iembot", "additional details here",
    )

    sql = """
        SELECT
            unnested_topic                          AS topic,
            COUNT(*)                                AS signal_count,
            COUNT(DISTINCT platform)                AS platform_count,
            array_agg(DISTINCT platform)            AS platforms,
            AVG(sentiment_compound)                 AS avg_sentiment
        FROM (
            SELECT
                jsonb_array_elements_text(topics) AS unnested_topic,
                platform,
                sentiment_compound
            FROM signals
            WHERE last_updated_at >= NOW() - INTERVAL '%s minutes'
              AND topics IS NOT NULL
              AND jsonb_array_length(topics) > 0
        ) sub
        WHERE LENGTH(unnested_topic) >= 3
          AND LENGTH(unnested_topic) <= 40
          AND LOWER(unnested_topic) != ALL(%s::text[])
          AND unnested_topic NOT LIKE '%%\r%%'
          AND unnested_topic NOT LIKE '%% - %%'
          AND unnested_topic NOT LIKE '%%:\t%%'
        GROUP BY unnested_topic
        HAVING COUNT(*) >= %s
        ORDER BY COUNT(*) DESC
        LIMIT %s
    """
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(sql, (WINDOW_MINUTES, list(TOPIC_BLOCKLIST), MIN_SIGNALS, MAX_TOPICS))
        return [dict(r) for r in cur.fetchall()]


def get_signals_for_topic(conn, topic: str) -> list[dict]:
    """Get top signals for a topic, ordered by trending_score desc."""
    sql = """
        SELECT
            platform,
            title,
            body,
            author,
            sentiment_compound,
            trending_score,
            score_velocity
        FROM signals
        WHERE last_updated_at >= NOW() - INTERVAL '%s minutes'
          AND topics @> to_jsonb(ARRAY[%s::text])
        ORDER BY COALESCE(trending_score, 0) DESC, COALESCE(score_velocity, 0) DESC
        LIMIT %s
    """
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(sql, (WINDOW_MINUTES, topic, TOP_SIGNALS))
        return [dict(r) for r in cur.fetchall()]


def get_platform_sentiment(signals: list[dict]) -> dict:
    """Aggregate sentiment per platform from signal list."""
    result = {}
    for s in signals:
        pf = s.get("platform", "unknown")
        sent = s.get("sentiment_compound") or 0
        if pf not in result:
            result[pf] = {"count": 0, "sentiment_sum": 0.0}
        result[pf]["count"] += 1
        result[pf]["sentiment_sum"] += sent
    for pf, data in result.items():
        data["sentiment"] = data["sentiment_sum"] / data["count"] if data["count"] else 0
    return result


def summary_is_fresh(conn, topic: str) -> bool:
    """Return True if we generated a summary for this topic within TTL window."""
    sql = """
        SELECT 1 FROM topic_summaries
        WHERE topic = %s
          AND generated_at >= NOW() - INTERVAL '%s minutes'
        LIMIT 1
    """
    with conn.cursor() as cur:
        cur.execute(sql, (topic, SUMMARY_TTL))
        return cur.fetchone() is not None


def write_summary(conn, topic: str, topic_meta: dict, parsed: dict,
                  model: str, prompt_tok: int, completion_tok: int, latency_ms: int):
    sql = """
        INSERT INTO topic_summaries (
            topic, window_minutes, generated_at,
            summary_text, divergence_explanation,
            dominant_narrative, emerging_angle,
            signal_count, platform_count, platforms, avg_sentiment,
            model_used, prompt_tokens, completion_tokens, latency_ms
        ) VALUES (
            %s, %s, NOW(),
            %s, %s, %s, %s,
            %s, %s, %s, %s,
            %s, %s, %s, %s
        )
        ON CONFLICT DO NOTHING
    """
    with conn.cursor() as cur:
        cur.execute(sql, (
            topic,
            WINDOW_MINUTES,
            parsed.get("summary"),
            parsed.get("divergence"),
            parsed.get("dominant_narrative"),
            parsed.get("emerging_angle"),
            topic_meta.get("signal_count"),
            topic_meta.get("platform_count"),
            json.dumps(list(topic_meta.get("platforms") or [])),
            topic_meta.get("avg_sentiment"),
            model,
            prompt_tok,
            completion_tok,
            latency_ms,
        ))
    conn.commit()


# ── MAIN LOOP ─────────────────────────────────────────────────────────────────

async def process_topic(
    topic_meta: dict,
    conn,
    client: httpx.AsyncClient,
    api_key: str = "",
) -> Optional[dict]:
    topic = topic_meta["topic"]

    if await asyncio.to_thread(summary_is_fresh, conn, topic):
        log.debug(f"skip {topic!r} — fresh summary exists")
        return None

    signals = await asyncio.to_thread(get_signals_for_topic, conn, topic)
    if not signals:
        log.debug(f"skip {topic!r} — no signals found")
        return None

    # Spam guard — if one author accounts for >80% of signals the topic
    # is almost certainly a bot or repeat-poster, not organic discourse
    authors = [s.get("author") for s in signals if s.get("author")]
    if authors:
        top_author_share = max(authors.count(a) for a in set(authors)) / len(authors)
        if top_author_share > 0.8:
            log.info(f"skip {topic!r} — dominated by single author ({top_author_share:.0%} share, spam)")
            return None

    pf_sentiment = get_platform_sentiment(signals)
    prompt = build_prompt(topic, signals, pf_sentiment)
    if not prompt:
        log.debug(f"skip {topic!r} — no usable signal text")
        return None

    t0 = time.monotonic()
    try:
        raw, prompt_tok, completion_tok = await call_llm(prompt, client, api_key=api_key)
        latency_ms = int((time.monotonic() - t0) * 1000)
    except Exception as e:
        log.warning(f"LLM error for {topic!r}: {e}")
        return None

    # Parse JSON response
    try:
        # Strip markdown code fences if present
        raw_clean = raw.strip()
        if raw_clean.startswith("```"):
            raw_clean = raw_clean.split("```")[1]
            if raw_clean.startswith("json"):
                raw_clean = raw_clean[4:]
        parsed = json.loads(raw_clean.strip())
    except json.JSONDecodeError:
        log.warning(f"bad JSON from LLM for {topic!r}: {raw[:100]}")
        return None

    model_name = {
        "openai": "gpt-4o-mini",
        "anthropic": "claude-haiku-4-5-20251001",
        "groq": "llama-3.1-8b-instant",
    }.get(LLM_PROVIDER, LLM_PROVIDER)

    await asyncio.to_thread(
        write_summary, conn, topic, topic_meta, parsed, model_name,
        prompt_tok, completion_tok, latency_ms,
    )

    log.info(
        f"summarised {topic!r} | {topic_meta['signal_count']} signals "
        f"| {latency_ms}ms | {prompt_tok}+{completion_tok} tokens"
    )
    return parsed


# Max concurrent LLM calls — keeps us inside Groq/OpenAI rate limits on cloud.
# Raise to 10 if on a paid tier with higher RPM.
# With 3 Groq keys round-robin = 90 req/min combined limit.
# concurrency=5 + 2.5s sleep = ~24 req/min per key = 72 req/min total (safe)
# If you only have 1 key, set SUMMARISER_CONCURRENCY=2 in .env
LLM_CONCURRENCY = int(os.getenv("SUMMARISER_CONCURRENCY", 5))


async def run_once(conn, client: httpx.AsyncClient):
    topics = await asyncio.to_thread(get_trending_topics, conn)
    log.info(f"found {len(topics)} topics with >={MIN_SIGNALS} signals")

    # prioritise topics that haven't been summarised recently
    # so high-value topics don't get starved by 429s hitting lower topics first
    async def get_age(t):
        fresh = await asyncio.to_thread(summary_is_fresh, conn, t['topic'])
        return (1 if fresh else 0, -t.get('signal_count', 0))

    import asyncio as _aio
    ages = await _aio.gather(*[get_age(t) for t in topics])
    topics = [t for _, t in sorted(zip(ages, topics), key=lambda x: x[0])]
    log.info(f"topics reordered — stale first, by signal count")

    semaphore = asyncio.Semaphore(LLM_CONCURRENCY)
    # Assign one Groq key per worker slot — each worker owns its key
    # for the full run so keys don't contend with each other.
    # Worker 0 → key 0, worker 1 → key 1, etc. (wraps if fewer keys than workers)
    worker_keys = [
        GROQ_KEYS[i % len(GROQ_KEYS)] if GROQ_KEYS else ""
        for i in range(LLM_CONCURRENCY)
    ]
    worker_id = 0
    worker_id_lock = asyncio.Lock()

    async def process_with_sem(topic_meta: dict) -> Optional[dict]:
        nonlocal worker_id
        async with worker_id_lock:
            my_key = worker_keys[worker_id % LLM_CONCURRENCY]
            worker_id += 1
        async with semaphore:
            result = await process_topic(topic_meta, conn, client, api_key=my_key)
            # 2.5s pacing per worker — keeps each key under 30 req/min
            await asyncio.sleep(2.5)
            return result

    results = await asyncio.gather(
        *[process_with_sem(t) for t in topics],
        return_exceptions=True,
    )

    skipped = 0
    processed = 0
    errors = 0

    for topic_meta, result in zip(topics, results):
        if isinstance(result, Exception):
            log.error(f"unexpected error for {topic_meta['topic']!r}: {result}")
            errors += 1
        elif result is None:
            skipped += 1
        else:
            processed += 1

    log.info(f"run complete — processed={processed} skipped={skipped} errors={errors}")

    # ── RETRY PASS ────────────────────────────────────────────────────────────
    # Topics that got 429'd are marked as errors. Groq rate limit resets every
    # 60 seconds — wait, then retry the top unsummarised high-signal topics.
    errored_topics = [
        topics[i] for i, r in enumerate(results)
        if isinstance(r, Exception)
    ]
    # Also grab any high-signal topics that were skipped (None result) but
    # don't yet have a summary in the DB at all (first-time topics)
    missing_topics = [
        topics[i] for i, r in enumerate(results)
        if r is None and topics[i].get("signal_count", 0) >= 50
    ]
    retry_queue = (errored_topics + missing_topics)[:10]  # top 10 only

    if retry_queue:
        log.info(f"retry pass: {len(retry_queue)} topics after 62s rate-limit reset")
        await asyncio.sleep(62)  # wait for Groq 1-min window to reset
        retry_processed = 0
        for topic_meta in retry_queue:
            try:
                result = await process_topic(topic_meta, conn, client)
                if result is not None:
                    retry_processed += 1
                await asyncio.sleep(3)  # conservative pacing on retry
            except Exception as e:
                log.warning(f"retry failed for {topic_meta['topic']!r}: {e}")
        log.info(f"retry pass complete — processed={retry_processed}/{len(retry_queue)}")


async def main():
    log.info(f"starting topic_summariser | provider={LLM_PROVIDER} | interval={POLL_INTERVAL}s")

    # Validate API keys
    if LLM_PROVIDER == "groq":
        if not GROQ_KEYS:
            log.error("no Groq keys found. Set GROQ_API_KEY_1 (and optionally _2, _3) in .env")
            return
        log.info(f"Groq key pool: {len(GROQ_KEYS)} key(s) — effective limit: {len(GROQ_KEYS) * 30} req/min")
    else:
        key_map = {"openai": OPENAI_KEY, "anthropic": ANTHROPIC_KEY}
        if not key_map.get(LLM_PROVIDER, ""):
            log.error(f"no API key found for provider={LLM_PROVIDER}. Set the env var and restart.")
            return

    conn = get_connection()
    await asyncio.to_thread(ensure_schema, conn)

    async with httpx.AsyncClient() as client:
        while True:
            try:
                await run_once(conn, client)
            except psycopg2.OperationalError as e:
                log.error(f"DB connection lost: {e} — reconnecting")
                try:
                    conn.close()
                except Exception:
                    pass
                conn = get_connection()
            except Exception as e:
                log.error(f"run_once failed: {e}")

            log.info(f"sleeping {POLL_INTERVAL}s until next run")
            await asyncio.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    asyncio.run(main())
