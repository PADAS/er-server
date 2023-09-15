from tracking.tasks import run_plugins
from utils.tenant.commands import TenantBaseCommand


class Command(TenantBaseCommand):
    help = "Run all the SourcePlugins that are ENABLED."

    def add_arguments(self, parser):
        parser.add_argument("source_id", nargs="*", type=str)

    def handle(self, *args, **options):
        run_plugins()
