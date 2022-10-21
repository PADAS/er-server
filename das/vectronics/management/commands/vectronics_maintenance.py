import logging

from django.core.management.base import BaseCommand

from vectronics.database_listener import handle_gps_plus_position
from vectronics.models import GpsPlusPositions


class Command(BaseCommand):
    help = 'Run vectronics maintenance.'

    def add_arguments(self, parser):
        parser.add_argument('--id-position', type=str,
                            help='position primary key to import')

    def handle(self, *args, **options):

        self.logger = logging.getLogger(__class__.__name__)

        position_key = options['id_position']
        if not position_key:
            raise ValueError('Missing position key')

        position = GpsPlusPositions.objects.get(pk=position_key)

        handle_gps_plus_position(position)
