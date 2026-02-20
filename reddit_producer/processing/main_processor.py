import json
from kafka import KafkaConsumer

# DB layer
from .db_writer import (
    upsert_post_snapshot,
    insert_metrics_history,
    upsert_nlp_features
)

# Analytics modules
from .analytics.sentiment import analyze_sentiment
from .analytics.engagement_velocity import calculate_velocity
from .analytics.trending_score import compute_trending


# ===============================
# 🟢 HANDLE RAW EVENTS
# ===============================
def handle_raw(post):

    # ---- NLP Analysis ----
    sentiment_score, sentiment_label = analyze_sentiment(post["title"])

    # simple keyword extraction placeholder
    keywords = post["title"].lower().split()[:5]

    # ---- DB writes ----
    upsert_post_snapshot(post)
    upsert_nlp_features(post["id"], sentiment_score, keywords)

    print(f"[RAW] Processed post {post['id']}")


# ===============================
# 🔵 HANDLE REFRESH EVENTS
# ===============================
def handle_refresh(post):

    # ---- Velocity Calculation ----
    score_velocity, comment_velocity = calculate_velocity(post)

    # ---- Sentiment reused (optional) ----
    sentiment_score, _ = analyze_sentiment(post["title"])

    # ---- Trending Logic ----
    trending_score, is_trending = compute_trending(
        post,
        score_velocity,
        sentiment_score
    )



    # ---- DB Writes ----
    upsert_post_snapshot(post)
    insert_metrics_history(post)




# ===============================
# 🧠 MAIN STREAM LOOP
# ===============================
def run_processor():

    consumer = KafkaConsumer(
        "reddit.posts.raw",
        "reddit.posts.refresh",
        bootstrap_servers="kafka:9092",
        value_deserializer=lambda x: json.loads(x.decode("utf-8"))
    )

    print("Streaming processor started...")

    for message in consumer:

        topic = message.topic
        post = message.value

        try:

            if topic == "reddit.posts.raw":
                handle_raw(post)

            elif topic == "reddit.posts.refresh":
                handle_refresh(post)

        except Exception as e:
            print(f"Error processing message: {e}")


# ===============================
# ENTRYPOINT
# ===============================
if __name__ == "__main__":
    run_processor()
