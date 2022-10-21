from django.core.management.base import BaseCommand
from tracking.models import FirmsPlugin


class Command(BaseCommand):
    help = 'Run FIRMS plugins'

    def handle(self, *args, **options):

        plugins = FirmsPlugin.objects.all()

        for p in plugins:
            p.execute()
