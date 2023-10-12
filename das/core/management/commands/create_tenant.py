from django.core.management.base import BaseCommand, CommandError

from core.models import DASTenant
from utils.tenant.managers import UnsetDASTenantContextManager
from utils.tenant.providers import TenantData


class Command(BaseCommand):
    help = "Helps to create the first DAS tenant."

    def create_parser(self, prog_name, subcommand, **kwargs):
        parser = super().create_parser(prog_name, subcommand, **kwargs)
        parser.add_argument("tenant_domain", type=str, help="Specify the tenant domain")
        return parser

    def handle(self, *args, **options):
        domain = options.get("tenant_domain")

        tenant_data = self._get_tenant_data(domain)
        tenant_id = tenant_data["id"]
        domain = tenant_data["domain"]

        try:
            with UnsetDASTenantContextManager():
                obj, created = DASTenant.objects.get_or_create(id=tenant_id, domain=domain)
            if created:
                self.stdout.write(self.style.SUCCESS("Tenant for domain '%s' created successfully" % domain))
        except DASTenant.DoesNotExist:
            raise CommandError("Error creating DAS tenant object")

    def _get_tenant_data(self, domain):
        instance = TenantData(domain=domain)
        return instance.get_tenant_data()
