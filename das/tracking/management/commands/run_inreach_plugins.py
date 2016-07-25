from django.core.management.base import BaseCommand
from tracking.tasks import run_inreach_plugins

class Command(BaseCommand):
    help = 'Run all the Demo plugins ENABLED.'
    def handle(self, *args, **options):
        run_inreach_plugins()
