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
from observations.utils import dateparse



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
        logger.exception(f"Exception raised {exc} when converting gpx-xml to dictionary.")
    else:
        to_json = json.dumps(xml_todict)
        return json.loads(to_json)


def get_track_points(gpx):
    try:
        trkpoint = gpx['gpx']['trk']['trkseg']['trkpt']
    except Exception as exc:
        logger.exception(f"Exception raised {exc} when getting trackpoint")
    else:
        return trkpoint


def check_if_observation_exist(recorded_at, src):
    Observation.objects.filter(source=src, recorded_at=recorded_at).exists()


def validate_observation(location, recorded_at, source_id, additional, obs_persist):
    observation = {
        'location': location,
        'recorded_at': recorded_at,
        'source': str(source_id),
        'additional': additional,
    }
    validator = ObservationSerializer(data=observation)
    if validator.is_valid():
        obs_persist.append(observation)
        logger.info(f"Added new observation record {observation}")
    else:
        logger.error(f"Observation validation failed {validator.errors}")


def get_additional(trkpoint):
    keys = ['@lat', '@lon', 'time']
    [trkpoint.pop(i) for i in keys]
    return trkpoint


@celery.app.task
def process_gpxtrack_file(gpx_id):
    gpx_file = GPXTrackFile.objects.get_file(gpx_id)
    data = gpx_file.read()
    to_dict = parse_xml_to_dict(data)
    if not to_dict:
        return
    trkpoints = get_track_points(to_dict)
    if not trkpoints:
        return

    source_id = GPXTrackFile.objects.get_source_id(gpx_id)
    obs_records = []

    for trkpt in trkpoints:
        recorded_at = dateparse(trkpt.get('time'))
        source = Source.objects.get(id=source_id)
        if not check_if_observation_exist(recorded_at, source):
            lat = trkpt.get('@lat')
            lon = trkpt.get('@lon')
            location = {'latitude': float(lat), 'longitude': float(lon)}
            additional = get_additional(trkpt)
            validate_observation(location, recorded_at, source_id, additional, obs_records)

    if obs_records:
        bulk_serializer = ObservationSerializer(data=obs_records, many=True)
        if bulk_serializer.is_valid():
            bulk_serializer.save()
            logger.info(f"Successfully created bulky observations {len(obs_records)}")
        else:
            logger.error(f"Failed to process bulk observation: {bulk_serializer.errors}")
