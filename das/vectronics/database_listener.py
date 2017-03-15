import datetime
import logging
import psycopg2.extensions
import select
import pytz

from django.db import connections
from observations.models import Source, Observation, SourceProvider, Subject
from vectronics.models import GpsPlusPositions
from tracking.models.plugin_base import Obs

logger = logging.getLogger('vectronics_db_listener')
channel_name = 'das_vectronics_position_notification'
source_type = 'tracking-device'
SOURCE_PROVIDER_NAME = 'vectronics'

def start_listening():

    def handle(*args):
        position = GpsPlusPositions.objects.get(pk=args[0].payload)

        # if position.latitude is None or position.longitude is None:
        #     logger.debug('GpsPlusPosition has null location, so ignoring it. %s', position)
        #     return

        logger.debug('GpsPlusPosition reported for collar: %s at %s, location: lon/lat %s, %s',
                     position.id_collar, position.acquisition_time.isoformat(), position.longitude, position.latitude)

        provider, created = SourceProvider.objects.get_or_create(name=SOURCE_PROVIDER_NAME)

        manufacturer_id = position.id_collar
        source = Source.objects.ensure_source(source_type=source_type,
                                              provider=provider.name,
                                              manufacturer_id=manufacturer_id,
                                              model_name='vectronics',
                                              subject={
                                                  'subject_type': Subject.TYPE_UNASSIGNED,
                                                  'subject_subtype': Subject.SUBTYPE_UNASSIGNED,
                                                  'name': manufacturer_id
                                              }
                                              )

        logger.debug('{} source ({}) for collar_id: {}'.format('Created' if created else 'Found', source.id,
                                                               position.id_collar))

        additional = dict((k, v) for k, v in position if not k.startswith('_') and v is not None and
                          k not in ('id_collar', 'latitude', 'longitude', 'acquisition_time'))

        for key in [k for k, v in additional.items() if isinstance(v, datetime.datetime)]:
            additional[key] = additional[key].isoformat()

        # Guard against null position data.
        latitude = position.latitude or 0.0
        longitude = position.longitude or 0.0

        # Note the null position in additional.
        if position.latitude is None or position.longitude is None:
            additional['null_position'] = True

        # Vectronics database stores a naive date that we can assume is UTC.
        recorded_at = pytz.utc.localize(position.acquisition_time)
        observation = Obs(source=source, recorded_at=recorded_at, latitude=latitude,
                          longitude=longitude, additional=additional)

        try:
            Observation.objects.add_observation(observation)

            logger.debug('Recorded observation for collar_id: %s, at %s, longitude: %s, latitude: %s',
                         position.id_collar, recorded_at.isoformat(), position.longitude, position.latitude)
        except Exception:
            logger.exception('Failed observation for collar_id: %s, at %s, longitude: %s, latitude: %s',
                         position.id_collar, recorded_at.isoformat(), position.longitude, position.latitude)

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