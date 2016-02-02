from django.core.management.base import BaseCommand
from tracking.tasks import run_all_source_plugins

class Command(BaseCommand):

    help = 'Run all the SourcePlugins that are ENABLED.'

    def handle(self, *args, **options):
        run_all_source_plugins()
