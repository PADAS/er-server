from django.contrib.auth.management.commands.changepassword import (
    Command as ChangePassword,
)

from utils.tenant.commands import TenantCommandMixin


class Command(TenantCommandMixin, ChangePassword):
    pass
