from ingestion.reddit_client import fetch_post_details


def refresh_post(post):
    # posts are dicts, not objects
    post_id = post["id"]

    data = fetch_post_details(post_id)

    # merge updated fields into original post
    updated_post = {**post, **data}

    return updated_post
