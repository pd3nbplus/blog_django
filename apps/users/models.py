from django.conf import settings
from django.db import models


class UserSiteSettings(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, related_name="site_settings", on_delete=models.CASCADE)
    home_avatar_path = models.CharField(max_length=255, blank=True, default="")
    home_hero_path = models.CharField(max_length=255, blank=True, default="")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "users_site_settings"
        verbose_name = "用户站点展示设置"
        verbose_name_plural = "用户站点展示设置"

    def __str__(self) -> str:
        return f"SiteSettings(user={self.user_id})"
