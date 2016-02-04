from django.core.management.base import BaseCommand
from analyzers.tasks import handle_source

class Command(BaseCommand):

    help = 'Run analyzers for the given source_id.'

    def handle(self, *args, **options):
        for source_id in options['source_id']:
            print("Running analyzers for source_id {}".format(source_id))
            handle_source(str(source_id))

    def add_arguments(self, parser):
        parser.add_argument('source_id', nargs='+', type=str, help='source_id for which to run analyzers.')
