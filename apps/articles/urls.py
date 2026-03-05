from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    AdminArticleViewSet,
    AdminCategoryViewSet,
    AdminCollectionViewSet,
    AdminCommentViewSet,
    AdminDashboardSummaryAPIView,
    AdminMediaDirectoryTreeAPIView,
    AdminMediaListAPIView,
    AdminMediaRenameAPIView,
    AdminMediaUploadAPIView,
    CategoryViewSet,
    HomeRecommendationsAPIView,
    HomeSummaryAPIView,
    PublicArticleViewSet,
    PublicCollectionViewSet,
    PublicImageProxyAPIView,
)

public_router = DefaultRouter()
public_router.register(r"articles", PublicArticleViewSet, basename="public-article")
public_router.register(r"categories", CategoryViewSet, basename="category")
public_router.register(r"collections", PublicCollectionViewSet, basename="collection")

admin_router = DefaultRouter()
admin_router.register(r"admin/articles", AdminArticleViewSet, basename="admin-article")
admin_router.register(r"admin/collections", AdminCollectionViewSet, basename="admin-collection")
admin_router.register(r"admin/categories", AdminCategoryViewSet, basename="admin-category")
admin_router.register(r"admin/comments", AdminCommentViewSet, basename="admin-comment")

urlpatterns = [
    path("home/summary/", HomeSummaryAPIView.as_view(), name="home-summary"),
    path("home/recommendations/", HomeRecommendationsAPIView.as_view(), name="home-recommendations"),
    path("image-proxy/", PublicImageProxyAPIView.as_view(), name="public-image-proxy"),
    path("admin/dashboard/summary/", AdminDashboardSummaryAPIView.as_view(), name="admin-dashboard-summary"),
    path("admin/media/", AdminMediaListAPIView.as_view(), name="admin-media-list"),
    path("admin/media/tree/", AdminMediaDirectoryTreeAPIView.as_view(), name="admin-media-tree"),
    path("admin/media/upload/", AdminMediaUploadAPIView.as_view(), name="admin-media-upload"),
    path("admin/media/rename/", AdminMediaRenameAPIView.as_view(), name="admin-media-rename"),
    path("", include(public_router.urls)),
    path("", include(admin_router.urls)),
]
