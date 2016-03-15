from django.core.management.base import BaseCommand
from tracking.tasks import run_all_source_plugins, run_source_plugin_for_source

class Command(BaseCommand):

    help = 'Run all the SourcePlugins that are ENABLED.'

    def add_arguments(self, parser):
        parser.add_argument('source_id', nargs='+', type=str)

    def handle(self, *args, **options):

        try:
            source_ids = options['source_id']
        except KeyError:
            source_ids = None

        if source_ids:
            for source_id in source_ids:
                run_source_plugin_for_source(source_id)
        else:
            run_all_source_plugins()
