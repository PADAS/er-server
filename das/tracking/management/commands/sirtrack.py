from django.core.management.base import BaseCommand

from tracking.tasks import run_sirtrack_plugins
from utils.tenant.commands import TenantCommandMixin


class Command(TenantCommandMixin, BaseCommand):
    help = "Run SirTrack plugins"

    def handle(self, *args, **options):
        run_sirtrack_plugins()
