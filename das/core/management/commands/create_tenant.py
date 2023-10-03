from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from core.models import DASTenant
from utils.tenant.managers import UnsetDASTenantContextManager
from utils.tenant.providers import TenantData


class Command(BaseCommand):
    help = "Helps to create the first DAS tenant."

    def handle(self, *args, **options):
        tenant_data = self._get_tenant_data()
        tenant_id = tenant_data["id"]
        domain = tenant_data["domain"]

        try:
            with UnsetDASTenantContextManager():
                obj, created = DASTenant.objects.get_or_create(id=tenant_id, domain=domain)
            if created:
                self.stdout.write(self.style.SUCCESS("Tenant for domain '%s' created successfully" % domain))
        except DASTenant.DoesNotExist:
            raise CommandError("Error creating DAS tenant object")

    def _get_tenant_data(self):
        instance = TenantData(domain=settings.SERVER_FQDN)
        return instance.get_tenant_data()
