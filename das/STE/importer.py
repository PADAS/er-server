import accounts.models
import datetime
import django
import django.contrib.auth.models
import logging
import observations.models
import psycopg2.extras
import pytz
import STE.subject_groups
import sys

from django.contrib.gis.geos import Point
from django.db import connections

logger = logging.getLogger(__name__)

def log_stdout(level=logging.DEBUG):
    soh = logging.StreamHandler(sys.stdout)
    soh.setLevel(level)
    logger = logging.getLogger()
    logger.addHandler(soh)
    logger.setLevel(level)

log_stdout(level=logging.INFO)


def dictfetchall(cursor):
    """Returns all rows from a cursor as a dict"""
    desc = cursor.description
    return [
        dict(zip([col[0] for col in desc], row))
        for row in cursor.fetchall()
    ]

TRACKING_MASTER_COMMON_FIELDS = ('comments', 'chronofile', 'rgb')
TRACKING_MASTER_ANIMAL_FIELDS = ('species', 'sex')
TRACKING_MASTER_DEVICE_FIELDS = ('active', 'frequency', 'predicted_expiry',)
ARCHIVE_LOC_FIELDS = ('dloadtime',)
TRACKING_COLLAR_SOURCE_TYPE = 'tracking-device'


def add_region(region, country):
    region_qs = observations.models.Region.objects.all().filter(region=region, country=country)
    if not region_qs:
        observations.models.Region(region=region, country=country).save()

def import_trackinguser(userid):
    logger.info('Importing TrackingUser %s', userid)
    at_conn = connections['animaltracking']
    with at_conn.cursor() as at_cursor:
        sql = 'SELECT * FROM trackingusers users JOIN trackingusersaux aux ON users.username = aux.username WHERE users.userid=%(userid)s'
        at_cursor.execute(sql, dict(userid=userid))
        rows = dictfetchall(at_cursor)
    trackinguser = rows[0]


    das_user = None;
    q_users = accounts.models.User.objects.filter(additional__ste_userid=trackinguser['userid'])
    for row in q_users:
        das_user = row

    if not das_user:
        das_user = accounts.models.User()
    additional = {'ste_userid': trackinguser['userid']}

    # Required Field
    das_user.username = trackinguser['username']

    emails = trackinguser.get('emails', ['NO_EMAIL_ADDRESS+{0}@vulcan.com'.format(das_user.username)])
    if len(emails) > 0:
        das_user.email = emails[0]
        if len(emails) > 1:
            additional['additional_emails'] = emails[1:]
    else:
        return

    password = trackinguser.get('password', None)
    if password is not None:
        das_user.set_password(password)

    lastname = trackinguser.get('lastname', 'None')
    das_user.last_name = lastname

    # Non-required user object fields
    firstname = trackinguser.get('firstname', None)
    if firstname is not None:
        das_user.first_name = firstname

    phonenumbers = trackinguser.get('phonenumbers', None)
    if phonenumbers is not None and len(phonenumbers) > 0:
        das_user.phone = phonenumbers[0]
        if len(phonenumbers) > 1:
            additional['additional_phonenumbers'] = phonenumbers[1:]

    # Additoinal fields (JSON)
    notes = trackinguser.get('notes', None)
    if notes is not None:
        additional['notes'] = notes

    org = trackinguser['organization']
    if org is not None:
        additional['organization'] = org

    moudatesigned = trackinguser.get('moudatesigned', None)
    if moudatesigned is not None:
        additional['moudatesigned'] = moudatesigned.isoformat()

    moutype = trackinguser.get('moutype', None)
    if moutype is not None:
        additional['moutype'] = moutype

    moufilename = trackinguser.get('moufilename', None)
    if moufilename is not None:
        additional['moufilename'] = moufilename

    tech = trackinguser.get('tech', None)
    if tech is not None:
        additional['tech'] = tech

    das_user.additional = additional

    try:
        das_user.save()
    except django.core.exceptions.ValidationError as ex:
        # Some emails are repeated in the STE database because the user does not have an email account
        # of their own. In this case, they use their manager's email. When we encounter these, update
        # the email to the format regular_email+das_username@regular_email.com and re-save. If we
        # still fail to save, let the exception go up the stack
        if len([message for message in ex.messages if 'address already exists' in message]) == 0:
            raise ex
        email_parts = das_user.email.split('@')
        unique_email = '{0}+{1}@{2}'.format(email_parts[0], das_user.username, email_parts[1])
        das_user.email = unique_email
        das_user.save()

    if trackinguser.get('delay', 0) == 0:
        time_permissions = accounts.models.PermissionSet.objects.get(name='View Elephants')
    else:
        time_permissions = accounts.models.PermissionSet.objects.get(name='View Delayed Elephants')
    das_user.permission_sets.add(time_permissions)

    for group_name in trackinguser['subjectgroups']:
        subject_group = observations.models.SubjectGroup.objects.get(name=group_name)
        if subject_group is None:
            continue

        permission_set = accounts.models.PermissionSet.objects.get_or_create(name='view_{0}_group'.format(group_name))[0]
        subject_group.permission_sets.add(permission_set)
        das_user.permission_sets.add(permission_set)

def import_trackingmaster(chronofile):
    logger.info('Importing TrackingMaster %s', chronofile)
    at_conn = connections['animaltracking']
    with at_conn.cursor() as at_cursor:
        sql = 'SELECT * from trackingmaster WHERE chronofile=%(chronofile)s'
        at_cursor.execute(sql, dict(chronofile=chronofile))
        rows = dictfetchall(at_cursor)
    trackingmaster = rows[0]

    if (trackingmaster['date_off_or_removed'] == 'Undeployed' or
        not trackingmaster['data_starts'] or
        trackingmaster['species'].lower() == 'undeployed'):
        logger.info('TrackingMaster for %s, Undeployed', chronofile)
        return

    with at_conn.cursor() as at_cursor:
        sql = 'SELECT * from regions WHERE chronofile=%(chronofile)s'
        at_cursor.execute(sql, dict(chronofile=chronofile))
        rows = dictfetchall(at_cursor)

    region = next(iter(rows), None)

    subject = None
    q_subject = observations.models.Subject.objects.filter(name=trackingmaster['name'])
    for row in q_subject:
        logger.info('Found existing subject %s by name', trackingmaster['name'])
        subject = row
    if not subject:
        additional = {}
        additional.update({key: trackingmaster[key] for key in TRACKING_MASTER_COMMON_FIELDS if key in trackingmaster})

        if region:
            add_region(region['region'], region['country'])
            additional['region'] = region['region']
            additional['country'] = region['country']
        additional['external_id'] = trackingmaster['animal_id']
        subject_type = 'wildlife'
        if trackingmaster['species'].lower() == 'vehicle':
            subject_type = 'vehicle'
        else:
            additional.update({key: trackingmaster[key] for key in TRACKING_MASTER_ANIMAL_FIELDS if key in trackingmaster})
        subject = observations.models.Subject(name=trackingmaster['name'],
                                              subject_type=subject_type,
                                              additional=additional)
        subject.save()

    source = None
    q_sources = observations.models.Source.objects.filter(source_type=TRACKING_COLLAR_SOURCE_TYPE)
    q_sources = q_sources.filter(manufacturer_id=trackingmaster['collar_id'])
    for row in q_sources:
        source = row
    if not source:
        additional = {}
        additional.update({key: trackingmaster[key] for key in TRACKING_MASTER_DEVICE_FIELDS if key in trackingmaster})
        for k, v in additional.items():
            if isinstance(v, datetime.datetime):
                additional[k] = v.isoformat()
        source = observations.models.Source(source_type=TRACKING_COLLAR_SOURCE_TYPE,
                                            manufacturer_id=trackingmaster['collar_id'],
                                            model_name=trackingmaster['collar_type'],
                                            additional=additional
                                            )
        source.save()

    subject_source = observations.models.SubjectSource(subject=subject, source=source, additional={})
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

    archive_locs = []
    for row in rows:
        observation = observations.models.Observation(
            source=source,
            additional={key: row[key] for key in ARCHIVE_LOC_FIELDS},
            location=Point(row['lon'], row['lat']),
            recorded_at=row['fixtime'].replace(tzinfo=pytz.UTC).isoformat()
        )
        for k, v in observation.additional.items():
            if isinstance(v, datetime.datetime):
                observation.additional[k] = v.isoformat()
        archive_locs.append(observation)


    if archive_locs:
        observations.models.Observation.objects.bulk_create(archive_locs, batch_size=200)

def import_subject_group(group_name, query):
    at_conn = connections['animaltracking']
    with at_conn.cursor() as at_cursor:
        at_cursor.execute(query)
        rows = dictfetchall(at_cursor)
    result = rows[0]

    if (result['group_members'] is None or len(result['group_members']) == 0):
        logger.info('Error looking up group members for {0)', group_name)
        return

    subject_group = observations.models.SubjectGroup.objects.get_or_create(name=group_name)[0]

    for chronofile_member in result['group_members']:

        with at_conn.cursor() as at_cursor:
            sql = 'SELECT * from trackingmaster WHERE chronofile=%(chronofile)s'
            at_cursor.execute(sql, dict(chronofile=chronofile_member))
            rows = dictfetchall(at_cursor)
        chronofile = rows[0]

        subject = None
        q_subject = observations.models.Subject.objects.filter(name=chronofile['name'])
        for row in q_subject:
            logger.info('Found existing subject %s by name',chronofile['name'])
            subject = row
        if not subject:
            logger.warn("could not find subject")
            continue
        subject.groups.add(subject_group)


def import_all_users():
    at_conn = connections['animaltracking']
    with at_conn.cursor() as at_cursor:
        sql = 'SELECT userid from trackingusers'
        at_cursor.execute(sql)
        rows = dictfetchall(at_cursor)

    error_list = []
    for user in rows:
        try:
            import_trackinguser(user['userid'])
        except Exception as ex:
            error_list.append({'User {0} import error - {1}'.format(user['userid'], str(ex))})
            logging.exception('Failed to import TrackingUser %s', user['userid'])
    return error_list

def import_all_chronofiles():
    at_conn = connections['animaltracking']
    with at_conn.cursor() as at_cursor:
        sql = 'SELECT chronofile from trackingmaster'
        at_cursor.execute(sql)
        rows = dictfetchall(at_cursor)

    error_list = []
    for animal in rows:
        try:
            import_trackingmaster(animal['chronofile'])
        except Exception as ex:
            error_list.append({'User {0} import error - {1}'.format(animal['chronofile'], str(ex))})
            logging.exception('Failed to import TrackingMaster %s',animal['chronofile'])
    return error_list

def import_all_subject_groups():
    error_list = []
    for group_name, query in STE.subject_groups.subject_group_query_map.items():
        print('######### Importing ' + group_name)
        import_subject_group(group_name, query)
    return error_list



def import_all():
    errors = []
    errors += import_all_chronofiles()
    errors += import_all_subject_groups()
    errors += import_all_users()
    print(errors)

def import_test():

    USER_SAMPLES = [
        6,
        90,
        116,
        172,
        189,
    ]

    CHRONO_SAMPLES = [
        21,
        154,
        333,
        400,
        685,
    ]

    for trackinguser in USER_SAMPLES:
        try:
            import_trackinguser(trackinguser)
        except Exception as ex:
            print(ex)
            raise ex

    for chronofile in CHRONO_SAMPLES:
        try:
            import_trackingmaster(chronofile)
        except Exception as ex:
            print(ex)
            raise ex

