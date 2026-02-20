def compute_trending(post, score_velocity, sentiment_score):

    trending_score = 0.0

    if score_velocity > 50:
        trending_score += 0.4
    elif score_velocity > 10:
        trending_score += 0.2

    if abs(sentiment_score) > 0.5:
        trending_score += 0.2

    if post["num_comments"] > 100:
        trending_score += 0.2

    is_trending = trending_score >= 0.5

    return trending_score, is_trending
