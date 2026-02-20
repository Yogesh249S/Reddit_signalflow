from celery import shared_task
from django.core.cache import cache
from django.db.models import Count, Sum, Avg, F
from .models import Post

@shared_task
def compute_stats_snapshot():

    base_qs = Post.objects.all()

    overview = {
        "total_posts": base_qs.count(),
        "avg_score": base_qs.aggregate(avg=Avg("current_score"))["avg"],
        "active_users": base_qs.values("author").distinct().count(),
    }

    top_users = list(
        base_qs.values("author")
        .annotate(posts=Count("id"), total_score=Sum("current_score"))
        .order_by("-total_score")[:50]
    )

    snapshot = {
        "overview": overview,
        "users": top_users,
    }

    #store in redis cache
    cache.set("stats_snapshot", snapshot, timeout=60)

    return "done"
