

def should_refresh(post, interval_seconds, now):
    last_polled = post.get("last_polled_at")

    if last_polled is None:
        return True

    return (now - last_polled) > interval_seconds
