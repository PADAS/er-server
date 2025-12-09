from django.core.management.base import BaseCommand

from utils.tenant.providers import refresh_tenants_cache


class Command(BaseCommand):
    help = "Clear and refresh the tenant cache from TMS API"

    def handle(self, *args, **options):
        self.stdout.write("Clearing and refreshing tenant cache...")

        try:
            refresh_tenants_cache()
            self.stdout.write(self.style.SUCCESS("Successfully cleared and refreshed tenant cache from TMS API"))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Failed to refresh tenant cache: {e}"))
            raise
