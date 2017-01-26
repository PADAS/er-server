import accounts.models
import datetime
import django
import django.contrib.auth.models
import logging
import observations.models
import psycopg2.extras
import pytz
from STE import unitlists
import STE.subject_groups
import sys

from django.contrib.gis.geos import Point
from django.db import connections
from django.contrib.contenttypes.models import ContentType

from tracking.models import SkygisticsSatellitePlugin, SavannahPlugin, AWTHttpPlugin, SourcePlugin

logger = logging.getLogger(__name__)

def log_stdout(level=logging.DEBUG):
    soh = logging.StreamHandler(sys.stdout)
    soh.setLevel(level)
    logger = logging.getLogger()
    logger.addHandler(soh)
    logger.setLevel(level)

log_stdout(level=logging.INFO)

# Map AnimalTracking species value to Das (type, sub-type)
# Keys are taking as a distinct list of species values in AnimalTracking.
# TODO: Ask Jake to review this map
atdb_species_to_das_type = {'elephant': ('wildlife', 'elephant'),
                            'undeployed': ('untyped', 'undeployed'),
                            'scimitar oryx': ('wildlife', 'scimitar_oryx'),
                            'cow': ('wildlife', 'cow'),
                            'cheetah': ('wildlife', 'cheetah'),
                            'expedition': ('person', 'expedition'),
                            'vehicle': ('vehicle', 'vehicle'),
                            'lion': ('wildlife', 'lion'),
                            'black rhino': ('wildlife', 'rhino'),
                            'goat': ('wildlife', 'goat'),
                            'sable': ('wildlife', 'sable'),
                            'forest elephant': ('wildlife', 'forest_elephant'),
                            'grevys zebra': ('wildlife', 'grevys_zebra'),
                            'white rhino': ('wildlife', 'rhino')
                            }

def dictfetchall(cursor):
    """Returns all rows from a cursor as a dict"""
    desc = cursor.description
    return [
        dict(zip([col[0] for col in desc], row))
        for row in cursor.fetchall()
    ]

TRACKING_MASTER_COMMON_FIELDS = ('comments', 'chronofile')
TRACKING_MASTER_ANIMAL_FIELDS = ('active', 'species', 'sex', 'rgb')
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

    lastname = trackinguser.get('lastname', '')
    das_user.last_name = lastname

    # Non-required user object fields
    firstname = trackinguser.get('firstname', '')
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

    # try:
    #     das_user.save()
    # except django.core.exceptions.ValidationError as ex:
    #     # Some emails are repeated in the STE database because the user does not have an email account
    #     # of their own. In this case, they use their manager's email. When we encounter these, update
    #     # the email to the format regular_email+das_username@regular_email.com and re-save. If we
    #     # still fail to save, let the exception go up the stack
    #     if len([message for message in ex.messages if 'address already exists' in message]) == 0:
    #         raise ex
    #     email_parts = das_user.email.split('@')
    #     unique_email = '{0}+{1}@{2}'.format(email_parts[0], das_user.username, email_parts[1])
    #     das_user.email = unique_email
    #     das_user.save()

    end = trackinguser.get('delay', 0)
    begin = trackinguser.get('fulldataaccess', 60)

    end_perms, created = accounts.models.PermissionSet.objects.get_or_create(name='Access Ends {0}'.format(end))
    if created:
        end_perms.permissions.add(django.contrib.auth.models.Permission.objects.get_by_natural_key('access_ends_{0}'.format(end), 'observations', 'subject'))

    begin_perms, created = accounts.models.PermissionSet.objects.get_or_create(name='Access Begins {0}'.format(begin))
    if created:
        begin_perms.permissions.add(django.contrib.auth.models.Permission.objects.get_by_natural_key('access_begins_{0}'.format(begin), 'observations', 'subject'))

    das_user.permission_sets.add(end_perms)
    das_user.permission_sets.add(begin_perms)

    for group_name in trackinguser['subjectgroups']:
        try:
            permission_set, created = accounts.models.PermissionSet.objects.get_or_create(name='view_{0}_group'.format(group_name))
            if created or not created:
                permission_set.permissions.add(django.contrib.auth.models.Permission.objects.get_by_natural_key(
                    'view_subjectgroup', 'observations', 'subjectgroup'))
                permission_set.permissions.add(django.contrib.auth.models.Permission.objects.get_by_natural_key(
                    'subscribe_alerts', 'observations', 'subject'))
                permission_set.permissions.add(django.contrib.auth.models.Permission.objects.get_by_natural_key(
                    'view_subject', 'observations', 'subject'))
            subject_group = observations.models.SubjectGroup.objects.get(name=group_name)
            subject_group.permission_sets.add(permission_set)
            # das_user.permission_sets.add(permission_set)
        except observations.models.SubjectGroup.DoesNotExist:
            continue

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

    # if not subject:
    additional = {}

    if region:
        add_region(region['region'], region['country'])
        additional['region'] = region['region']
        additional['country'] = region['country']
    additional['tm_animal_id'] = trackingmaster['animal_id']

    # Resolve ATDB species to DAS subject type values.;
    subject_type, subject_subtype = atdb_species_to_das_type.get(trackingmaster['species'].lower(), ('wildlife', 'elephant'))

    additional.update({key: trackingmaster[key] for key in TRACKING_MASTER_ANIMAL_FIELDS if key in trackingmaster})

    active = 'active' in additional and additional['active'] == 1

    with at_conn.cursor() as at_cursor:
        sql = 'SELECT * from display WHERE displaygroup=%(subject_name)s'
        at_cursor.execute(sql, dict(subject_name=trackingmaster['name']))
        rows = dictfetchall(at_cursor)

    display = next(iter(rows), None)

    if (display is None or 'colour' not in display) and 'rgb' in additional:
        if additional['rgb'] is None or ',' not in additional['rgb']:
            del(additional['rgb'])
    else:
        try:
            rgb = display['colour']
            additional['rgb'] = '{0},{1},{2}'.format(rgb[0], rgb[1], rgb[2])
        except Exception as ex:
            print(ex)
            del (additional['rgb'])


    # Handle creating or updating Subject
    subject, created = observations.models.Subject.objects.update_or_create(name=trackingmaster['name'],
                                                                            defaults=dict(subject_type=subject_type,
                                                                                          subject_subtype=subject_subtype,
                                                                                          is_active=active,
                                                                                          additional=additional))

    if created:
        logger.info('Created new subject for name=%s', trackingmaster['name'])
    else:
        logger.info('Updated existing subject for name=%s', trackingmaster['name'])


    # Handle creating or updating Source
    additional.update({key: trackingmaster[key] for key in TRACKING_MASTER_DEVICE_FIELDS if key in trackingmaster})
    for k, v in additional.items():
        if isinstance(v, datetime.datetime):
            additional[k] = v.isoformat()
    source, created = observations.models.Source.objects.update_or_create(source_type=TRACKING_COLLAR_SOURCE_TYPE,
                                        manufacturer_id=trackingmaster['collar_id'],
                                        defaults=dict(model_name=trackingmaster['collar_type'],
                                        additional=additional)
                                        )
    if created:
        logger.info('Created new source for name=%s, collar_id=%s', trackingmaster['name'], trackingmaster['collar_id'])
    else:
        logger.info('Updated existing source for name=%s, collar_id=%s', trackingmaster['name'], trackingmaster['collar_id'])

    #
    # Handle Creating or updating SubjectSource
    #
    ss_additional = {key: trackingmaster[key] for key in TRACKING_MASTER_COMMON_FIELDS if key in trackingmaster}

    # subject_source = observations.models.SubjectSource(subject=subject, source=source, additional=ss_additional)
    start_at = trackingmaster['data_starts'].replace(tzinfo=pytz.UTC)
    end_at = datetime.datetime.max.replace(tzinfo=pytz.UTC)
    if trackingmaster['data_stops']:
        end_at = trackingmaster['data_stops'].replace(tzinfo=pytz.UTC)

    if end_at < start_at:
        end_at = datetime.datetime.max.replace(tzinfo=pytz.UTC)

    assigned_range = psycopg2.extras.DateTimeTZRange(start_at, end_at)

    subject_source, created = observations.models.SubjectSource.objects.get_or_create(subject=subject, source=source,
                                                                                      assigned_range=assigned_range,
                                                                                      defaults={
                                                                                          'additional': ss_additional
                                                                                      })
    if created:
        logger.info('Created new SubjectSource for name=%s, collar_id=%s', trackingmaster['name'], trackingmaster['collar_id'])
    else:
        logger.info('Found existing SubjectSource for name=%s, collar_id=%s', trackingmaster['name'], trackingmaster['collar_id'])


    return
    # with at_conn.cursor() as at_cursor:
    #     sql = 'SELECT * from archive_loc WHERE chronofile=%(chronofile)s'
    #     at_cursor.execute(sql, dict(chronofile=chronofile))
    #     rows = dictfetchall(at_cursor)
    #
    # mapping = map_source_to_plugin(source, trackingmaster['datasource'], trackingmaster['collar_type'])
    # if mapping is None or not SourcePlugin.objects.filter(source=source).exists():
    #     archive_locs = []
    #     try:
    #         latest_observation = observations.models.Observation.objects.filter(source=source).latest('recorded_at')
    #         latest_das_observation = latest_observation.recorded_at
    #     except:
    #         latest_observation = None
    #         latest_das_observation = datetime.datetime.min
    #
    #     for row in rows:
    #         observation = observations.models.Observation(
    #             source=source,
    #             additional={key: row[key] for key in ARCHIVE_LOC_FIELDS},
    #             location=Point(row['lon'], row['lat']),
    #             recorded_at=pytz.utc.localize(row['fixtime'])
    #         )
    #         if observation.recorded_at <= latest_das_observation:
    #             continue
    #
    #         if latest_observation is None or observation.recorded_at > latest_observation.recorded_at:
    #             latest_observation = observation
    #
    #         for k, v in observation.additional.items():
    #             if isinstance(v, datetime.datetime):
    #                 observation.additional[k] = v.isoformat()
    #         archive_locs.append(observation)
    #
    #     if archive_locs:
    #         observations.models.Observation.objects.bulk_create(archive_locs, batch_size=200)
    #         for delay_hours in (0, 24):
    #             observations.models.SubjectStatus.objects.update_from_observation(latest_observation, delay_hours=delay_hours)
    #
    #     create_sourceplugin(source, latest_observation=latest_observation, datasource=trackingmaster['datasource'],
    #                         collar_type=trackingmaster['collar_type'])

def map_source_to_plugin (source, datasource=None, collar_type=None):
    if (datasource == 'localfile' and collar_type == 'AWT Satellite') \
            or source.manufacturer_id in unitlists.skyq_imeilist:
        # Associate with SkygisticsPlugin
        return SkygisticsSatellitePlugin.objects.get(name='ste-skygistics')
    elif datasource == 'HTTP':
        # AWT Http Plugin
        return AWTHttpPlugin.objects.get(name='awt-http-gsm')
    elif datasource == 'SavannahTrackingAPI':
        # SavannahTrackingPlugin
        return SavannahPlugin.objects.get(name='savannah')
    else:
        logger.info('No plugin identified for source %s', source)
        return None

def create_sourceplugin(source, latest_observation=None, datasource=None, collar_type=None):

    plugin = map_source_to_plugin(source, datasource, collar_type)

    if plugin is not None:
        logger.info('Associating source %s with plugin %s', source, plugin)

        defaults = {
            'cursor_data': {'latest_timestamp': latest_observation.recorded_at.isoformat()}
        } if latest_observation else None

        plugin_type = ContentType.objects.get_for_model(plugin)
        sp, created = SourcePlugin.objects.get_or_create(source=source, plugin_id=plugin.id, plugin_type=plugin_type,
                                           defaults=defaults)
        source.provider_name = plugin.name
        source.save()

def import_subject_group(group_name, query):
    at_conn = connections['animaltracking']
    with at_conn.cursor() as at_cursor:
        at_cursor.execute(query)
        rows = dictfetchall(at_cursor)
    result = rows[0]

    if (result['group_members'] is None or len(result['group_members']) == 0):
        logger.info('Error looking up group members for {0}'.format(group_name))
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
            error_list.append({'Chronofile {0} import error - {1}'.format(animal['chronofile'], str(ex))})
            logging.exception('Failed to import TrackingMaster %s',animal['chronofile'])
    return error_list

def import_all_subject_groups():
    error_list = []
    for group_name, query in STE.subject_groups.subject_group_query_map.items():
        try:
            import_subject_group(group_name, query)
        except Exception as ex:
            error_list.append({'Subject group {0} import error - {1}'.format(group_name, str(ex))})
    return error_list



def import_all():
    errors = []
    errors += import_all_chronofiles()
    #errors += import_all_subject_groups()
    #errors += import_all_users()
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

