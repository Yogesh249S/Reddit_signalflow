import time
from ingestion.reddit_client import fetch_new_posts
from ingestion.reddit_client import safe_fetch_new_posts
from ingestion.kafka_client import get_producer

from ingestion.priority_rules import calculate_priority
from ingestion.post_selector import should_refresh
from ingestion.refresh_logic import refresh_post
#
# from reddit_producer.ingestion.reddit_client import fetch_new_posts
# from reddit_producer.ingestion.reddit_client import safe_fetch_new_posts
# from reddit_producer.ingestion.kafka_client import get_producer
#
# from reddit_producer.ingestion.priority_rules import calculate_priority
# from reddit_producer.ingestion.post_selector import should_refresh
# from reddit_producer.ingestion.refresh_logic import refresh_post


# Top engagement subreddits (fast polling - 300s)
TOP_SUBREDDITS = [
    {"name": "askreddit", "interval": 300},
    {"name": "funny", "interval": 300},
    {"name": "gaming", "interval": 300},
    {"name": "pics", "interval": 300},
    {"name": "todayilearned", "interval": 300},
    {"name": "aww", "interval": 300},
    {"name": "memes", "interval": 300},
    {"name": "movies", "interval": 300},
    {"name": "news", "interval": 300},
    {"name": "worldnews", "interval": 300},
]

# Mid-size engagement subreddits (slower polling - 1800s)
MID_SUBREDDITS = [
    {"name": "technology", "interval": 1800},
    {"name": "science", "interval": 1800},
    {"name": "space", "interval": 1800},
    {"name": "history", "interval": 1800},
    {"name": "books", "interval": 1800},
    {"name": "dataisbeautiful", "interval": 1800},
    {"name": "explainlikeimfive", "interval": 1800},
    {"name": "personalfinance", "interval": 1800},
    {"name": "programming", "interval": 1800},
    {"name": "machinelearning", "interval": 1800},
]

# Merge both groups
SUBREDDITS = TOP_SUBREDDITS + MID_SUBREDDITS


last_polled = {}

# TEMP in-memory storage for active posts
# (Later replace with DB/storage layer)
ACTIVE_POSTS = []


def run_scheduler():
    producer = get_producer()

    while True:
        now = time.time()

        # ==========================
        # FLOW 1 — Fetch NEW posts
        # ==========================
        for sub in SUBREDDITS:
            name = sub["name"]
            interval = sub["interval"]

            if now - last_polled.get(name, 0) >= interval:
                print(f"Fetching new posts from {name}")

                posts = safe_fetch_new_posts(name)

                for p in posts:
                    # NEW: assign polling priority
                    p["poll_priority"] = calculate_priority(
                        p["created_utc"], now
                    )

                    # mark first poll
                    p["last_polled_at"] = None

                    # store locally (temporary until DB layer)
                    ACTIVE_POSTS.append(p)

                    producer.send("reddit.posts.raw", p)

                last_polled[name] = now

        # 🧹 Remove posts older than 24h from ACTIVE_POSTS
        ACTIVE_POSTS[:] = [
            p for p in ACTIVE_POSTS
            if now - p["created_utc"] <= 86400]


        # ==========================
        #  FLOW 2 — Refresh active posts
        # ==========================
        for post in ACTIVE_POSTS:
            priority = post.get("poll_priority")

            if priority == "aggressive":
                refresh_interval = 300
            elif priority == "normal":
                refresh_interval = 1800
            elif priority == "slow":
                refresh_interval = 7200
            else:
                continue

            if should_refresh(post, refresh_interval, now):
                print(f"Refreshing post {post.get('id')}")

                updated = refresh_post(post)
                updated["poll_priority"] = calculate_priority(
                    updated["created_utc"], now
                )
                updated["last_polled_at"] = now

                producer.send("reddit.posts.refresh", updated)

        time.sleep(10)
