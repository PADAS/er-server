from django.conf import settings
from django.core.management.base import BaseCommand
from vectronics import database_listener


class Command(BaseCommand):

    help = 'Start vectronics database listener'

    if not hasattr(settings, 'DATABASES') or 'vectronics' not in settings.DATABASES:
        raise ConnectionError('Connection information for vectronics database not specified')

    def handle(self, *args, **options):
        database_listener.start_listening()
