from django.conf import settings
from django.core.management import BaseCommand

from accounts.models import PermissionSet


class Command(BaseCommand):
    help = "remove users from_wrong permission set view tracks last 16 days delayed"

    def handle(self, *args, **options):
        User = settings.AUTH_USER_MODEL

        try:
            wrong_permission = PermissionSet.objects.get(name="View Tracks Last 16 Days Delayed")
        except PermissionSet.DoesNotExist:
            return

        for user in User.objects.filter(permission_sets=wrong_permission):
            user.permission_sets.remove(wrong_permission)
