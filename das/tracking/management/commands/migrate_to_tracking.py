from django.core.management.base import BaseCommand
from tracking.tools.migrate_dips_to_tracking import migrate

class Command(BaseCommand):

    help = ''

    def handle(self, *args, **options):
        migrate()
