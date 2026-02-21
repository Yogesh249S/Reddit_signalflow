# Reddit Pulse — Phase 2 Implementation Notes

Phase 2 takes the Phase 1 foundation (Redis velocity cache, DLQ, TimescaleDB,
observability, schema migrations) and adds horizontal scale, live push, fault
tolerance, and security.

---

## 1. Multi-Replica Processing

**File changed:** `reddit_producer/docker-compose.yml`

Removed `container_name: reddit_processing`. Named containers cannot scale.
Replaced with:

```yaml
processing:
  deploy:
    replicas: 3
    resources:
      limits: { memory: 400m }
    restart_policy:
      condition: on-failure
```

Kafka's partition assignment (3 partitions per topic) distributes messages
evenly across 3 consumers in the same group. Each replica processes a disjoint
partition set — no coordination code needed. Velocity state is shared via the
Redis velocity cache (Phase 1 prerequisite), so all replicas compute accurate
velocity without contention.

**To scale beyond 3:** increase partition count to 6 via `kafka-topics --alter`
then update `docker compose up --scale processing=6`.

---

## 2. WebSocket Dashboard Push

**New files:**
- `apps/reddit/consumers.py` — `PostFeedConsumer` (async Channels consumer)
- `config/routing.py` — Channels `ProtocolTypeRouter`
- `reddit_producer/processing/channel_publisher.py` — Redis pub after flush

**Changed:** `config/settings.py`, `config/asgi.py` → now `ASGI_APPLICATION`
points to `config.routing:application`. Gunicorn replaced with Daphne in
`docker-compose.yml`.

**Flow:**
1. Browser opens `ws://host/ws/posts/`
2. `PostFeedConsumer.connect()` joins the `"posts_feed"` group
3. After each batch DB flush, `channel_publisher.publish_post_updates()` publishes to Redis channel layer (DB 2)
4. Channels delivers the message to all consumers in the group
5. `PostFeedConsumer.post_update()` forwards serialised post list to browser

**Impact:** idle WebSocket traffic = 0 DB queries. Old 5-second HTTP polling
at 50 users = 600 req/min and 600 Postgres queries. Phase 2 = ~0.

---

## 3. 3-Broker Kafka Cluster

**File changed:** `reddit_producer/docker-compose.yml`

Added `kafka2` and `kafka3` services using the shared `x-kafka-common` anchor.
All topics now created with `--replication-factor 3 --partitions 3`.
Key environment:
- `KAFKA_MIN_INSYNC_REPLICAS: 2` — one broker can be dead; writes succeed
- `KAFKA_DEFAULT_REPLICATION_FACTOR: 3`

Producer in `kafka_client.py` already used `acks="all"` (Phase 1). With a
3-broker cluster this now means "wait for 2 in-sync replicas" — true durability.

**Failover:** Kafka elects a new leader in <30s. Consumers pause briefly then
resume from their committed offsets (Phase 1 manual commit) with zero message loss.

---

## 4. Postgres Read Replica

**New files:**
- `config/db_router.py` — `ReadReplicaRouter`

**Changed:** `config/settings.py`

```python
DATABASES['replica'] = {
    'HOST': env('POSTGRES_REPLICA_HOST'),
    ...
}
DATABASE_ROUTERS = ['config.db_router.ReadReplicaRouter']
```

The router sends all `SELECT` queries to the replica and all
`INSERT/UPDATE/DELETE` to the primary. No view or queryset changes needed —
the router is transparent to application code.

The replica is seeded from the primary via `pg_basebackup` in the
`postgres-replica` container entrypoint. WAL streaming keeps it <1s behind.

**Impact:** the primary now receives only bulk upsert writes from the
processing replicas. All Django ORM reads (PostViewSet, stats, Admin) hit the
replica. Effective query throughput roughly doubles with no hardware changes.

---

## 5. Subreddit Management UI

**New files:**
- `reddit_producer/storage/migrations/V4__subreddit_config.sql`
- `apps/reddit/models.py` — `SubredditConfig` model
- `apps/reddit/admin.py` — `SubredditConfigAdmin`

**Changed:** `reddit_producer/ingestion/scheduler.py`

The scheduler now:
1. Calls `_fetch_subreddit_config()` on startup to load active subreddits from the DB
2. Runs a `config_watcher()` asyncio task that re-fetches every `SCHEDULER_CONFIG_POLL_S` seconds (default 60)
3. On config change: cancels tasks for removed subreddits; spawns tasks for new ones

**Operations workflow:**
- Open Django Admin → Subreddit Configs
- Add a row: `name=politics`, `interval_seconds=90`, `priority=fast`, `is_active=True`
- Within 60 seconds the scheduler spawns a `poll-politics` asyncio task
- No code change, no Docker rebuild, no container restart required

---

## 6. API Authentication

**Changed:** `config/settings.py`, `config/urls.py`, `apps/reddit/views.py`

JWT via `djangorestframework-simplejwt`:

```python
# settings.py
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': ['...JWTAuthentication'],
    'DEFAULT_PERMISSION_CLASSES': ['...IsAuthenticated'],
    'DEFAULT_THROTTLE_RATES': {'user': '100/min'},
}
```

**Endpoints:**
| Endpoint | Auth required |
|---|---|
| `POST /api/token/` | No — issues access + refresh tokens |
| `POST /api/token/refresh/` | No — rotates refresh token |
| `GET /api/health/` | No — load balancer probe |
| `GET /api/posts/` | Yes — Bearer token |
| `GET /api/stats/` | Yes — Bearer token |
| All other `/api/*` | Yes — Bearer token |

Rate limiting: 100 req/min per user stored in Redis. Rate limit headers
(`X-RateLimit-*`) returned on every response. Throttle class reads the
`Authorization` header to identify the user.

---

## Dependency chain summary

```
Phase 1: Redis velocity cache
    ↓ (prerequisite)
Phase 2: Multi-replica processing (safe concurrent consumers)
    ↓ (same Redis, DB 2)
Phase 2: WebSocket push (channel layer on DB 2)
    ↓
Phase 2: 3-broker Kafka (durability for messages the replicas consume)
Phase 2: Read replica (offloads reads from the primary the replicas write to)
Phase 2: Subreddit config (ops tooling, scheduler hot-reload)
Phase 2: JWT auth (security gate on the API those replicas serve data through)
```

---

## Running Phase 2

```bash
# From reddit_producer/
docker compose up --build

# Check 3 processing replicas are running
docker compose ps | grep processing

# Watch WebSocket live
wscat -c ws://localhost:8080/ws/posts/ \
  -H "Authorization: Bearer <token>"

# Get a token
curl -X POST http://localhost:8080/api/token/ \
  -d '{"username":"admin","password":"admin"}' \
  -H "Content-Type: application/json"

# Add a subreddit without restarting anything
open http://localhost:8080/admin/reddit/subredditconfig/add/
```
