from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from core import tms_api_client
from core.models import DASTenant


class Command(BaseCommand):
    help = "Helps to create the first DAS tenant."

    def handle(self, *args, **options):
        tenant_data = self._get_tenant_data()
        tenant_id = tenant_data["id"]
        domain = tenant_data["domain"]

        try:
            obj, created = DASTenant.objects.get_or_create(id=tenant_id, domain=domain)
            if created:
                self.stdout.write(self.style.SUCCESS("Tenant for domain '%s' created successfully" % domain))
        except DASTenant.DoesNotExist:
            raise CommandError("Error creating DAS tenant object")

    def _get_tenant_data(self):
        domain = settings.SERVER_FQDN
        return tms_api_client.get_tenant_data(domain=domain)
