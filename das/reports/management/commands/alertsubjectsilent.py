from django.core.management.base import BaseCommand

from reports.tasks import run_silent_source_report


class Command(BaseCommand):

    help = 'Report any Sources having no observations recorded within a configured threshold.'

    def handle(self, *args, **options):
        run_silent_source_report()

    def add_arguments(self, parser):
        pass
