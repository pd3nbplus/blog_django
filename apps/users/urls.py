from django.urls import path

from .views import (
    AdminLogListAPIView,
    AdminPasswordAPIView,
    AdminProfileAPIView,
    LoginAPIView,
    LogoutAPIView,
    ProfileAPIView,
)

urlpatterns = [
    path("auth/login/", LoginAPIView.as_view(), name="api-login"),
    path("auth/logout/", LogoutAPIView.as_view(), name="api-logout"),
    path("auth/profile/", ProfileAPIView.as_view(), name="api-profile"),
    path("admin/profile/", AdminProfileAPIView.as_view(), name="api-admin-profile"),
    path("admin/profile/password/", AdminPasswordAPIView.as_view(), name="api-admin-password"),
    path("admin/logs/", AdminLogListAPIView.as_view(), name="api-admin-logs"),
]
