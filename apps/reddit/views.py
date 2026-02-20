
from datetime import datetime, timedelta, time
from django.db.models.functions import Extract
from django.db.models import Count, Avg, Sum, F, ExpressionWrapper, FloatField
from django.db.models.functions import Now

from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import viewsets

from .models import Subreddit, Post, Comment, KeywordTrend, SubredditStats
from .serializers import (
    SubredditSerializer,
    PostSerializer,
    CommentSerializer,
    KeywordTrendSerializer,
    SubredditStatsSerializer,
)


@api_view(["GET"])
def home(request):
    return Response({"status": "Reddit Trends API Running"})


class PostViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = PostSerializer
    filterset_fields = ["subreddit__name"]

    def get_queryset(self):

        return (
            Post.objects
            .select_related("subreddit")  # 🔥 huge speed boost
            .annotate(
            engagement_score=F("current_score") + (F("current_comments") * 2),

            age_minutes=ExpressionWrapper(
                Extract(Now() - F("created_utc"), "epoch") / 60.0,
                output_field=FloatField(),
            ),

            # ⭐ NEW — MOMENTUM CALCULATION
            momentum=ExpressionWrapper(
                (F("current_score") + (F("current_comments") * 2)) /
                (Extract(Now() - F("created_utc"), "epoch") / 60.0 + 1.0),
                output_field=FloatField(),
            ),
        )

            .order_by("-created_utc")[:300]
        )


class CommentViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Comment.objects.all().order_by("-score")
    serializer_class = CommentSerializer

@api_view(["GET"])
def stats(request):

    start = request.GET.get("start")
    end = request.GET.get("end")


    # 👉 Default = yesterday
    if not start or not end:
        yesterday = datetime.utcnow().date() - timedelta(days=1)
        start_date = yesterday
        end_date = yesterday
    else:
        start_date = datetime.strptime(start, "%Y-%m-%d").date()
        end_date = datetime.strptime(end, "%Y-%m-%d").date()

    # ✅ Build datetime range properly
    start_dt = datetime.combine(start_date, time.min)
    end_dt = datetime.combine(end_date, time.max)

    # ✅ ONE BASE QUERYSET (very important)

    # base_qs = Post.objects.filter(
    # created_utc__date__range=[start, end])

    base_qs = Post.objects.filter(
    created_utc__range=(start_dt, end_dt))


    print("DEBUG START:", start_dt)
    print("DEBUG END:", end_dt)
    print("DEBUG COUNT:", base_qs.count())
    print("DEBUG SAMPLE:", list(base_qs.values("created_utc")[:3]))


    # ---------- OVERVIEW ----------
    overview = {
        "total_posts": base_qs.count(),
        "avg_score": base_qs.aggregate(avg=Avg("current_score"))["avg"],
        "active_users": base_qs.values("author").distinct().count(),
    }

    # ---------- POST LEVEL ----------
    most_upvoted = base_qs.order_by("-current_comments").values(
        "id", "title", "author", "current_score"
    ).first()

    most_commented = base_qs.order_by("-current_comments").values(
        "id", "title", "author", "current_comments").first()

    top_posts = list(
        base_qs.annotate(
            engagement=F("current_score") + F("current_comments")
        )
        .order_by("-engagement")
        .values("id", "title", "author", "engagement")[:50]
    )

    # ---------- USER LEVEL ----------
    top_users = list(
        base_qs.values("author")
        .annotate(
            posts=Count("id"),
            total_score=Sum("current_score")
        )
        .order_by("-total_score")[:50]
    )

    # ---------- DOMAIN / SUBREDDIT ----------
    # top_domains = list(
    #     base_qs.values("domain")
    #     .annotate(count=Count("id"))
    #     .order_by("-count")[:10]
    # )

    top_subreddits = list(
        base_qs.values("subreddit__name")
        .annotate(count=Count("id"))
        .order_by("-count")[:20]
    )

    return Response({
        "range": {"start": start, "end": end},
        "overview": overview,
        "posts": {
            "most_upvoted": most_upvoted,
            "most_commented": most_commented,
            "top_posts": top_posts,
        },
        "users": top_users,
        # "domains": top_domains,
        "subreddits": top_subreddits,
    })


class TrendViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = KeywordTrend.objects.all().order_by("-score")
    serializer_class = KeywordTrendSerializer


class StatsViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = SubredditStats.objects.all().order_by("-date")
    serializer_class = SubredditStatsSerializer


