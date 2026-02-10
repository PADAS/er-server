import logging

from django_multitenant.utils import get_current_tenant

from django.core.management.base import BaseCommand

from utils.cache import delete_tile_keys_by_prefix
from utils.tenant.commands import TenantCommandMixin

logger = logging.getLogger(__name__)


class Command(TenantCommandMixin, BaseCommand):
    help = (
        "Bust the vector tile cache for the current tenant. "
        "Deletes all cached tiles (subjects + segments) so the next "
        "request regenerates them from the database."
    )

    def handle(self, *args, **options):
        tenant = get_current_tenant()
        if not tenant:
            self.stderr.write(self.style.ERROR("No tenant set. Use --tenant_domain."))
            return

        tenant_id = str(tenant.id)
        prefix = f"vt:{tenant_id}:"

        try:
            deleted = delete_tile_keys_by_prefix(prefix)
            self.stdout.write(
                self.style.SUCCESS(
                    f"Deleted {deleted} cached vector tile entries for tenant {tenant.domain} ({tenant_id})."
                )
            )
        except Exception as e:
            logger.exception("Failed to bust vector tile cache for tenant %s", tenant_id)
            self.stderr.write(self.style.ERROR(f"Failed to bust vector tile cache: {e}"))
            raise
