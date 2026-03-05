from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from rest_framework.authtoken.models import Token

User = get_user_model()


class Command(BaseCommand):
    help = "为指定用户生成或刷新 API Token"

    def add_arguments(self, parser):
        parser.add_argument("username", type=str, help="用户名")

    def handle(self, *args, **options):
        username = options["username"]
        try:
            user = User.objects.get(username=username)
            token, created = Token.objects.update_or_create(user=user)
            if created:
                self.stdout.write(self.style.SUCCESS(f"Token created for {username}: {token.key}"))
            else:
                self.stdout.write(self.style.WARNING(f"Token refreshed for {username}: {token.key}"))
        except User.DoesNotExist:
            self.stderr.write(self.style.ERROR(f"User {username} does not exist"))
