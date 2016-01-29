from django.core.management.base import BaseCommand
from tracking.tasks import adhoc

class Command(BaseCommand):

    help = ''

    def handle(self, *args, **options):
        adhoc.add()
