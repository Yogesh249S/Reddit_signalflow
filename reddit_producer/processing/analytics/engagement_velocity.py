import psycopg2
from .velocity_cache import get_previous, update_cache
import time

conn = psycopg2.connect(
    dbname="reddit",
    user="reddit",
    password="reddit",
    host="postgres",
    port="5432"
)


def calculate_velocity(post):

    post_id = post["id"]
    now = time.time()

    prev = get_previous(post_id)

    if not prev:
        update_cache(post_id, post["score"], post["num_comments"], now)
        return 0.0, 0.0

    old_score, old_comments, old_time = prev

    delta_time = max(now - old_time, 1)

    score_velocity = (post["score"] - old_score) / delta_time
    comment_velocity = (post["num_comments"] - old_comments) / delta_time

    update_cache(post_id, post["score"], post["num_comments"], now)

    return score_velocity, comment_velocity
