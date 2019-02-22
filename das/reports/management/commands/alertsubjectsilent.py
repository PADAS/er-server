from django.core.management.base import BaseCommand

from reports.tasks import alert_subject_silent


class Command(BaseCommand):

    help = 'Alert if a Source Provider\'s average obvservation lag exceeds a its configured threshold.'

    def handle(self, *args, **options):
        alert_subject_silent()

    def add_arguments(self, parser):
        pass
