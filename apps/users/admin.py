from django.contrib import admin

from .models import UserSiteSettings


@admin.register(UserSiteSettings)
class UserSiteSettingsAdmin(admin.ModelAdmin):
    list_display = ("user", "home_avatar_path", "home_hero_path", "updated_at")
    search_fields = ("user__username", "home_avatar_path", "home_hero_path")
