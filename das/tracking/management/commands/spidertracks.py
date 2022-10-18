from django.core.management.base import BaseCommand

from tracking.tasks import run_spidertracks_plugins
from utils.tenant.commands import TenantCommandMixin


class Command(TenantCommandMixin, BaseCommand):
    help = "Run plugin maintenance."

    def handle(self, *args, **options):
        run_spidertracks_plugins()
