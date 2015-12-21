from django.core.management.base import BaseCommand
from data_input import tasks
class Command(BaseCommand):

    help = 'Run Inreach import job for a given source_id.'

    def handle(self, *args, **options):
        tasks.run_inreach.delay()
