import logging

from django.core.management.base import BaseCommand

from utils.tenant.providers import refresh_tenants_cache

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Clear and refresh the tenant cache by fetching updated data from TMS"

    def add_arguments(self, parser):
        parser.add_argument(
            "--force",
            action="store_true",
            help="Force refresh even if cache is not empty",
        )

    def handle(self, *args, **options):
        self.stdout.write("Starting tenant cache refresh...")

        try:
            refresh_tenants_cache()
            self.stdout.write(
                self.style.SUCCESS(
                    "Successfully refreshed tenant cache. All sites will now pick up the latest "
                    "tenant settings and feature flags from TMS."
                )
            )
        except Exception as e:
            logger.exception("Failed to refresh tenant cache: %s", str(e))
            self.stdout.write(self.style.ERROR(f"Failed to refresh tenant cache: {e}"))
            raise
