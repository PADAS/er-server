from django.core.management.base import BaseCommand
from activity.alerts import create_alerts_permissionset


class Command(BaseCommand):

    help = 'Create alert rule permissions and permission sets.'

    def handle(self, *args, **options):
        create_alerts_permissionset()
