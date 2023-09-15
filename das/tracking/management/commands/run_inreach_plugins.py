from tracking.tasks import run_inreach_plugins
from utils.tenant.commands import TenantBaseCommand


class Command(TenantBaseCommand):
    help = "Run all the Demo plugins ENABLED."

    def handle(self, *args, **options):
        run_inreach_plugins()
