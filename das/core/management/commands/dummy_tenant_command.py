from django_multitenant.utils import get_current_tenant

from django.core.management.base import BaseCommand

from utils.tenant import get_tenant_settings
from utils.tenant.commands import TenantCommandMixin


class Command(TenantCommandMixin, BaseCommand):
    help = "Dummy tenant-aware command"

    def handle(self, *args, **options):
        if options.get("verbosity", 0) >= 2:
            self.stdout.write(f"tenant model instance (DASTenant) from thread locals: {get_current_tenant()}")
            self.stdout.write(f"tenant settings (Tenant) from thread locals: {get_tenant_settings()}")
        self.stdout.write("dummy tenant-aware command executed.")
