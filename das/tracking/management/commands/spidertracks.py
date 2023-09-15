from tracking.tasks import run_spidertracks_plugins
from utils.tenant.commands import TenantBaseCommand


class Command(TenantBaseCommand):
    help = "Run plugin maintenance."

    def handle(self, *args, **options):
        run_spidertracks_plugins()
