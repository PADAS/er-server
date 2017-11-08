from django.core.management.base import BaseCommand

from reports.tasks import subjectsource_report


class Command(BaseCommand):

    def handle(self, *args, **options):

        subjectsource_report()
