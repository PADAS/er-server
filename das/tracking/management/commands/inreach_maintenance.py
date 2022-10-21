from django.core.management.base import BaseCommand
from tracking.models import InreachPlugin

class Command(BaseCommand):
    help = 'Run plugin maintenance.'
    def handle(self, *args, **options):

        sk = InreachPlugin.objects.all()

        for p in sk:
            p._maintenance()


