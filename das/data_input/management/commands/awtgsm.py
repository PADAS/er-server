from django.core.management.base import BaseCommand
from data_input import tasks

class Command(BaseCommand):

    help = 'Run AWT HTTP import job for a given source_id.'

    def handle(self, *args, **options):
        tasks.run_awt_http.delay()
