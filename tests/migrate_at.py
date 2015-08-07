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
from observations import models
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

TRACKING_MASTER_COMMON_FIELDS = ('comments', 'chronofile', 'rgb', 'gmt', 'utm')
TRACKING_MASTER_ANIMAL_FIELDS = ('species', 'sex')
TRACKING_MASTER_DEVICE_FIELDS = ('active', 'frequency', 'predicted_expiry',)
ARCHIVE_LOC_FIELDS = ('dloadtime',)
TRACKING_COLLAR_SOURCE_TYPE = 'tracking-device'

def import_trackingmaster(chronofile):
    logger.info('Importing TrackingMaster %s', chronofile)
    at_conn = connections['animaltracking']
    with at_conn.cursor() as at_cursor:
        sql = 'SELECT * from trackingmaster WHERE chronofile=%(chronofile)s'
        at_cursor.execute(sql, dict(chronofile=chronofile))
        rows = dictfetchall(at_cursor)
    trackingmaster = rows[0]

    if trackingmaster['date_off_or_removed'] == 'Undeployed' or not trackingmaster['data_starts']:
        logger.info('TrackingMaster for %s, Undeployed', chronofile)
        return

    additional = {key: trackingmaster[key] for key in TRACKING_MASTER_COMMON_FIELDS if key in trackingmaster}
    additional['external_id'] = trackingmaster['animal_id']
    subject_type = 'wildlife'
    if trackingmaster['species'].lower() == 'vehicle':
        subject_type = 'vehicle'
    else:
        additional.update({key: trackingmaster[key] for key in TRACKING_MASTER_ANIMAL_FIELDS if key in trackingmaster})
    subject = models.Subject(name=trackingmaster['name'],
                             subject_type=subject_type,
                             additional=additional)
    subject.save()

    source = None
    q_sources = models.Source.objects.filter(source_type=TRACKING_COLLAR_SOURCE_TYPE)
    q_sources = q_sources.filter(manufacturer_id=trackingmaster['collar_id'])
    for row in q_sources:
        source = row
    if not source:
        additional = {key: trackingmaster[key] for key in TRACKING_MASTER_DEVICE_FIELDS if key in trackingmaster}
        source = models.Source(source_type=TRACKING_COLLAR_SOURCE_TYPE,
                               manufacturer_id=trackingmaster['collar_id'],
                               model_name=trackingmaster['collar_type'],
                               additional=additional
                               )
        source.save()

    subject_source = models.SubjectSource(subject=subject, source=source)
    start_at = trackingmaster['data_starts'].replace(tzinfo=pytz.UTC)
    end_at = datetime.datetime.max.replace(tzinfo=pytz.UTC)
    if trackingmaster['data_stops']:
        end_at = trackingmaster['data_stops'].replace(tzinfo=pytz.UTC)

    if end_at < start_at:
        end_at = datetime.datetime.max.replace(tzinfo=pytz.UTC)

    subject_source.assigned_range = psycopg2.extras.DateTimeTZRange(start_at, end_at)
    subject_source.save()

    with at_conn.cursor() as at_cursor:
        sql = 'SELECT * from archive_loc WHERE chronofile=%(chronofile)s'
        at_cursor.execute(sql, dict(chronofile=chronofile))
        rows = dictfetchall(at_cursor)

    archive_locs = rows
    for row in archive_locs:
        additional = {key: row[key] for key in ARCHIVE_LOC_FIELDS}
        obs = models.Observation(source=source,
                                 location=Point(row['lon'], row['lat']),
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
            import_trackingmaster(animal['chronofile'])
        except:
            logging.exception('Failed to import TrackingMaster %s', animal['chronofile'])



def main():
    import_all()
    return

    import_trackingmaster(558)
    import_trackingmaster(557)
    import_trackingmaster(546)
    import_trackingmaster(533)


if __name__ == '__main__':
    django.setup()
    main()
