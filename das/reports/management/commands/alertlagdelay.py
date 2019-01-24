from django.core.management.base import BaseCommand

from reports.tasks import alert_lag_delay


class Command(BaseCommand):

    help = 'Alert if a Source Provider\'s average obvservation lag exceeds a its configured threshold.'

    def handle(self, *args, **options):
        alert_lag_delay()

    def add_arguments(self, parser):
        pass
