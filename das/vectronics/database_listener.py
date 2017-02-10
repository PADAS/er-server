import datetime
import logging
import psycopg2.extensions
import select

from django.db import connections
from observations.models import Source, Observation, SourceProvider
from vectronics.models import GpsPlusPositions
from tracking.models.plugin_base import Obs

logger = logging.getLogger('vectronics_db_listener')
channel_name = 'das_vectronics_position_notification'
source_type = 'tracking-device'

def start_listening():

    def handle(*args):
        position = GpsPlusPositions.objects.get(pk=args[0].payload)
        provider, created = SourceProvider.objects.get_or_create(name='vectronics')
        source, created = Source.objects.ensure_source(source_type=source_type,
                                                       manufacturer_id=position.id_collar,
                                                       model_name='vectronics',
                                                       provider_name=provider.name)

        additional = dict((k, v) for k, v in position if not k.startswith('_') and v is not None and
                          k not in ('id_collar', 'latitude', 'longitude', 'acquisition_time'))

        for key in [k for k, v in additional.items() if isinstance(v, datetime.datetime)]:
            additional[key] = additional[key].isoformat()

        observation = Obs(source=source, recorded_at=position.acquisition_time.isoformat(), latitude=position.latitude,
                          longitude=position.longitude, additional=additional)

        Observation.objects.add_observation(observation)

    cursor = connections['vectronics'].cursor()
    db_connection = connections['vectronics'].connection
    db_connection.set_isolation_level(psycopg2.extensions.ISOLATION_LEVEL_AUTOCOMMIT)
    cursor.execute('LISTEN ' + channel_name + ';')

    print('Waiting for notifications: ' + channel_name)

    while 1:
        if select.select([db_connection], [], [], 5) != ([], [], []):
            db_connection.poll()
            while db_connection.notifies:
                notify = db_connection.notifies.pop(0)
                handle(notify)