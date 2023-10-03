from django_multitenant.utils import set_current_tenant

from django.core.management.base import CommandError

from core.models import DASTenant
from utils.features import features
from utils.tenant.exceptions import TenantNotFoundException
from utils.tenant.managers import UnsetDASTenantContextManager
from utils.tenant.providers import TenantData
from utils.tenant.thread import get_tenant_settings, set_tenant_settings


class TenantCommandMixin:
    """
    Mixin for tenant-aware Django commands.
    This class can be mixed in Custom Django commands.

    Tenant resolution:
        1. Look for the tenant specified by --tenant_id.
        2. Look if a tenant is already set in the current thread.

    By the time the handle method of the custom command subclass is called,
    the tenant instance and tenant settings are both set in the current thread

    Class usage example:
    ```
        # my_tenant_command.py
        from django.core.management.base import BaseCommand
        from utils.tenant.commands import TenantCommandMixin

        class Command(TenantCommandMixin, BaseCommand):
            help = "Perform some operation against one tenant's data"

            def add_arguments(self, parser):
                #  Add extra arguments as needed
                parser.add_argument(...)

            def handle(self, *args, **options):
                # Implement your custom command logic here as usual
                ...
    ```
    Command usage example
    ```
        python manage.py my_tenant_command --tenant_domain domain [-v] [other options]
    ```
    When verbose mode is set to 2 or greater, then extra tenant details are printed.
    """

    help = "Base command for tenant-aware commands"

    def create_parser(self, prog_name, subcommand, **kwargs):
        """
        Overriden to add tenant_domain argument for tenant-aware commands
        """
        parser = super().create_parser(prog_name, subcommand, **kwargs)
        if features.tms.is_on():
            parser.add_argument("--tenant_domain", type=str, help="Specify the tenant domain", required=False)
        return parser

    def execute(self, *args, **options):
        """
        Overriden to set the tenant instance and tenant settings for tenant-aware commands
        before the handle method is called.
        """
        if features.tms.is_on():
            domain = options.get("tenant_domain")
            if domain:
                tenant_settings = self._set_tenant_settings(domain=domain)
                tenant = self._set_tenant_instance(tenant_id=tenant_settings.get("id"))
            else:
                try:
                    tenant_settings = get_tenant_settings()
                    tenant = self._set_tenant_instance(tenant_id=tenant_settings.id)
                except TenantNotFoundInLocalThreadException:
                    raise CommandError(
                        "Please either specify a tenant with '--tenant_domain' or set the tenant in the current thread"
                    )
            # Verbose mode
            if options.get("verbosity", 0) >= 2:
                self.stdout.write(f"Executing command with tenant id {tenant.id}...")
        super().execute(*args, **options)

    def _set_tenant_settings(self, domain):
        try:
            tenant_data = TenantData(domain=domain)
            tenant_settings = tenant_data.get_tenant_data()
            set_tenant_settings(value=tenant_settings)
            return tenant_settings
        except TenantNotFoundException:
            raise CommandError(f"Tenant settings for domain '{domain}' not found.")
        except Exception as e:
            raise CommandError(f"Error resolving tenant settings with domain '{domain}': {e}")

    def _set_tenant_instance(self, tenant_id):
        try:
            with UnsetDASTenantContextManager():
                tenant = DASTenant.objects.get(domain=domain)

            set_current_tenant(tenant=tenant)
            return tenant
        except DASTenant.DoesNotExist:
            raise CommandError(f"Tenant with id '{tenant_id}' not found.")
        except Exception as e:
            raise CommandError(f"Error resolving tenant with id '{tenant_id}': {e}")
