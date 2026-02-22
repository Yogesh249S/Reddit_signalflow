# Reddit_signalflow
Signalflow is a real-time social media intelligence platform built on a production-grade event streaming architecture. It ingests, processes, and analyses content from Reddit across multiple subreddits simultaneously, surfacing trending signals, engagement velocity, and sentiment patterns as they emerge.



## Table of Contents

1. [What This Is](#1-what-this-is)
2. [Why It's Built This Way](#2-why-its-built-this-way)
3. [Architecture Overview](#3-architecture-overview)
4. [Data Flow — End to End](#4-data-flow--end-to-end)
5. [Ingestion Service](#5-ingestion-service)
6. [Processing Service](#6-processing-service)
7. [Database Layer](#7-database-layer)
8. [Django API & WebSocket](#8-django-api--websocket)
9. [Live Dashboard](#9-live-dashboard)
10. [Observability](#10-observability)
11. [Deployment Guide](#11-deployment-guide)
12. [Operational Runbook](#12-operational-runbook)
13. [Configuration Reference](#13-configuration-reference)
14. [Known Gaps & Roadmap](#14-known-gaps--roadmap)

---

## 1. What This Is

Reddit Pulse is a **production-grade real-time data platform** that continuously monitors Reddit subreddits, processes engagement metrics and NLP signals at stream speed, stores time-series data in a purpose-built engine, and serves results through a live-updating REST and WebSocket API.

The project is infrastructure, not a Reddit analytics tool in the narrow sense. The same pipeline — Kafka ingestion, micro-batch processing, TimescaleDB storage, WebSocket serving — could be pointed at financial news feeds, brand monitoring queries, or academic discourse tracking with minimal changes to the ingestion layer. Reddit is the demonstration domain.

### What it monitors

- Configurable subreddits via Django Admin (hot-reloaded without restarts)
- Post scores, comment counts, upvote ratios — polled at tiered intervals
- Score velocity and comment velocity — upvotes per second computed across refresh cycles
- VADER sentiment on post titles — cached per post for the 24h lifecycle
- Trending score — weighted composite of velocity, sentiment, and comment volume
- Topic keywords — extracted from titles, stored as JSONB

### What it produces

- Live WebSocket feed of post updates pushed to connected dashboards
- REST API with JWT auth, cursor pagination, and 30s Redis-cached stats
- TimescaleDB hypertable with 90-day retention and continuous hourly aggregates
- Prometheus metrics on throughput, latency, DLQ rate, and pool saturation
- Grafana dashboard with pre-provisioned panels

---

## 2. Why It's Built This Way

Every architectural decision exists to solve a specific problem encountered during development.

| Decision | Problem it solves |
|---|---|
| Kafka over a task queue | Two genuinely different data streams (raw vs refresh) with different consumers and processing semantics. Kafka's consumer group partition assignment enables horizontal scaling by adding replicas — no code change required. |
| TimescaleDB over plain Postgres | `post_metrics_history` is append-only time-series. Hypertable chunks mean time-range queries scan only relevant partitions. Retention drops entire chunk files — no WAL-bloating DELETEs. |
| asyncio concurrent polling | Sequential subreddit polling: 20 subreddits × 1s API call = 20s per cycle. asyncio tasks: all 20 complete in ~1s wall time — network I/O overlaps. |
| Redis velocity cache | Three processing replicas each had their own in-memory velocity dict. A post processed by replica A, then replica B, computed velocity against B's empty cache — always returning 0.0. Shared Redis cache eliminates split-brain. |
| Micro-batching with manual offsets | One DB write per message = 500 messages/min → 1000 DB round-trips/min. At batch_size=50: 10 round-trips/min (50× reduction). Manual `consumer.commit()` only after confirmed DB write: crash mid-batch re-delivers from last committed offset. Combined with upserts, re-delivery is idempotent. |
| DB-driven subreddit config | Hard-coded subreddit list required a container restart to change. `subreddit_config` table + Django Admin + background config_watcher: add/pause subreddits with zero downtime. Changes propagate within 60 seconds. |
| Daphne ASGI over Gunicorn WSGI | Gunicorn cannot handle WebSocket connections. Daphne handles HTTP and WebSocket on the same port. Django Channels routes by protocol type. |
| Read replica routing | All Django reads hitting the primary competed with processing service write bursts. Router sends ORM reads to the streaming replica, writes to the primary. |
| DLQ with HTTP replay | Failed batches silently dropped = data loss. DLQ routes failed messages to `reddit.posts.dlq` with full error context. HTTP replay API allows ops to re-process failed messages without code changes or redeployment. |

---

## 3. Architecture Overview

### Service inventory

| Container | Image | Role | Port |
|---|---|---|---|
| `zookeeper` | confluentinc/cp-zookeeper:7.5.0 | Kafka coordination | 2181 |
| `kafka`, `kafka2`, `kafka3` | confluentinc/cp-kafka:7.5.0 | Message broker cluster | 29092, 9093, 9094 |
| `kafka-init` | one-shot | Topic creation | — |
| `postgres` | timescale/timescaledb:latest-pg15 | Primary DB | 5433 |
| `postgres-replica` | timescale/timescaledb:latest-pg15 | Read replica | 5434 |
| `redis` | redis:7-alpine | Cache + channels + velocity | 6379 |
| `ingestion` | local build | Reddit API polling | — |
| `processing` ×3 | local build | Stream processing | 8010–8012 |
| `dlq-consumer` | local build | DLQ monitoring + replay | 8001 |
| `reddit_django` | local build | API + WebSocket server | 8080 |
| `prometheus` | prom/prometheus:v2.47.0 | Metrics collection | 9090 |
| `grafana` | grafana/grafana:10.1.0 | Dashboards | 3000 |

### Infrastructure layers

```
Reddit API  (OAuth, 60 req/min per app)
     │
     ▼
Ingestion Service  (asyncio, concurrent per-subreddit tasks)
     │  aiokafka producer — Snappy compression, 500ms linger
     ▼
Kafka Cluster  (3 brokers, RF=3, minISR=2)
     ├── reddit.posts.raw      3 partitions
     ├── reddit.posts.refresh  3 partitions
     └── reddit.posts.dlq      1 partition
     │
     ▼
Processing Service  (×3 replicas, one partition each)
     │  Micro-batch flush, VADER sentiment, velocity, trending score
     │
     ├──▶  Postgres Primary (TimescaleDB)
     │          │
     │          │  WAL streaming replication
     │          ▼
     │     Postgres Replica (hot standby)
     │          ▲
     │          │  ORM reads via ReadReplicaRouter
     │
     ├──▶  Redis DB0  (velocity cache, shared across replicas)
     │
     └──▶  Redis DB2  (Django Channels pub/sub)
               │
               ▼
          Django / Daphne ASGI
               ├── REST API  /api/posts/  /api/stats/
               ├── WebSocket /ws/posts/
               └── Admin     /admin/
               │
               ├──▶  Redis DB1  (30s response cache)
               └──▶  React Dashboard  (Recharts, live WS updates)

Prometheus  scrapes ×3 processing replicas every 15s
Grafana     pre-provisioned panels from prometheus data
```

### Kafka topic design

Three brokers with replication factor 3 and `min.insync.replicas=2`:

- With 1 broker down: writes still succeed (2 ISR ≥ minISR of 2)
- With 2 brokers down: writes pause until a broker recovers — no data loss
- Topics created explicitly — `auto.create.topics.enable=false` prevents typo phantom topics
- 3 partitions per topic supports 3 concurrent processing replicas, one partition each

### Redis logical databases

| DB | Purpose | TTL |
|---|---|---|
| 0 | Velocity cache — `vel:{post_id}` hash of score/comments/ts | 25h per key |
| 1 | Django response cache — stats endpoint | 30s per query |
| 2 | Django Channels layer — WebSocket group pub/sub | Managed by channels_redis |

`maxmemory=512MB`, `allkeys-lru` eviction. If Redis is unreachable, velocity falls back to per-replica in-memory dict — calculations degrade to split-brain mode but the pipeline continues.

---

## 4. Data Flow — End to End

A single Reddit post from first appearance to WebSocket delivery:

```
1. Reddit user posts to r/technology  (ID: xyz789)

2. INGESTION
   poll_subreddit("technology") fetches /r/technology/new
   xyz789 not in active_posts dict → is_new = True
   calculate_priority() → "aggressive"  (post < 5 min old)
   producer.send("reddit.posts.raw", serialized_post)
   active_posts["xyz789"] = post

3. KAFKA
   Message lands on partition hash(xyz789) % 3
   Replicated to all 3 brokers  →  ack returned to producer

4. PROCESSING — raw path
   Replica assigned to that partition pulls message into raw_batch
   At 50 messages OR 2s timeout → flush_batches():
     analyze_sentiment(title) → compound=0.34
     keywords = ["breakthrough", "quantum", "computing"]
     bulk_upsert_posts([...50 posts...])      one execute_values() call
     bulk_upsert_nlp_features([...50 rows...]) one execute_values() call
     consumer.commit()  →  Kafka offset advances

5. POSTGRES
   Primary writes to WAL
   Replica streams WAL and applies within milliseconds
   xyz789 queryable from both primary and replica

6. INGESTION — refresh, 5 min later
   "xyz789" in active_posts, priority="aggressive" → due for refresh
   producer.send("reddit.posts.refresh", updated_post)

7. PROCESSING — refresh path
   calculate_velocity():
     prev = Redis HGET vel:xyz789  →  {score:45, comments:2, ts:T0}
     score_velocity   = (1200 - 45) / 300 = 3.85 per second
     comment_velocity = (45 - 2)   / 300 = 0.14 per second
   Redis HSET vel:xyz789  {score:1200, comments:45, ts:T1}
   compute_trending(velocity=3.85, sentiment=0.34, comments=45) → 0.2
   bulk_upsert_posts()         updates score, velocity, trending_score
   bulk_insert_metrics_history() appends row to hypertable
   publish_post_updates()      Redis PUBLISH asgi:group:posts_feed

8. DJANGO CHANNELS
   All PostFeedConsumer instances subscribed to "posts_feed"
   channels_redis delivers to each connected Daphne instance
   post_update() handler calls await self.send_json(event["data"])

9. BROWSER
   WebSocket receives JSON frame
   Dashboard updates score, velocity, trending badge — no HTTP poll
```

---

## 5. Ingestion Service

### Concurrent async polling

```python
# Sequential — 20 subreddits × 1s = 20s per cycle
for subreddit in subreddits:
    poll(subreddit)

# asyncio — all 20 complete in ~1s, network I/O overlaps
tasks = [asyncio.create_task(poll_subreddit(sub)) for sub in subreddits]
```

### Priority tiers

```
aggressive    post < 5 min old     refresh every 5 min
normal        post < 60 min old    refresh every 30 min
slow          post < 24 h old      refresh every 2 hours
inactive      post > 24 h old      no longer refreshed
```

All thresholds are environment variables — tunable from `.env` without rebuilding.

### Hot-reload via config_watcher

```python
async def config_watcher():
    while True:
        await asyncio.sleep(60)
        new_config = await asyncio.to_thread(_fetch_subreddit_config)
        _spawn_poll_tasks(new_config)
```

`_spawn_poll_tasks()` diffs the new list against the current `task_map`. Removed subreddits: `task.cancel()`. New subreddits: `asyncio.create_task(...)`. Unchanged: continue running. Changes made in Django Admin take effect within 60 seconds with no restart.

### Reddit API quota

Reddit allows 600 requests per 10 minutes (~60 req/min sustained) per OAuth client. Each subreddit costs approximately 3.4 req/min at default settings. One OAuth app supports 16–18 subreddits at aggressive intervals, or 40–45 at slow/medium. For more subreddits, register additional OAuth apps and run additional ingestion containers with distinct `INGESTION_SHARD_ID` env vars.

---

## 6. Processing Service

### Micro-batching

Messages accumulate in `raw_batch` and `refresh_batch`. A flush triggers when `len(batch) >= 50` (BATCH_SIZE) or `time.monotonic() - last_flush >= 2.0` (BATCH_TIMEOUT). Result: 500 messages/min → 10 database operations/min. One statement, one query plan, one network round-trip per batch.

### Exactly-once semantics

```python
enable_auto_commit = False

try:
    flush_batches(raw_batch, refresh_batch)
    consumer.commit()           # offset advances ONLY after confirmed DB write
except Exception as e:
    send_to_dlq(raw_batch, refresh_batch, e)
    # no commit — Kafka re-delivers from last committed offset
    # ON CONFLICT DO UPDATE makes re-delivery idempotent
```

### Sentiment analysis

VADER (`SentimentIntensityAnalyzer`) initialised once at module import. Sentiment is cached per post ID — in a 24h post lifecycle VADER runs exactly once on ingestion. All refresh cycles hit the cache.

```
compound >= 0.05   →  positive
compound <= -0.05  →  negative
else               →  neutral
```

### Velocity calculation

```python
score_velocity   = (current_score    - prev_score)    / max(delta_seconds, 1.0)
comment_velocity = (current_comments - prev_comments) / max(delta_seconds, 1.0)
```

Previous values stored in Redis (`vel:{post_id}` HASH). All three replicas share Redis DB 0 — velocity is always computed against the true last observation, no split-brain.

### Trending score

| Condition | Weight |
|---|---|
| `score_velocity > 50/s` (TRENDING_VELOCITY_HIGH) | +0.4 |
| `score_velocity > 10/s` (TRENDING_VELOCITY_LOW) | +0.2 |
| `abs(sentiment_score) > 0.5` (TRENDING_SENTIMENT_MIN) | +0.2 |
| `num_comments > 100` (TRENDING_COMMENT_MIN) | +0.2 |

`is_trending = trending_score >= 0.5` — requires at least two concurrent signals. All thresholds are environment variables.

### Dead-letter queue

On any batch flush failure: offsets are not committed (re-delivery guaranteed), every message in the failed batch is published to `reddit.posts.dlq` with a full error envelope, and `reddit_processor_dlq_messages_total` is incremented.

The DLQ consumer exposes an HTTP replay API on port 8001:

```
GET  /dlq               view all buffered failures
GET  /dlq/stats         failure counts per topic
POST /dlq/replay        republish all buffered messages to source topic
POST /dlq/replay/{idx}  replay a single message by index
```

---

## 7. Database Layer

### Schema overview

```
subreddits                  subreddit metadata, id cache
posts                       central table, upserted on every refresh
post_metrics_history        TimescaleDB hypertable (time-series per post)
post_nlp_features           sentiment score, keywords JSONB, topic_cluster
post_metrics_hourly         continuous aggregate (1h buckets, refreshed 30min)
subreddit_config            hot-reload config managed from Django Admin
dlq_events                  durable DLQ persistence (survives restarts)
```

### posts table — key columns

```sql
id                TEXT PRIMARY KEY        -- Reddit's string ID
first_seen_at     TIMESTAMPTZ             -- set once on insert, never updated
last_polled_at    TIMESTAMPTZ             -- updated every refresh cycle
current_score     INT                     -- overwritten on upsert
current_comments  INT                     -- overwritten on upsert
poll_priority     TEXT                    -- aggressive/normal/slow/inactive
score_velocity    FLOAT                   -- upvotes per second
comment_velocity  FLOAT                   -- comments per second
trending_score    FLOAT                   -- composite 0.0–1.0
is_trending       BOOLEAN                 -- trending_score >= 0.5
```

### Index strategy

```sql
-- Partial index on is_active — avoids low-selectivity full boolean scan
CREATE INDEX idx_posts_active_created
  ON posts (created_utc DESC) WHERE is_active = TRUE;

-- Covering index — index-only scan for the stats aggregation query
CREATE INDEX idx_posts_stats_covering
  ON posts (created_utc, current_score DESC, author, subreddit_id)
  WHERE is_active = TRUE;

-- Partial index for trending queries
CREATE INDEX idx_posts_trending
  ON posts (trending_score DESC) WHERE is_trending = TRUE;
```

### TimescaleDB hypertable

`post_metrics_history` is partitioned by day using TimescaleDB's `by_range()` dimension builder:

- **Query performance**: time-range queries scan only relevant day-chunks
- **Retention**: `add_retention_policy('post_metrics_history', INTERVAL '90 days')` drops entire chunk files — no WAL-bloating row-level DELETEs
- **Continuous aggregate**: `post_metrics_hourly` materialises hourly summaries, refreshed every 30 minutes — trend charts query pre-aggregated data rather than the raw hypertable

### Migration system

Custom sequential runner in `storage/migrate.py`. Migrations named `V1__init.sql`, `V2__...sql`. A `schema_migrations` table tracks applied versions. The processing service runs these on startup. Django manages its own system tables separately via `python manage.py migrate`.

---

## 8. Django API & WebSocket

### Endpoints

```
GET  /api/posts/          paginated post feed with annotations and NLP data
GET  /api/stats/          aggregate stats — cached 30s in Redis
POST /api/token/          obtain JWT (username + password → access + refresh)
POST /api/token/refresh/  rotate JWT refresh token
GET  /health/             health check — no auth, no DB query
WS   /ws/posts/           live post update stream
```

### PostViewSet — what each post returns

Every post in the feed includes DB-computed annotations and joined NLP features:

```json
{
  "id": "xyz789",
  "subreddit": "technology",
  "title": "New breakthrough in quantum computing",
  "current_score": 1200,
  "current_comments": 45,
  "score_velocity": 3.85,
  "comment_velocity": 0.14,
  "trending_score": 0.2,
  "is_trending": false,
  "engagement_score": 1290,
  "age_minutes": 312.4,
  "momentum": 4.12,
  "nlp": {
    "sentiment_score": 0.34,
    "keywords": ["breakthrough", "quantum", "computing"],
    "topic_cluster": null
  }
}
```

`engagement_score`, `age_minutes`, and `momentum` are annotated on query via SQL expressions — not computed in Python. `nlp` is joined via a single `prefetch_related("nlp_features")` call — not N+1 queries.

Cursor pagination uses `WHERE created_utc < cursor_value` — no `OFFSET` scan that degrades with table size. Maximum `page_size=200`.

### WebSocket consumer

```python
class PostFeedConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        await self.channel_layer.group_add("posts_feed", self.channel_name)
        await self.accept()

    async def post_update(self, event):
        await self.send_json(event["data"])
```

When processing flushes a batch, it publishes to `asgi:group:posts_feed` via Redis pub/sub. Every connected Daphne instance delivers the update to its local WebSocket clients. At 50 connected users polling every 5 seconds this eliminates 600 HTTP requests/minute.

### Authentication

JWT access tokens (60-minute lifetime), refresh tokens (7-day, rotating). Rate throttle: 100 requests/minute per authenticated user, counters in Redis DB 1.

> **Note**: `AllowAny` is currently active for local development. Switch to `IsAuthenticated` in `settings.py` before production.

---

## 9. Live Dashboard

A React + Vite + Recharts dashboard with two pages:

**Posts page**

- Left panel: live feed with time-range filter (30m / 1h / 2h / 3h / 6h / 12h / 24h), subreddit filter, sort by score/velocity/momentum/sentiment
- Center: KPI strip, momentum leaderboard, full posts table with velocity and sentiment columns
- Right: post detail panel with sentiment bar, velocity bar, all metrics

**Stats page**

- Time-range picker controls all charts
- Engagement top 20, velocity leaderboard, activity timeline (posts per hour + avg score), sentiment distribution per subreddit, keyword cloud, age vs engagement scatter
- Sidebar: top authors, subreddit rankings, most upvoted/commented posts

The dashboard polls every 30 seconds as a fallback. The WebSocket pushes live updates instantly when the processing service flushes a batch.

---

## 10. Observability

### Prometheus metrics

Each processing replica exposes metrics on port 8000 (mapped to 8010–8012 on the host). Prometheus scrapes all three every 15 seconds.

| Metric | Type | Description |
|---|---|---|
| `reddit_processor_messages_total{topic}` | Counter | Messages consumed per topic |
| `reddit_processor_batches_total{status}` | Counter | Batch flushes by ok/error |
| `reddit_processor_dlq_messages_total` | Counter | Messages sent to DLQ |
| `reddit_processor_batch_flush_seconds` | Histogram | Batch write latency |
| `reddit_processor_kafka_poll_seconds` | Histogram | Kafka poll latency |

### Grafana dashboard

Pre-provisioned via `grafana/provisioning/`. Access at `http://localhost:3000` (admin/admin).

| Panel | What to watch |
|---|---|
| Messages Consumed/sec | 2–5 sustained, spikes to 15–25 during refresh bursts — normal |
| Batch Flush Latency P99 | Action needed above ~250ms. Currently 70–100ms |
| Batch Outcomes | All ok lines. Any sustained error spikes need immediate investigation |
| DLQ Messages/sec | Should be 0. Any non-zero sustained rate = data loss in progress |

---

## 11. Deployment Guide

### Prerequisites

- Docker Engine 24+ and Docker Compose v2
- 8 GB RAM minimum (16 GB recommended)
- Python 3.11+ and Node 18+ for local development outside Docker
- Reddit OAuth credentials — register at [reddit.com/prefs/apps](https://reddit.com/prefs/apps)

### Step 1 — Environment

```bash
git clone https://github.com/yogesh249s/reddit-pulse
cd reddit-pulse

cp .env.example .env
```

Edit `.env` — minimum required:

```bash
REDDIT_CLIENT_ID=your_client_id
REDDIT_CLIENT_SECRET=your_client_secret
REDDIT_USER_AGENT=reddit-pulse:v1.0 (by /u/your_reddit_username)
DJANGO_SECRET_KEY=generate-a-long-random-string-here
```

### Step 2 — Start the infrastructure

```bash
docker compose up -d

# Watch startup — first run takes ~90 seconds
docker compose ps
```

Wait until all containers show `healthy` or `running`. The `migrate` container must complete before anything else starts writing.

### Step 3 — Django setup

Run Django's own migrations (creates auth, sessions, admin tables):

```bash
# If running Django locally via manage.py
python manage.py migrate

# If running Django inside Docker
docker exec -it reddit_django python manage.py migrate
```

Create a superuser for Django Admin:

```bash
# Local
python manage.py createsuperuser

# Docker
docker exec -it reddit_django python manage.py createsuperuser
```

### Step 4 — Add subreddits

Via Django Admin at `http://localhost:8080/admin` → Subreddit Configs → Add, or bulk insert via SQL:

```bash
docker exec -it postgres psql -U reddit -d reddit
```

```sql
INSERT INTO subreddit_config (name, interval_seconds, priority, is_active, added_by)
VALUES
    ('technology',     60,  'fast',   true, 'setup'),
    ('worldnews',      60,  'fast',   true, 'setup'),
    ('science',        90,  'fast',   true, 'setup'),
    ('programming',    180, 'medium', true, 'setup'),
    ('MachineLearning',180, 'medium', true, 'setup'),
    ('datascience',    300, 'slow',   true, 'setup')
ON CONFLICT (name) DO NOTHING;
```

Ingestion picks up the new config within 60 seconds.

### Step 5 — Start Django locally (optional)

If you prefer to run Django outside Docker against the Dockerised Postgres and Redis:

```bash
# Install dependencies
pip install -r requirements.txt

# Run the development server
python manage.py runserver

# Or run with Daphne (ASGI — required for WebSocket)
daphne -b 0.0.0.0 -p 8000 config.routing:application
```

Django connects to Postgres on port 5433 and Redis on port 6379 by default (configured in `settings.py`).

### Step 6 — Verify the pipeline

```bash
# Kafka has messages flowing
docker exec -it kafka kafka-consumer-groups \
  --bootstrap-server localhost:9092 \
  --describe --group reddit-processor

# Postgres has posts
docker exec -it postgres psql -U reddit -d reddit \
  -c "SELECT COUNT(*), MAX(last_polled_at) FROM posts;"

# API responds
curl http://localhost:8080/health/
curl http://localhost:8080/api/posts/?page_size=5
curl "http://localhost:8080/api/stats/?start=2026-02-21&end=2026-02-21"
```

### Step 7 — Start the dashboard

```bash
cd dashboard/reddit_dashboard
npm install
npm run dev
# Opens at http://localhost:5173
```

### Step 8 — Access all services

| Service | URL | Credentials |
|---|---|---|
| React dashboard | http://localhost:5173 | — |
| Django API | http://localhost:8080/api/ | — |
| Django Admin | http://localhost:8080/admin/ | superuser you created |
| DLQ replay API | http://localhost:8001/dlq | — |
| Grafana | http://localhost:3000 | admin / admin |
| Prometheus | http://localhost:9090 | — |

### Production checklist

Before exposing beyond localhost:

1. Set `IsAuthenticated` in `settings.py` — currently `AllowAny`
2. Rotate `DJANGO_SECRET_KEY` — never use the dev default
3. Set `DEBUG=false` and populate `ALLOWED_HOSTS`
4. Uncomment `DATABASE_ROUTERS` in `settings.py` once replication is confirmed healthy (`pg_stat_replication` shows `state = streaming`)
5. Put Nginx or Traefik in front of Daphne for HTTPS/WSS
6. Replace `acks=1` with `acks=all` in the Kafka producer for stronger durability
7. Run multiple Daphne replicas behind a load balancer — Channels is stateless, Redis channel layer handles fan-out

---

## 12. Operational Runbook

### Add a subreddit

```
Django Admin → http://localhost:8080/admin
→ Subreddit Configs → Add Subreddit Config
  name: wallstreetbets
  interval_seconds: 60
  priority: fast
  is_active: ✓
→ Save
```

Takes effect within 60 seconds. Watch `docker logs ingestion` for confirmation.

### Pause a subreddit

```
Django Admin → Subreddit Configs → [subreddit] → is_active: uncheck → Save
```

The `config_watcher` coroutine cancels that subreddit's poll task within 60 seconds.

### Check replication health

```bash
docker exec -it postgres psql -U reddit -d reddit \
  -c "SELECT client_addr, state, sent_lsn, replay_lsn FROM pg_stat_replication;"
# state must be "streaming"
```

### Inspect and replay DLQ failures

```bash
curl http://localhost:8001/dlq           # view all buffered failures
curl http://localhost:8001/dlq/stats     # failure counts by topic
curl -X POST http://localhost:8001/dlq/replay        # replay all
curl -X POST http://localhost:8001/dlq/replay/0      # replay one by index
```

### Scale processing replicas

```bash
docker compose up -d --scale processing=5
```

Kafka automatically reassigns partitions. With 3 partitions, max 3 replicas do useful work simultaneously. Increase partitions first:

```bash
docker exec -it kafka kafka-topics \
  --bootstrap-server localhost:9092 \
  --alter --topic reddit.posts.raw --partitions 6
```

### Tune trending thresholds

```bash
# In .env
TRENDING_VELOCITY_HIGH=100
TRENDING_COMMENT_MIN=200

docker compose up -d processing   # restart processing only, no rebuild
```

---

## 13. Configuration Reference

### Reddit API

| Variable | Default | Description |
|---|---|---|
| `REDDIT_CLIENT_ID` | — | OAuth app client ID |
| `REDDIT_CLIENT_SECRET` | — | OAuth app client secret |
| `REDDIT_USER_AGENT` | — | Identifies your app to Reddit |
| `INGESTION_SHARD_ID` | `0` | Which shard of subreddit_config to poll |

### Kafka

| Variable | Default | Description |
|---|---|---|
| `KAFKA_BOOTSTRAP_SERVERS` | `kafka:9092,kafka2:9092,kafka3:9092` | Broker list |
| `BATCH_SIZE` | `50` | Messages before forced flush |
| `BATCH_TIMEOUT` | `2.0` | Seconds before forced flush |

### Database

| Variable | Default | Description |
|---|---|---|
| `POSTGRES_HOST` | `postgres` | Primary host |
| `POSTGRES_PORT` | `5433` | Primary port (Docker host) |
| `POSTGRES_REPLICA_HOST` | `postgres-replica` | Replica host |
| `POSTGRES_REPLICA_PORT` | `5434` | Replica port (Docker host) |
| `POSTGRES_DB` | `reddit` | Database name |
| `POSTGRES_USER` | `reddit` | Username |
| `POSTGRES_PASSWORD` | `reddit` | Change in production |

### Processing

| Variable | Default | Description |
|---|---|---|
| `TRENDING_VELOCITY_HIGH` | `50` | Score velocity threshold for +0.4 signal |
| `TRENDING_VELOCITY_LOW` | `10` | Score velocity threshold for +0.2 signal |
| `TRENDING_SENTIMENT_MIN` | `0.5` | Abs sentiment for +0.2 signal |
| `TRENDING_COMMENT_MIN` | `100` | Comment count for +0.2 signal |
| `PRIORITY_AGGRESSIVE_MINS` | `5` | Posts younger than this get aggressive tier |
| `PRIORITY_NORMAL_MINS` | `60` | Posts younger than this get normal tier |
| `PRIORITY_SLOW_MINS` | `1440` | Posts younger than this get slow tier |
| `SCHEDULER_CONFIG_POLL_S` | `60` | How often config_watcher checks subreddit_config |

### Django

| Variable | Default | Description |
|---|---|---|
| `DJANGO_SECRET_KEY` | `insecure-dev-key` | Must be changed in production |
| `DJANGO_DEBUG` | `true` | Set false in production |
| `DJANGO_ALLOWED_HOSTS` | `localhost,127.0.0.1` | Comma-separated allowed hosts |
| `REDIS_URL` | `redis://redis:6379` | Redis base URL |

---

## 14. Known Gaps & Roadmap

### Current gaps

| Gap | Impact | Fix |
|---|---|---|
| `DATABASE_ROUTERS` commented out | All Django reads hit primary | Uncomment after confirming `pg_stat_replication` shows `streaming` |
| `IsAuthenticated` commented out | API is publicly open | Uncomment `DEFAULT_PERMISSION_CLASSES` in `settings.py` |
| DLQ consumer doesn't write to `dlq_events` | DLQ messages lost on consumer restart | Add `_persist_to_db(envelope)` call in `dlq_consumer.py` |
| `topic_cluster` column never populated | NLP features table incomplete | Implement keyword-to-cluster assignment in `flush_batches()` |
| `tests.py` is empty | No test coverage on analytics functions | Add unit tests for `analyze_sentiment`, `compute_trending`, `calculate_velocity` |
| Velocity cache size gauge not implemented | Dashboard shows "No data" | Add `set_gauge("reddit_processor_velocity_cache_size", ...)` in `velocity_cache.py` |

### Phase 3 — Close the gaps (1–2 weeks)

- Activate `DATABASE_ROUTERS` and `IsAuthenticated`
- DLQ persistence to `dlq_events` table
- Analytics unit tests
- Populate `topic_cluster` with a keyword-based classifier
- Fix Prometheus histogram implementation (switch to official `prometheus_client` buckets)

### Phase 4 — Data quality layer (2–3 weeks)

- Pydantic schema validation at ingestion boundary before Kafka publish
- `schema_version` field on every Kafka message
- DLQ error categorisation: validation vs transient vs permanent
- Subreddit health heartbeat table + Django Admin display

### Phase 5 — Analytics depth (1 month)

- BERTopic batch job for real topic clustering
- Z-score anomaly detection on velocity (self-calibrating per subreddit)
- dbt transformation layer for metric consistency and lineage
- Keyword trending endpoint on the API

### Phase 6 — Data lineage (1 month+)

- `_meta` provenance fields on every Kafka message
- `lineage` JSONB column on `post_metrics_history`
- Pipeline run tracking table
- Backfill/reprocess capability from Kafka offsets

### Domain pivots this backbone supports

| Product | What changes | What stays |
|---|---|---|
| Financial sentiment intelligence | Add ticker entity extraction, focus on finance subreddits | Everything else |
| Brand monitoring platform | Add keyword filter config, webhook alerts on velocity spikes | Everything else |
| Misinformation narrative tracking | Add cross-subreddit diffusion tracking | Everything else |
| Market research tool | Add pain-point keyword extraction | Everything else |

---

## Tech Stack

| Layer | Technology |
|---|---|
| Ingestion | Python 3.11, asyncpraw, aiokafka |
| Stream processing | Python 3.11, kafka-python, psycopg2, vaderSentiment |
| Message broker | Apache Kafka 7.5.0 (Confluent), Zookeeper |
| Primary database | PostgreSQL 15 + TimescaleDB |
| Read replica | PostgreSQL 15 + TimescaleDB (streaming replication) |
| Cache / Channels | Redis 7 |
| API framework | Django 6, Django REST Framework, Django Channels |
| ASGI server | Daphne |
| Authentication | djangorestframework-simplejwt |
| Dashboard | React 19, Vite, Recharts, Framer Motion |
| Monitoring | Prometheus 2.47, Grafana 10.1 |
| Containerisation | Docker Compose 3.9 |

---




















