
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import home, TrendViewSet,PostViewSet, CommentViewSet, StatsViewSet
from .views import stats

router = DefaultRouter()
# router.register(r"posts", PostViewSet)

router.register(r"posts", PostViewSet, basename="post")
router.register(r"comments", CommentViewSet)
router.register(r"trends", TrendViewSet)
#router.register(r"stats", StatsViewSet)

urlpatterns = [
    path("", home),
    path("", include(router.urls)),
    path("stats/", stats, name="stats"),
]
