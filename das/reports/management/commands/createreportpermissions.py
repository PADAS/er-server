from django.core.management.base import BaseCommand

from reports.distribution import create_report_permissionset


class Command(BaseCommand):

    help = 'Create report permissions and permission sets.'

    def handle(self, *args, **options):
        create_report_permissionset()
