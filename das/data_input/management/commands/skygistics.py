from django.core.management.base import BaseCommand
from data_input import tasks
class Command(BaseCommand):

    help = 'Run Skygistics import job for a given source_id.'

    def handle(self, *args, **options):
        tasks.run_skygistics.delay()
