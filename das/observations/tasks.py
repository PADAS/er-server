import os
import logging
import json
import xmltodict
from datetime import datetime, timedelta
import pytz

from celery_once import QueueOnce
from das_server import celery, pubsub
from observations import servicesutils
from observations.models import Subject, SubjectStatus, Observation, SourceProvider, Source, GPXTrackFile
from observations.serializers import ObservationSerializer
from django.db.models import F
from django.core.exceptions import ValidationError
from observations.utils import dateparse
from django.core.files.storage import default_storage
from django.utils.translation import gettext as _


logger = logging.getLogger(__name__)


@celery.app.task()
def store_and_forward_service_status(provider_key=None, data=None):

    data = data or {}
    servicesutils.store_service_status(provider_key=provider_key, data=data)


@celery.app.task(base=QueueOnce, once={'graceful': True})
def maintain_subjectstatus_all():
    for subject in Subject.objects.filter(is_active=True).values('id'):
        maintain_subjectstatus_for_subject.apply_async(
            args=(str(subject['id']),))


@celery.app.task(base=QueueOnce, once={'graceful': True, })
def maintain_subjectstatus_for_subject(subject_id):

    SubjectStatus.objects.maintain_subject_status(subject_id)


@celery.app.task
def maintain_observation_data():
    for ssprovider in SourceProvider.objects.annotate(unique_id=F('id')):
        days_data_retain = ssprovider.additional.get('days_data_retain')
        if not days_data_retain:
            continue
        try:
            days_data_retain = int(days_data_retain)
        except ValueError:
            logger.warning(
                f'Mis-configured field days_data_retain {days_data_retain} not an integer for source_provider: {ssprovider.display_name}'
            )
            continue

        minimum_date = pytz.utc.localize(
            datetime.utcnow()) - timedelta(days=days_data_retain)

        # Observation records older than minimum date
        observation_queryset = Observation.objects.filter(
            source__provider__id=ssprovider.unique_id, recorded_at__lte=minimum_date)

        if observation_queryset.exists():
            observation_queryset.delete()


def parse_xml_to_dict(xml):
    try:
        xml_todict = xmltodict.parse(xml)
    except Exception as exc:
        message = f"Error occurred: {repr(exc)} when parsing gpx file."
        logger.exception(message)
        return message
    else:
        to_json = json.dumps(xml_todict)
        return json.loads(to_json)


def get_track_points(gpx):
    try:
        trkpoint = gpx['gpx']['trk']['trkseg']['trkpt']
    except KeyError:
        message = "No track points were found in the file."
    except Exception as exc:
        message = f"Error occurred: {repr(exc)} when getting trackpoints from gpx file"
        logger.exception(message)
    else:
        return trkpoint
    return message


def get_array_recorded_time(src, array_recorded_at):
    """Returns an array of trackpoints datetime that does not exist in observation table"""
    arr_obs = Observation.objects.filter(source=src,
                                         recorded_at__in=array_recorded_at).values_list('recorded_at', flat=True)
    arr_recorded_at = set(array_recorded_at).difference(set(arr_obs))
    return arr_recorded_at


def validate_observation(location, recorded_at, source_id, additional, obs_persist, obs_errors):
    observation = {
        'location': location,
        'recorded_at': recorded_at,
        'source': str(source_id),
        'additional': additional,
    }
    validator = ObservationSerializer(data=observation)
    if validator.is_valid():
        obs_persist.append(observation)
        logger.debug(f"Added new observation record {observation}")
    else:
        obs_errors.append(validator.errors)
        logger.error(f"Observation validation failed {validator.errors}")


def process_observation(observation_records, observation_errors):
    if observation_records:
        bulk_serializer = ObservationSerializer(data=observation_records, many=True)
        if bulk_serializer.is_valid():
            bulk_serializer.save()
            message = f"Successfully created {len(observation_records)} observations"
            logger.info(message)
            return True, message
        else:
            message = f"Failed to process bulk observation: {bulk_serializer.errors}"
            logger.error(message)
            return False, message
    elif observation_errors:
        message = f"Failed to process observation: {observation_errors}"
        logger.error(message)
        return False, message
    else:
        message = 'Observations records already exists'
        return True, message


def process_trackpoints(source, source_id, trkpoints, file_name):
    error_msg = None

    try:
        list_gpx_datetime = [dateparse(trkp.get('time')) for trkp in trkpoints]
    except TypeError:
        error_msg = _('Points are missing timestamps in GPX file %s') % (file_name, )
    except Exception as exc:
        error_msg = _('Invalid timestamp, %s') % (exc, )

    if error_msg:
        return None, error_msg

    array_datetime = get_array_recorded_time(source, list_gpx_datetime)

    obs_records = []
    obs_errors = []
    for trkpt in trkpoints:
        recorded_at = dateparse(trkpt.get('time'))
        if recorded_at in array_datetime:
            lat = trkpt.get('@lat')
            lon = trkpt.get('@lon')
            location = {'latitude': float(lat), 'longitude': float(lon)}
            additional = get_additional(trkpt)
            validate_observation(location, recorded_at, source_id, additional, obs_records, obs_errors)
            array_datetime.remove(recorded_at)
        else:
            logger.info(f"Ignored observation record of recorded_at: {recorded_at} and source: {source}")

    return obs_records, obs_errors


def get_additional(trkpoint):
    keys = ['@lat', '@lon', 'time']
    [trkpoint.pop(i) for i in keys]
    return trkpoint


def success_process_gpxtrack(gpx_id, message):
    # get length of observations from message
    count = ''.join(filter(str.isdigit, message))
    points_imported = int(count) if count else '0 (All Duplicates)'

    return GPXTrackFile.objects.filter(id=gpx_id).update(
        processed_status='success',
        points_imported=points_imported)


def failed_process_gpxtrack(gpx_id, error_msg=None):
    return GPXTrackFile.objects.filter(id=gpx_id).update(
        processed_status='failure',
        status_description=error_msg,
        points_imported=0)


@celery.app.task
def process_gpxtrack_file(gpx_id):
    gpx_file, file_name = GPXTrackFile.objects.get_file(gpx_id)
    data = gpx_file.read()
    response = parse_xml_to_dict(data)
    if isinstance(response, str):
        failed_process_gpxtrack(gpx_id, response)
        return
    trkpoints = get_track_points(response)
    if isinstance(trkpoints, str):
        failed_process_gpxtrack(gpx_id, trkpoints)
        return

    source_id = GPXTrackFile.objects.get_source_id(gpx_id)
    source = Source.objects.get(id=source_id)
    obs_records, obs_errors = process_trackpoints(source, source_id, trkpoints, file_name)

    status, message = process_observation(observation_records=obs_records, observation_errors=obs_errors)
    if status:
        success_process_gpxtrack(gpx_id, message)
    else:
        if obs_records is None:
            failed_process_gpxtrack(gpx_id, obs_errors)
        else:
            failed_process_gpxtrack(gpx_id)


@celery.app.task(bind=True, track_started=True, ignore_result=False)
def process_gpxdata_api(self, filename, source_id):
    with default_storage.open(filename, 'r') as file:
        data = file.read()

        response = parse_xml_to_dict(data)
        if isinstance(response, str):
            raise ValidationError(response)

        trkpoints = get_track_points(response)
        if isinstance(trkpoints, str):
            raise ValidationError(trkpoints)

    source = Source.objects.get(id=source_id)

    file_name = filename.split('/')[-1]
    obs_records, obs_errors = process_trackpoints(source, source_id, trkpoints, file_name)

    status, message = process_observation(observation_records=obs_records, observation_errors=obs_errors)
    if status:
        return message
    else:
        raise ValidationError(message)
