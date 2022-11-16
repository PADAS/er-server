from django.core.management.base import BaseCommand

from tracking.tasks import run_plugins
from utils.tenant.commands import TenantCommandMixin


class Command(TenantCommandMixin, BaseCommand):
    help = "Run all the SourcePlugins that are ENABLED."

    def add_arguments(self, parser):
        parser.add_argument("source_id", nargs="*", type=str)

    def handle(self, *args, **options):
        run_plugins()
