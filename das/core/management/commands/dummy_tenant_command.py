from utils.tenant.commands import TenantBaseCommand


class Command(TenantBaseCommand):
    help = "Dummy tenant-aware command"

    def handle(self, *args, **options):
        self.stdout.write("dummy tenant-aware command executed.")
