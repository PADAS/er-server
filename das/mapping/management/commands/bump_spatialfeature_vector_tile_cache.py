import logging

from django.core.management.base import BaseCommand

from mapping.cache import bump_vector_tile_data_version
from utils.tenant.commands import TenantCommandMixin

logger = logging.getLogger(__name__)


class Command(TenantCommandMixin, BaseCommand):
    help = "Bump the vector tile cache version to invalidate all cached vector tiles"

    def handle(self, *args, **options):
        try:
            bump_vector_tile_data_version()
            self.stdout.write(
                self.style.SUCCESS(
                    "Vector tile cache version bumped successfully. All cached vector tiles will be regenerated."
                )
            )
        except Exception as e:
            logger.exception("Failed to bump vector tile cache version: %s")
            self.stdout.write(self.style.ERROR(f"Failed to bump vector tile cache version: {e}"))
            raise
