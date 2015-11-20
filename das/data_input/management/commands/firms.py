from django.core.management.base import BaseCommand
from data_input import jobs
class Command(BaseCommand):

    help = 'Run Firms ingester.'

    def handle(self, *args, **options):
        jobs.run_firms()
