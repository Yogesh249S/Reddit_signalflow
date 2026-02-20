
import time
import os
import praw
from dotenv import load_dotenv

load_dotenv()

reddit = praw.Reddit(
    client_id=os.getenv("REDDIT_CLIENT_ID"),
    client_secret=os.getenv("REDDIT_CLIENT_SECRET"),
    user_agent=os.getenv("REDDIT_USER_AGENT")
)

# ==========================
# 1. Fetch NEW posts (existing)
# ==========================
def fetch_new_posts(subreddit_name, limit=25):
    subreddit = reddit.subreddit(subreddit_name)

    results = []
    for post in subreddit.new(limit=limit):
        results.append({
            "id": post.id,
            "title": post.title,
            "created_utc": post.created_utc,
            "subreddit": subreddit_name,
            "score": post.score,
            "num_comments": post.num_comments,
            "author": str(post.author) if post.author else "deleted",
            "upvote_ratio": post.upvote_ratio,
        })
    return results



def safe_fetch_new_posts(subreddit_name, limit=25):

    while True:
        try:
            return fetch_new_posts(subreddit_name, limit)

        except prawcore.exceptions.TooManyRequests as e:
            wait_time = getattr(e, "sleep_time", 10)
            print(f"[RATE LIMIT] Sleeping {wait_time}s")
            time.sleep(wait_time)

        except Exception as e:
            print(f"[ERROR] {e}, retrying in 5s")
            time.sleep(5)


# ==========================
# 2. NEW — Fetch post details (for refresh logic)
# ==========================
def fetch_post_details(post_id):
    """
    Fetch updated metrics for an existing post.
    Used by refresh pipeline.
    """
    submission = reddit.submission(id=post_id)

    # Important: refresh() forces PRAW to fetch latest data
    submission._fetch()

    return {
        "id": submission.id,
        "title": submission.title,
        "created_utc": submission.created_utc,
        "subreddit": submission.subreddit.display_name,
        "score": submission.score,
        "num_comments": submission.num_comments,
        "author": str(submission.author) if submission.author else "deleted",
        "upvote_ratio": submission.upvote_ratio,
    }
