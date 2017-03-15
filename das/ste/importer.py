import accounts.models

import django
import django.contrib.auth.models
import django.db.utils
from django.db.models import Max, Min
import logging
import observations.models
import ste.models

import psycopg2.extras
from ste import unitlists
import ste.subject_groups
import sys

from datetime import datetime, timedelta
import pytz
import pandas as pd

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
                            'unassigned': ('untyped', 'undeployed'),
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
TRACKING_MASTER_ANIMAL_FIELDS = ('active', 'species', 'sex')
TRACKING_MASTER_DEVICE_FIELDS = ('active', 'frequency', 'predicted_expiry',)
TRACKING_USER_ADDITIONAL_FIELDS = ('notes', 'organization', 'moudatesigned', 'moutype', 'tech', 'expiry')
ARCHIVE_LOC_FIELDS = ('dloadtime',)
TRACKING_COLLAR_SOURCE_TYPE = 'tracking-device'
DEFAULT_SOURCE_PROVIDER_NAME = 'default'

def add_region(region, country):
    region_qs = observations.models.Region.objects.all().filter(region=region, country=country)
    if not region_qs:
        observations.models.Region(region=region, country=country).save()

def import_trackinguser(userid):
    logger.info('Importing TrackingUser %s', userid)
    at_conn = connections['animaltracking']
    das_conn = connections['default']

    with at_conn.cursor() as at_cursor:
        sql = 'SELECT * FROM trackingusers users JOIN trackingusersaux aux ON users.username = aux.username WHERE users.userid=%(userid)s'
        at_cursor.execute(sql, dict(userid=userid))
        rows = dictfetchall(at_cursor)
    trackinguser = rows[0]

    # Fix up these fields in trackinsmaster because they have
    if not trackinguser['lastname'] or len(trackinguser['lastname']) == 0:
        trackinguser['lastname'] = 'No Lastname'

    if not trackinguser['firstname'] or len(trackinguser['firstname']) == 0:
        trackinguser['firstname'] = 'No Firstname'

    # Put together the additional fields
    additional = {'ste_userid': trackinguser['userid']}

    # Save primary email for a top-level user attribute
    emails = trackinguser.get('emails', None)
    if emails and len(emails) > 0:
        primary_email = emails[0]
        if len(emails) > 1:
            additional['additional_emails'] = emails[1:]
    else:
        primary_email = 'NO_EMAIL_ADDRESS+{0}@vulcan.com'.format(
            trackinguser['username'])

    # save primary phone for a top-level user attribute
    primary_phone = '+55555555555'
    phonenumbers = trackinguser.get('phonenumbers', None)
    if phonenumbers and len(phonenumbers) > 0:
        primary_phone = phonenumbers[0]
        if len(phonenumbers) > 1:
            additional['additional_phonenumbers'] = phonenumbers[1:]

    # Get any other fields, if they exist
    additional.update({key: trackinguser[key] for key in
                       TRACKING_USER_ADDITIONAL_FIELDS if
                       key in trackinguser})

    # Fix any date fields
    for k, v in additional.items():
        if isinstance(v, datetime):
            additional[k] = v.isoformat()

    # Look to see if a das user for this trackingusers row already exists
    with das_conn.cursor() as das_cursor:
        id_string = str(trackinguser['userid'])
        sql = 'SELECT * ' \
              '  FROM accounts_user' \
              ' WHERE additional ->> \'ste_userid\'=%(user_id)s'
        das_cursor.execute(sql, dict(user_id=id_string))
        rows = dictfetchall(das_cursor)

    user = next(iter(rows), None)

    # If one does, update that user. Can't use update_or_create because the
    # primary key in AT maps to an entry in the additional column in DAS
    if user:
        created = False
        users = accounts.models.User.objects.filter(id=user['id'])
        user = users.first()
        try:
            users.update(username=trackinguser['username'],
                         last_name=trackinguser.get('lastname', 'No Lastname'),
                         first_name=trackinguser.get('firstname', 'No Firstname'),
                         email=primary_email,
                         phone=primary_phone,
                         additional=additional)
        except django.db.utils.IntegrityError as ex:
            # Some emails are repeated in the STE database because the user does not have an email account
            # of their own. In this case, they use their manager's email. When we encounter these, update
            # the email to the format regular_email+das_username@regular_email.com and re-save. If we
            # still fail to save, let the exception go up the stack
            if len([message for message in ex.args if 'accounts_user_email_' in message]) == 0:
                raise ex
            email_parts = primary_email.split('@')
            primary_email = '{0}+{1}@{2}'.format(email_parts[0], trackinguser['username'], email_parts[1])
            users.update(username=trackinguser['username'],
                         last_name=trackinguser.get('lastname', 'No Lastname'),
                         first_name=trackinguser.get('firstname', 'No Firstname'),
                         email=primary_email,
                         phone=primary_phone,
                         additional=additional)

        # Set password this way so that it gets correctly encrypted
        user.set_password(trackinguser.get('password', None))

    # If we didn't find an existing das user for this AT user, create one
    else:
        try:
            user, created = accounts.models.User.objects.update_or_create(
                username=trackinguser['username'],
                defaults=dict(last_name=trackinguser.get('lastname', 'No Lastname'),
                              first_name=trackinguser.get('firstname', 'No Firstname'),
                              email=primary_email,
                              phone=primary_phone,
                              additional=additional))
        except django.core.exceptions.ValidationError as ex:
            # Some emails are repeated in the STE database because the user does not have an email account
            # of their own. In this case, they use their manager's email. When we encounter these, update
            # the email to the format regular_email+das_username@regular_email.com and re-save. If we
            # still fail to save, let the exception go up the stack
            if len([message for message in ex.messages if 'address already exists' in message]) == 0:
                raise ex
            email_parts = primary_email.split('@')
            primary_email = '{0}+{1}@{2}'.format(email_parts[0], trackinguser['username'], email_parts[1])
            user, created = accounts.models.User.objects.update_or_create(
                username=trackinguser['username'],
                defaults=dict(last_name=trackinguser.get('lastname', 'No Lastname'),
                              first_name=trackinguser.get('firstname', 'No Firstname'),
                              email=primary_email,
                              phone=primary_phone,
                              additional=additional))

        # Set password this way so that it gets correctly encrypted
        user.set_password(trackinguser.get('password', None))

    if created:
        logger.info('Created new user: %s', user.username)
    else:
        logger.info('Updated existing user: %s', user.username)

    # Update the user's password this way so it gets hashed
    password = trackinguser.get('password', None)
    if password is not None:
        user.set_password(password)
        user.save()

    # Clean up the user's permissions. This line can be removed eventually,
    # but for the time being, there's cruft.
    user.permission_sets.clear()

    # Get the user's access window
    end = trackinguser.get('delay', 0)
    begin = trackinguser.get('fulldataaccess', 60)
    begin_name = begin

    # Use a positive value so our checks to find the largest allowed
    # permission work correctly
    if begin == -999:
        begin_name = 'All'
        begin = 'all'

    end_perms, created = accounts.models.PermissionSet.objects.get_or_create(name='Access Ends {0}'.format(end))
    if created:
        end_perms.permissions.add(django.contrib.auth.models.Permission.objects.get_by_natural_key('access_ends_{0}'.format(end), 'observations', 'subject'))

    begin_perms, created = accounts.models.PermissionSet.objects.get_or_create(name='Access Begins {0}'.format(begin_name))
    if created:
        begin_perms.permissions.add(django.contrib.auth.models.Permission.objects.get_by_natural_key('access_begins_{0}'.format(begin), 'observations', 'subject'))

    user.permission_sets.add(end_perms)
    user.permission_sets.add(begin_perms)

    # Get the user's allowed subjects
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
            user.permission_sets.add(permission_set)
        except observations.models.SubjectGroup.DoesNotExist:
            continue

def import_trackingmaster_animal(animal_name):
    logger.info('Importing TrackingMaster records for subject %s', animal_name)
    at_conn = connections['animaltracking']
    das_conn = connections['default']
    with at_conn.cursor() as at_cursor:
        sql = 'SELECT * from trackingmaster WHERE name=%(animal_name)s ' \
              'ORDER BY data_starts asc'
        at_cursor.execute(sql, dict(animal_name=animal_name))
        rows = dictfetchall(at_cursor)

    for trackingmaster in rows:

        chronofile = trackingmaster['chronofile']

        # Get the subject info prepared
        additional = {'tm_animal_id': trackingmaster['animal_id']}
        additional.update(
            {key: trackingmaster[key] for key in TRACKING_MASTER_ANIMAL_FIELDS
             if key in trackingmaster})

        # Subject region -> lookup and endure it exists in das
        with at_conn.cursor() as at_cursor:
            sql = 'SELECT * from regions WHERE chronofile=%(chronofile)s'
            at_cursor.execute(sql, dict(chronofile=chronofile))
            rows = dictfetchall(at_cursor)
        region = next(iter(rows), None)

        if region:
            add_region(region['region'], region['country'])
            additional['region'] = region['region']
            additional['country'] = region['country']

        # Subject sex -> Unknown sex should not be in additional at all
        if 'sex' in additional and additional['sex'] in (
                'Unknown', 'Unkown', 'None'):
            del (additional['sex'])

        # Resolve ATDB species to DAS subject type values.;
        subject_type, subject_subtype = atdb_species_to_das_type.get(
            trackingmaster['species'].lower(), ('unassigned', 'unassigned'))

        # Icon color -> If color is not specified, default to white
        # _ALWAYS_ ignore rgb column in trackingmaster, even if display table
        # has no value for chronofile
        with at_conn.cursor() as at_cursor:
            sql = 'SELECT * from display WHERE displaygroup=%(subject_name)s'
            at_cursor.execute(sql, dict(subject_name=trackingmaster['name']))
            rows = dictfetchall(at_cursor)
        display = next(iter(rows), None)

        if display is not None and 'colour' in display and \
                len(display['colour']) == 3:
            r = display['colour'][0]
            g = display['colour'][1]
            b = display['colour'][2]
            additional['rgb'] = '{0},{1},{2}'.format(r, g, b)
        else:
            # Per Jake: if subject has no display table entry, it should always
            # display as a white triangle
            additional['rgb'] = '255,255,255'
            subject_type = 'unassigned'
            subject_subtype = 'unassigned'

        # If a subject name has changed in trackingmaster, calling get_or_create
        # will create a new subject, which is not what we want. Check to see
        # if there's an existing subjectsource record for this chronofile first.
        # We'll use this to determine if a subject we haven't seen before is
        # new, or if it's an existing subject with an updated name.
        with das_conn.cursor() as das_cursor:
            id_string=str(chronofile)
            sql = 'SELECT * ' \
                  '  FROM observations_subjectsource' \
                  ' WHERE additional ->> \'chronofile\'=%(chronofile)s'
            das_cursor.execute(sql, dict(chronofile=id_string))
            rows = dictfetchall(das_cursor)

        existing_ss = next(iter(rows), None)

        if existing_ss:
            created = False
            subjects = observations.models.Subject.objects.filter(
                id=existing_ss['subject_id'])
            subject = subjects.first()
            subjects.update(
                name=trackingmaster['name'],
                subject_type=subject_type,
                subject_subtype=subject_subtype,
                is_active='active' in additional and additional['active'] == 1,
                additional=additional)
        else:
            # Create or update the subject
            subject, created = observations.models.Subject.objects.\
                update_or_create(
                    name = trackingmaster['name'],
                    defaults = dict(subject_type=subject_type,
                                    subject_subtype=subject_subtype,
                                    is_active='active' in additional and
                                              additional['active'] == 1,
                                    additional=additional))

        if created:
            logger.info('Created new subject for name=%s',
                        trackingmaster['name'])
        else:
            logger.info('Updated existing subject for name=%s',
                        trackingmaster['name'])

        # Handle creating or updating Source
        additional.update({
            key: trackingmaster[key] for key in TRACKING_MASTER_DEVICE_FIELDS if
            key in trackingmaster})
        for k, v in additional.items():
            if isinstance(v, datetime):
                additional[k] = v.isoformat()

        mapped_plugin = map_source_to_plugin(trackingmaster['collar_id'],
                                             trackingmaster['datasource'],
                                             trackingmaster['collar_type'])

        # We need to use the plugin's name in place of the source's
        # provider_name. Default value is 'default'.
        provider_name = mapped_plugin.name if mapped_plugin \
            else DEFAULT_SOURCE_PROVIDER_NAME

        source, created = observations.models.Source.objects.update_or_create(
            source_type=TRACKING_COLLAR_SOURCE_TYPE,
            manufacturer_id=trackingmaster['collar_id'],
            provider_name=provider_name,
            defaults=dict(model_name=trackingmaster['collar_type'],
            additional=additional)
                                            )
        if created:
            logger.info('Created new source for name=%s, collar_id=%s',
                        trackingmaster['name'], trackingmaster['collar_id'])
        else:
            logger.info('Updated existing source for name=%s, collar_id=%s',
                        trackingmaster['name'], trackingmaster['collar_id'])

        #
        # Handle Creating or updating SubjectSource
        #
        ss_additional = {key: trackingmaster[key] for key in
                         TRACKING_MASTER_COMMON_FIELDS if
                         key in trackingmaster}

        if trackingmaster['data_starts'] is not None:
            start_at = trackingmaster['data_starts'].replace(
                tzinfo=pytz.UTC)
        else:
            start_at = pytz.utc.localize(datetime.min)

        if trackingmaster['data_stops'] is not None:
            end_at = pytz.utc.localize(trackingmaster['data_stops'])
        else:
            end_at = pytz.utc.localize(datetime.max)

        if end_at < start_at:
            end_at = pytz.utc.localize(datetime.max)

        assigned_range = psycopg2.extras.DateTimeTZRange(start_at, end_at)

        # If a subjectsource's assigned range changes in trackingmaster, calling
        # get_or_create will create a new record, which is not what we want.
        # Check to see if there's an existing subjectsource record for this
        # chronofile first.
        with das_conn.cursor() as das_cursor:
            id_string=str(chronofile)
            sql = 'SELECT * ' \
                  '  FROM observations_subjectsource' \
                  ' WHERE additional ->> \'chronofile\'=%(chronofile)s'
            das_cursor.execute(sql, dict(chronofile=id_string))
            rows = dictfetchall(das_cursor)

        subject_source = next(iter(rows), None)

        if subject_source:
            created = False
            observations.models.SubjectSource.objects.filter(
                id=subject_source['id']).update(subject=subject,
                                                source=source,
                                                assigned_range=assigned_range,
                                                additional=ss_additional)

        else:
            subject_source, created = observations.models.SubjectSource.\
                objects.get_or_create(subject=subject,
                                      source=source,
                                      assigned_range=assigned_range,
                                      defaults={'additional': ss_additional})
        if created:
            logger.info('Created new SubjectSource for name=%s, collar_id=%s',
                        trackingmaster['name'], trackingmaster['collar_id'])
        else:
            logger.info('Found existing SubjectSource for name=%s, collar=%s',
                        trackingmaster['name'], trackingmaster['collar_id'])

        if mapped_plugin is None or not SourcePlugin.objects.filter(
                source=source).exists():
            archive_locs = []
            try:
                latest_observation = observations.models.Observation.objects.\
                    filter(source=source).latest('recorded_at')
                latest_das_observation = latest_observation.recorded_at
            except:
                latest_observation = None
                latest_das_observation = pytz.utc.localize(datetime.min)

            with at_conn.cursor() as at_cursor:
                sql = 'SELECT * from archive_loc WHERE chronofile=%(chronofile)s'
                at_cursor.execute(sql, dict(chronofile=chronofile))
                rows = dictfetchall(at_cursor)

            for row in rows:
                observation = observations.models.Observation(
                    source=source,
                    additional={key: row[key] for key in ARCHIVE_LOC_FIELDS},
                    location=Point(row['lon'], row['lat']),
                    recorded_at=pytz.utc.localize(row['fixtime'])
                )
                if observation.recorded_at <= latest_das_observation:
                    continue

                if latest_observation is None or observation.recorded_at > \
                        latest_observation.recorded_at:
                    latest_observation = observation

                for k, v in observation.additional.items():
                    if isinstance(v, datetime):
                        observation.additional[k] = v.isoformat()
                archive_locs.append(observation)

            if archive_locs:
                observations.models.Observation.objects.bulk_create(
                    archive_locs,
                    batch_size=200)
                for delay_hours in observations.models.Subject.VIEW_END_WINDOWS:
                    observations.models.SubjectStatus.objects.\
                        update_from_observation(latest_observation,
                                                delay_hours=delay_hours[1]*24)

            create_sourceplugin(source,
                                latest_observation=latest_observation,
                                datasource=trackingmaster['datasource'],
                                collar_type=trackingmaster['collar_type'])

        # This probably doesn't need to get run every time once we're caught up
        # find_and_add_missing_observations(chronofile, source)

        # make sure the subjectstatus gets updated with the latest observation
        latest_observation = observations.models.Observation.objects.\
            get_last_observation(subject=subject)

        if latest_observation is not None:
            for delay_hours in observations.models.Subject.VIEW_END_WINDOWS:
                observations.models.SubjectStatus.objects.\
                    update_from_observation(
                    latest_observation, delay_hours=delay_hours[1]*24)

def find_and_add_missing_observations(chronofile, source):

    add_these = generate_missing_observations(chronofile, source)
    observations.models.Observation.objects.bulk_create(add_these, batch_size=200)


def generate_missing_observations(chronofile, source):
    '''
    Find and yield archive_loc records that aren't matched in DAS, for the given source.

    :param chronofile: integer, identifies chronofile in archive_loc table.
    :param source: Source, indicates the Source to associate these observations with.
    :return: generator of archive_loc dicts that should be added to DAS.
    '''

    # Create dataframes for both record sets.
    def generate_old(items):
        for item in items:
            yield {'recorded_at': pytz.utc.localize(item.fixtime),
                   'latitude': item.lat,
                   'longitude': item.lon,
                   'recordserial': item.recordserial,
                   'chronofile': item.chronofile.chronofile,
                   'dloadtime': item.dloadtime
                   }

    def generate_new(items):
        for item in items:
            yield {'recorded_at': item.recorded_at,
                   'latitude': item.location.y,
                   'longitude': item.location.x
                   }


    # Compare in chunks of this size.
    chunk_interval = timedelta(days=180)

    # Set hard limits on the dates we'll look for.
    START_DATE_LIMIT = pytz.utc.localize(datetime(1980, 1, 1))
    END_DATE_LIMIT = pytz.utc.localize(datetime.utcnow())

    # Determine the range of observations for the given chronofile.
    date_range = ste.models.ArchiveLoc.objects.using('animaltracking').filter(
        chronofile__chronofile=chronofile).aggregate(Min('fixtime'), Max('fixtime'))

    # Set the date where we'll stop looking for observations.
    try:
        earliest_date = pytz.utc.localize(date_range['fixtime__min'])
    except:
        earliest_date = START_DATE_LIMIT

    # Set the markers for the first block of fixes.
    try:
        end = pytz.utc.localize(date_range['fixtime__max']) + timedelta(seconds=1)
    except:
        end = END_DATE_LIMIT

    start = end - chunk_interval

    print('chronofile: {}, source: {} {}, finding observations in range: {} to {}'.format(
        chronofile, source.id, source.manufacturer_id, start, end
    ))

    # Compare within chunk_interval, and quit when we get back before the 10 years ago.
    while end >= earliest_date:

        print('chronofile: {}, source: {} {}, matching from {} to {}'.format(
            chronofile, source.id, source.manufacturer_id, start, end)
        )

        atobservations = ste.models.ArchiveLoc.objects.using('animaltracking').filter(chronofile__chronofile=chronofile,
                                                                                      fixtime__gte=start,
                                                                                      fixtime__lt=end)

        das_observations = observations.models.Observation.objects.filter(source=source, recorded_at__gte=start,
                                                                          recorded_at__lt=end)

        df_at = pd.DataFrame(generate_old(atobservations))
        df_das = pd.DataFrame(generate_new(das_observations))

        if len(df_at) > 0:
            # Join the two dataframes, on recorded_at
            merged_result = df_at.merge(df_das, on='recorded_at', how='left', suffixes=('_at', '_das'))

            # Create a dataframe of those records exclusive to Animal Tracking
            missing_observations_results = merged_result[pd.isnull(merged_result['latitude_das'])]

            print('\tFound {} missing observations.'.format(len(missing_observations_results)))
            def create_observation(s):
                s = s.to_dict()
                return observations.models.Observation(
                    recorded_at=s['recorded_at'].isoformat(),
                    source=source,
                    additional={'dloadtime': s['dloadtime'].isoformat(),},
                    location=Point(x=s['longitude_at'], y=s['latitude_at']),
                )

            for i, s in missing_observations_results.iterrows():
                yield create_observation(s)

        end = start
        start = start - chunk_interval


def map_source_to_plugin (manufacturer_id, datasource=None, collar_type=None):
    if (datasource == 'localfile' and collar_type == 'AWT Satellite') \
            or manufacturer_id in unitlists.skyq_imeilist:
        # Associate with SkygisticsPlugin
        return SkygisticsSatellitePlugin.objects.get(name='ste-skygistics')
    elif datasource == 'HTTP':
        # AWT Http Plugin
        return AWTHttpPlugin.objects.get(name='awt-http-gsm')
    elif datasource == 'SavannahTrackingAPI':
        # SavannahTrackingPlugin
        return SavannahPlugin.objects.get(name='savannah')
    else:
        logger.info('No plugin identified for manufacturer_id %s', manufacturer_id)
        return None

def create_sourceplugin(source, latest_observation=None, datasource=None, collar_type=None):

    plugin = map_source_to_plugin(source.manufacturer_id, datasource, collar_type)

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
        sql = 'SELECT distinct(name) from trackingmaster order by name'
        at_cursor.execute(sql)
        rows = dictfetchall(at_cursor)

    error_list = []
    for animal in rows:
        try:
            import_trackingmaster_animal(animal['name'])
        except Exception as ex:
            error_list.append({'Animal {0} import error - {1}'.format(animal['name'], str(ex))})
            logging.exception('Failed to import TrackingMaster animal %s',animal['name'])
    return error_list

def import_all_subject_groups():
    error_list = []
    for group_name, query in ste.subject_groups.subject_group_query_map.items():
        try:
            import_subject_group(group_name, query)
        except Exception as ex:
            error_list.append({'Subject group {0} import error - {1}'.format(group_name, str(ex))})
    return error_list



def import_all():
    errors = []
    errors += import_all_chronofiles()
    errors += import_all_subject_groups()
    errors += import_all_users()
    print(errors)
