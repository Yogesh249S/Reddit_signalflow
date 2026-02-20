import psycopg2
import json
from datetime import datetime

# ==========================
# DB CONNECTION (singleton style)
# ==========================
conn = psycopg2.connect(
    dbname="reddit",
    user="reddit",
    password="reddit",
    host="postgres",
    port="5432"
)
conn.autocommit = True


# ==========================
# ENSURE SUBREDDIT EXISTS
# ==========================
def ensure_subreddit(cur, subreddit_name):

    cur.execute("""
        INSERT INTO subreddits(name)
        VALUES (%s)
        ON CONFLICT (name) DO NOTHING
        RETURNING id;
    """, (subreddit_name,))

    result = cur.fetchone()

    if result:
        return result[0]

    cur.execute(
        "SELECT id FROM subreddits WHERE name=%s",
        (subreddit_name,)
    )

    return cur.fetchone()[0]


# ==========================
# UPSERT POST SNAPSHOT
# ==========================
def upsert_post_snapshot(post):

    with conn.cursor() as cur:

        subreddit_id = ensure_subreddit(cur, post["subreddit"])



        cur.execute("""
            INSERT INTO posts(
                id,
                subreddit_id,
                title,
                author,
                created_utc,
                current_score,
                current_comments,
                current_ratio,
                poll_priority,
                is_active

            )
            VALUES (%s,%s,%s,%s,to_timestamp(%s),%s,%s,%s,%s,TRUE)


            ON CONFLICT (id) DO UPDATE SET
                current_score = EXCLUDED.current_score,
                current_comments = EXCLUDED.current_comments,
                current_ratio = EXCLUDED.current_ratio,
                last_polled_at = NOW();

        """, (
            post["id"],
            subreddit_id,
            post["title"],
            post["author"],
            post["created_utc"],
            post["score"],
            post["num_comments"],
            post["upvote_ratio"],
            post.get("poll_priority"),

        ))


# ==========================
# INSERT METRICS HISTORY
# ==========================
def insert_metrics_history(post):

    with conn.cursor() as cur:

        cur.execute("""
            INSERT INTO post_metrics_history(
                post_id,
                score,
                num_comments,
                upvote_ratio

            )
            VALUES (%s,%s,%s,%s);
        """, (
            post["id"],
            post["score"],
            post["num_comments"],
            post["upvote_ratio"],


        ))


# ==========================
# UPSERT NLP FEATURES
# ==========================
def upsert_nlp_features(post_id, sentiment_score, keywords):

    with conn.cursor() as cur:

        cur.execute("""
            INSERT INTO post_nlp_features(post_id, sentiment_score, keywords)
            VALUES (%s,%s,%s)
            ON CONFLICT(post_id) DO UPDATE SET
                sentiment_score = EXCLUDED.sentiment_score,
                keywords = EXCLUDED.keywords;
        """, (
            post_id,
            sentiment_score,
            json.dumps(keywords)
        ))
