from django_multitenant.utils import set_current_tenant

from django.core.management.base import BaseCommand, CommandError

from core.models import DASTenant

from ..features import features
from .exceptions import TenantNotFoundException
from .providers import TenantData
from .thread import set_tenant_settings


class TenantBaseCommand(BaseCommand):
    """
    Base class for tenant-aware commands.
    This class can be used as a drop-in replacement of the Django BaseCommand class.

    A mandatory argument --tenant_domain is added.

    Derived classes must implement handle(), and optionally add_arguments().
    By the time the handle method of the custom command subclass is called,
    the tenant instance and tenant settings are both set in the current thread

    Class usage example:
    ```
        # my_tenant_command.py
        from utils.tenant.commands import TenantBaseCommand

        class Command(TenantBaseCommand):
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
    When verbose mode is set to 2 or greater to get extra tenant details printed.
    """

    help = "Base command for tenant-aware commands"

    def _set_tenant_settings(self, domain):
        try:  # Get tenant settings from TMS/Cache/Django settings
            tenant_data = TenantData(domain=domain)
            tenant_settings = tenant_data.get()
        except TenantNotFoundException:
            raise CommandError(f"Tenant settings for domain '{domain}' not found.")
        except Exception as e:
            raise CommandError(f"Error getting tenant settings with domain '{domain}': {e}")
        else:
            set_tenant_settings(value=tenant_settings)
            return tenant_settings

    def _set_tenant_instance(self, domain):
        try:
            tenant = DASTenant.objects.get(domain=domain)
        except DASTenant.DoesNotExist:
            raise CommandError(f"Tenant for domain '{domain}' not found.")
        except Exception as e:
            raise CommandError(f"Error getting tenant with domain '{domain}': {e}")
        else:
            set_current_tenant(tenant=tenant)
            return tenant

    def create_parser(self, prog_name, subcommand, **kwargs):
        """
        Overriden to add tenant_domain as a mandatory argument for tenant-aware commands
        """
        parser = super().create_parser(prog_name, subcommand, **kwargs)
        if features.tms.is_on():
            parser.add_argument("--tenant_domain", type=str, help="Specify the tenant domain", required=True)
        return parser

    def execute(self, *args, **options):
        """
        Overriden to set the tenant instance and tenant settings for tenant-aware commands
        before the handle method is called.
        """
        if features.tms.is_on():
            domain = options.get("tenant_domain")
            tenant = self._set_tenant_instance(domain=domain)
            settings = self._set_tenant_settings(domain=domain)
            # Verbose mode
            if options.get("verbosity", 0) >= 2:
                self.stdout.write(f"Executing command with tenant id {tenant.id} and tenant settings {settings}..")
        super().execute(*args, **options)
