from django_multitenant.utils import get_current_tenant, set_current_tenant

from django.core.management.base import CommandError

from core.models import DASTenant
from utils.features import features
from utils.tenant import get_tenant_settings
from utils.tenant.exceptions import (
    TenantNotFoundException,
    TenantNotFoundInLocalThreadException,
)
from utils.tenant.managers import UnsetDASTenantContextManager, set_tenant
from utils.tenant.providers import post_tenant_to_thread


class TenantCommandMixin:
    """
    Mixin for tenant-aware Django commands.
    This class has to be mixed in Custom Django commands.

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
                try:
                    set_tenant(domain=domain)
                except Exception as e:
                    raise CommandError(f"Error setting tenant for domain {domain}: {e}")
            else:
                try:
                    tenant_settings = get_tenant_settings()
                except TenantNotFoundInLocalThreadException:
                    das_tenant = get_current_tenant()
                    if das_tenant:
                        self._set_tenant_settings(domain=das_tenant.domain)
                    else:
                        raise CommandError(
                            "Please either specify a tenant with '--tenant_domain' or set the tenant in the current thread"
                        )
                else:
                    self._set_das_tenant(tenant_id=tenant_settings.id)
            # Verbose mode
            if options.get("verbosity", 0) >= 2:
                current_tenant_settings = get_tenant_settings()
                self.stdout.write(f"Executing command with tenant id {current_tenant_settings.id}...")
        super().execute(*args, **options)

    def _set_tenant_settings(self, domain):
        try:
            post_tenant_to_thread(domain=domain)
        except TenantNotFoundException:
            raise CommandError(f"Tenant settings for domain '{domain}' not found.")
        except Exception as e:
            raise CommandError(f"Error resolving tenant settings with domain '{domain}': {e}")

    def _set_das_tenant(self, tenant_id):
        try:
            with UnsetDASTenantContextManager():
                tenant = DASTenant.objects.get(id=tenant_id)
                set_current_tenant(tenant=tenant)
        except DASTenant.DoesNotExist:
            raise CommandError(f"Tenant with id '{tenant_id}' not found.")
        except Exception as e:
            raise CommandError(f"Error resolving tenant with id '{tenant_id}': {e}")
