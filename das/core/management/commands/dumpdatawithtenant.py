from django.core.management.commands.dumpdata import Command as DumpDataCommand

from utils.tenant.commands import TenantCommandMixin


class Command(TenantCommandMixin, DumpDataCommand):
    pass
