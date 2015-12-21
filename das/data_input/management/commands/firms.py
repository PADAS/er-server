from django.core.management.base import BaseCommand
from data_input import tasks
class Command(BaseCommand):

    help = 'Run Firms ingester.'

    def handle(self, *args, **options):
        tasks.run_firms.delay()
