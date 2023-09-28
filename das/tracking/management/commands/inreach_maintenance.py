from django.core.management.base import BaseCommand

from tracking.models import InreachPlugin
from utils.tenant.commands import TenantCommandMixin


class Command(TenantCommandMixin, BaseCommand):
    help = "Run plugin maintenance."

    def handle(self, *args, **options):
        sk = InreachPlugin.objects.all()

        for p in sk:
            p._maintenance()
