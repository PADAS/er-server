import datetime
import logging
import psycopg2
import psycopg2.extensions
import select
import pytz

from django.db import connections
from observations.models import Source, Observation, SourceProvider, Subject
from vectronics.models import GpsPlusPositions
from tracking.models.plugin_base import Obs
from tracking.pubsub_registry import notify_new_tracks


logger = logging.getLogger('vectronics_db_listener')
channel_name = 'das_vectronics_position_notification'
SOURCE_TYPE = 'tracking-device'
MODEL_NAME = 'vectronics'
SOURCE_PROVIDER_KEY = 'default'


def handle_notify(notify):

    try:
        print('Handling notify...')
        logger.info('Handling notify...')
        position = GpsPlusPositions.objects.get(pk=notify.payload)
        handle_gps_plus_position(position)
    except GpsPlusPositions.DoesNotExist:
        logger.warning(
            'Notified for id_position: %s, but it does not exist in the database.', notify.payload)


def handle_gps_plus_position(position):
    logger.info('GpsPlusPosition (%s) reported for collar: %s at %s, location: lon/lat %s, %s',
                position.id_position,
                position.id_collar, position.acquisition_time.isoformat(), position.longitude, position.latitude)

    provider, created = SourceProvider.objects.get_or_create(
        provider_key=SOURCE_PROVIDER_KEY)
    manufacturer_id = position.id_collar
    source = Source.objects.ensure_source(source_type=SOURCE_TYPE,
                                          manufacturer_id=position.id_collar,
                                          model_name=MODEL_NAME,
                                          provider=provider.provider_key,
                                          subject={
                                              'subject_subtype_id': 'unassigned',
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
        observation, created = Observation.objects.add_observation(observation)

        if created:
            notify_new_tracks(observation.source.id)

        logger.info('Recorded observation for collar_id: %s, at %s, longitude: %s, latitude: %s',
                    position.id_collar, recorded_at.isoformat(), position.longitude, position.latitude)
    except Exception:
        logger.exception('Failed observation for collar_id: %s, at %s, longitude: %s, latitude: %s',
                         position.id_collar, recorded_at.isoformat(), position.longitude, position.latitude)


def start_listening():

    cursor = connections['vectronics'].cursor()
    db_connection = connections['vectronics'].connection
    db_connection.set_isolation_level(
        psycopg2.extensions.ISOLATION_LEVEL_AUTOCOMMIT)
    cursor.execute('LISTEN ' + channel_name + ';')

    msg = 'Waiting for notifications: ' + channel_name
    print(msg)
    logger.info(msg)

    while True:
        try:
            if select.select([db_connection], [], [], 5) != ([], [], []):
                db_connection.poll()
                while db_connection.notifies:
                    notify = db_connection.notifies.pop(0)
                    handle_notify(notify)
        except psycopg2.OperationalError as oe:
            logger.exception('Caught exception in select loop.')
