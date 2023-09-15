from tracking.models import InreachPlugin
from utils.tenant.commands import TenantBaseCommand


class Command(TenantBaseCommand):
    help = "Run plugin maintenance."

    def handle(self, *args, **options):
        sk = InreachPlugin.objects.all()

        for p in sk:
            p._maintenance()
