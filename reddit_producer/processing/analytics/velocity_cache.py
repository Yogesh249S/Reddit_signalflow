# In-memory cache: post_id -> (score, comments, timestamp)
velocity_cache = {}


def get_previous(post_id):
    return velocity_cache.get(post_id)


def update_cache(post_id, score, num_comments, timestamp):
    velocity_cache[post_id] = (score, num_comments, timestamp)
