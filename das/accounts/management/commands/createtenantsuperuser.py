from django.contrib.auth.management.commands.createsuperuser import (
    Command as CreateSuperuserCommand,
)

from utils.tenant.commands import TenantCommandMixin


class Command(TenantCommandMixin, CreateSuperuserCommand):
    pass
