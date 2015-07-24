"""Migrate some data from the AnimalTracking db to the DasDB

To your local_settings add this DATABASES configuration for the AT db

'animaltracking': {
        'ENGINE': 'django.db.backends.postgresql_psycopg2',
        'NAME': 'AnimalTracking',
        'USER': 'postgres',
        'HOST': 'at-db.cuts0lhpybwu.us-west-2.rds.amazonaws.com',
        'PASSWORD': '',
    },

"""
import os
import sys
import logging
import datetime
DAS_ROOT = '../das'
sys.path.append(os.path.join(os.path.dirname(__file__), DAS_ROOT))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "das_server.local_settings")
from django.db import connections
from sensors import models
from django.contrib.gis.geos import Point
import pytz
import django
import psycopg2.extras

logger = logging.getLogger(__name__)

def log_stdout(level=logging.DEBUG):
    soh = logging.StreamHandler(sys.stdout)
    soh.setLevel(level)
    logger = logging.getLogger()
    logger.addHandler(soh)
    logger.setLevel(level)

log_stdout(level=logging.INFO)


def dictfetchall(cursor):
    "Returns all rows from a cursor as a dict"
    desc = cursor.description
    return [
        dict(zip([col[0] for col in desc], row))
        for row in cursor.fetchall()
    ]

TRACKING_MASTER_ANIMAL_FIELDS = ('animal_id', 'comments', 'chronofile' 'species', 'rgb', 'sex', 'gmt',)
TRACKING_MASTER_VEHICLE_FIELDS = ('animal_id', 'comments', 'chronofile' 'species', 'rgb', 'gmt',)
TRACKING_MASTER_DEVICE_FIELDS = ('active', 'frequency', 'predicted_expiry',)
ARCHIVE_LOC_FIELDS = ('dloadtime',)
TRACKING_COLLAR_DEVICE_CATEGORY = 'gps'

def import_animal(chronofile):
    logger.info('Importing TrackingMaster %s', chronofile)
    at_conn = connections['animaltracking']
    with at_conn.cursor() as at_cursor:
        sql = 'SELECT * from trackingmaster WHERE chronofile=%(chronofile)s'
        at_cursor.execute(sql, dict(chronofile=chronofile))
        rows = dictfetchall(at_cursor)
    animal = rows[0]

    if animal['date_off_or_removed'] == 'Undeployed' or not animal['data_starts']:
        logger.info('TrackingMaster for %s, Undeployed', chronofile)
        return

    additional = {key: animal[key] for key in TRACKING_MASTER_ANIMAL_FIELDS if key in animal }
    subject = models.Subject(name=animal['name'], additional=additional)
    subject.save()

    q_types = models.DeviceType.objects.filter(name=animal['collar_type'])
    device_type = None
    for row in q_types:
        device_type = row
    if not device_type:
        device_type = models.DeviceType(name=animal['collar_type'],
                                        categories=[TRACKING_COLLAR_DEVICE_CATEGORY,])
        device_type.save()

    device = None
    q_devices = models.Device.objects.filter(device_type=device_type)
    q_devices = q_devices.filter(manufacturer_id=animal['collar_id'])
    for row in q_devices:
        device = row
    if not device:
        additional = {key: animal[key] for key in TRACKING_MASTER_DEVICE_FIELDS if key in animal }
        device = models.Device(device_type=device_type,
                               manufacturer_id=animal['collar_id'],
                               additional=additional
                               )
        device.save()

    subject_device = models.SubjectDevice(subject=subject, device=device)
    start_at = animal['data_starts'].replace(tzinfo=pytz.UTC)
    end_at = datetime.datetime.max.replace(tzinfo=pytz.UTC)
    if animal['data_stops']:
        end_at = animal['data_stops'].replace(tzinfo=pytz.UTC)

    if end_at < start_at:
        end_at = datetime.datetime.max.replace(tzinfo=pytz.UTC)

    subject_device.assigned_range = psycopg2.extras.DateTimeTZRange(start_at, end_at)
    subject_device.save()


    with at_conn.cursor() as at_cursor:
        sql = 'SELECT * from archive_loc WHERE chronofile=%(chronofile)s'
        at_cursor.execute(sql, dict(chronofile=chronofile))
        rows = dictfetchall(at_cursor)

    observations = rows
    for row in observations:
        additional = {key: row[key] for key in ARCHIVE_LOC_FIELDS}
        obs = models.Observation(device=device,
                                 location=Point(row['lat'], row['lon']),
                                 recorded_at=row['fixtime'].replace(tzinfo=pytz.UTC),
                                 additional=additional)

        obs.save()


def import_all():
    at_conn = connections['animaltracking']
    with at_conn.cursor() as at_cursor:
        sql = 'SELECT chronofile from trackingmaster'
        at_cursor.execute(sql)
        rows = dictfetchall(at_cursor)
    for animal in rows:
        try:
            import_animal(animal['chronofile'])
        except:
            logging.exception('Failed to import TrackingMaster %s', animal['chronofile'])



def main():
    import_all()
    return

    import_animal(558)
    import_animal(557)
    import_animal(546)
    import_animal(533)


if __name__ == '__main__':
    django.setup()
    main()
