from django.core.management.base import BaseCommand

from tracking.models import AWETelemetryPlugin
from utils.tenant.commands import TenantCommandMixin


class Command(TenantCommandMixin, BaseCommand):
    help = "Run plugin maintenance."

    def handle(self, *args, **options):

        sk = AWETelemetryPlugin.objects.all()

        for p in sk:
            p._maintenance()

            p.execute()
