from django.conf import settings
from django.core.management.base import BaseCommand
from ste import importer


class Command(BaseCommand):

    help = 'Import STE database into DAS'

    if not hasattr(settings, 'DATABASES') or 'animaltracking' not in settings.DATABASES:
        raise ConnectionError('Connection information for vectronics database not specified')

    def handle(self, *args, **options):
        importer.import_all()