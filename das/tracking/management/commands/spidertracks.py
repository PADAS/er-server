from django.core.management.base import BaseCommand
from tracking.tasks import run_spidertacks_plugin

class Command(BaseCommand):
    help = 'Run plugin maintenance.'
    def handle(self, *args, **options):
        run_spidertacks_plugin()


