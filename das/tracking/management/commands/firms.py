from django.core.management.base import BaseCommand

from tracking.models import FirmsPlugin
from utils.tenant.commands import TenantCommandMixin


class Command(TenantCommandMixin, BaseCommand):
    help = "Run FIRMS plugins"

    def handle(self, *args, **options):

        plugins = FirmsPlugin.objects.all()

        for p in plugins:
            p.execute()
