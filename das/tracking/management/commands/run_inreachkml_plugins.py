from django.core.management.base import BaseCommand

from tracking.tasks import run_inreachkml_plugins
from utils.tenant.commands import TenantCommandMixin


class Command(TenantCommandMixin, BaseCommand):
    help = "Run all Inreach KML plugins."

    def handle(self, *args, **options):
        run_inreachkml_plugins()
