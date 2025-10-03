import json
import logging
import random
import tempfile
from datetime import datetime, timedelta, timezone

import xmltodict
from asgiref.sync import async_to_sync
from celery_once import QueueOnce
from google.api_core import exceptions
from google.cloud import storage

from django.core.exceptions import ValidationError
from django.core.files.storage import default_storage
from django.db.models import F
from django.utils.translation import gettext as _

import utils.db.task_helpers as utils_db_task_helpers
from das_server import celery, pubsub
from observations.materialized_views import patrols_view
from observations.message_adapters import SendError, _handle_outbox_message
from observations.models import (
    Announcement,
    GPXTrackFile,
    Observation,
    Source,
    SourceProvider,
    Subject,
    SubjectStatus,
)
from observations.serializers import ObservationSerializer
from observations.utils import dateparse
from utils.tenant.celery import OverAllTenantTask, TenantQueueOnceTask

logger = logging.getLogger(__name__)

MAX_MAINTAIN_SUBJECTSTATUS_DELAY_SECONDS = 600


@celery.app.task(base=OverAllTenantTask, once={"graceful": True})
def maintain_subjectstatus_all():
    for subject_id in Subject.objects.filter(is_active=True).values_list("id", flat=True):
        maintain_subjectstatus_for_subject.apply_async(
            args=(str(subject_id),),
            countdown=random.randint(0, MAX_MAINTAIN_SUBJECTSTATUS_DELAY_SECONDS),
        )


@celery.app.task(
    base=TenantQueueOnceTask,
    once={
        "graceful": True,
    },
)
def maintain_subjectstatus_for_subject(subject_id, notify=False, **kwargs):
    """
    Maintenance task to ensure the subjectstatus is up to date for a subject.
    """
    SubjectStatus.objects.maintain_subject_status(subject_id)

    if notify:
        pubsub.publish({"subject_id": str(subject_id)}, "das.subjectstatus.update")


@celery.app.task(base=OverAllTenantTask, once={"graceful": True})
def maintain_observation_data():
    """Maintain observation data for all SourceProviders if they have the
    days_data_retain setting. For each matching SourceProvider a task maintain_observation_data_for_source_provider
    is queued.
    """
    for ssprovider in SourceProvider.objects.annotate(unique_id=F("id")):
        days_data_retain = ssprovider.additional.get("days_data_retain")
        if not days_data_retain:
            continue

        try:
            days_data_retain = int(days_data_retain)
        except ValueError:
            logger.warning(
                f"Mis-configured field days_data_retain {days_data_retain} not an integer for source_provider: {ssprovider.display_name}"
            )
            continue

        maintain_observation_data_for_source_provider.apply_async(args=(ssprovider.unique_id, days_data_retain))


DAYS_BACK_TO_SEARCH_OBSERVATION_PARTITIONS = 365


@celery.app.task(
    base=TenantQueueOnceTask,
    bind=True,
    once={
        "graceful": True,
    },
)
def maintain_observation_data_for_source_provider(
    self,
    source_provider_id: str,
    days_data_retain: int,
    search_back_days: int = DAYS_BACK_TO_SEARCH_OBSERVATION_PARTITIONS,
    **kwargs,
):
    """
    Delete observation records older than days_data_retain for a source_provider.
    Only go back DAYS_BACK_TO_SEARCH_OBSERVATION_PARTITIONS days to not search all Observation table partitions
    """
    if search_back_days < days_data_retain:
        logger.warning(
            f"search_back_days {search_back_days} is less than days_data_retain {days_data_retain} for source_provider_id: {source_provider_id}"
        )
        return

    current_datetime = datetime.now(timezone.utc)
    minimum_date = current_datetime - timedelta(days=days_data_retain)
    minimum_observation_partition_lower_bound = current_datetime - timedelta(days=search_back_days)

    logger.info(f"Deleting observation records older than {minimum_date} for source_provider_id: {source_provider_id}")

    for source_id in Source.objects.filter(provider_id=source_provider_id).values_list("id", flat=True):
        # Observation records older than minimum date
        observation_queryset = Observation.objects.filter(
            source_id=source_id,
            recorded_at__lte=minimum_date,
            recorded_at__gte=minimum_observation_partition_lower_bound,
        )

        observation_queryset.delete()


def parse_xml_to_dict(xml):
    try:
        xml_todict = xmltodict.parse(xml)
    except Exception as exc:
        message = f"Error occurred when parsing gpx file: {str(exc)} "
        logger.exception(message)
        return message
    else:
        to_json = json.dumps(xml_todict)
        return json.loads(to_json)


def get_track_points(gpx):
    try:
        trkpoint = gpx["gpx"]["trk"]["trkseg"]["trkpt"]
    except KeyError:
        message = "No track points were found in the file."
    except Exception as exc:
        message = f"Error occurred when getting trackpoints from gpx file: {str(exc)}"
        logger.exception(message)
    else:
        return trkpoint
    return message


def get_array_recorded_time(src, array_recorded_at):
    """Returns an array of trackpoints datetime that does not exist in observation table"""
    arr_obs = Observation.objects.filter(source=src, recorded_at__in=array_recorded_at).values_list(
        "recorded_at", flat=True
    )
    arr_recorded_at = set(array_recorded_at).difference(set(arr_obs))
    return arr_recorded_at


def validate_observation(location, recorded_at, source_id, additional, obs_persist, obs_errors):
    observation = {
        "location": location,
        "recorded_at": recorded_at,
        "source": str(source_id),
        "additional": additional,
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
        message = "Observations records already exists"
        return True, message


def process_trackpoints(source, source_id, trkpoints, file_name):
    error_msg = None

    try:
        list_gpx_datetime = [dateparse(trkp.get("time")) for trkp in trkpoints]
    except TypeError:
        error_msg = _("Points are missing timestamps in GPX file %s") % (file_name,)
    except Exception as exc:
        error_msg = _("Invalid timestamp, %s") % (exc,)

    if error_msg:
        return None, error_msg

    array_datetime = get_array_recorded_time(source, list_gpx_datetime)

    obs_records = []
    obs_errors = []
    for trkpt in trkpoints:
        recorded_at = dateparse(trkpt.get("time"))
        if recorded_at in array_datetime:
            lat = trkpt.get("@lat")
            lon = trkpt.get("@lon")
            location = {"latitude": float(lat), "longitude": float(lon)}
            additional = get_additional(trkpt)
            validate_observation(location, recorded_at, source_id, additional, obs_records, obs_errors)
            array_datetime.remove(recorded_at)
        else:
            logger.info(f"Ignored observation record of recorded_at: {recorded_at} and source: {source}")

    return obs_records, obs_errors


def get_additional(trkpoint):
    keys = ["@lat", "@lon", "time"]
    [trkpoint.pop(i) for i in keys]
    return trkpoint


def success_process_gpxtrack(gpx_id, message):
    # get length of observations from message
    count = "".join(filter(str.isdigit, message))
    points_imported = int(count) if count else "0 (All Duplicates)"

    return GPXTrackFile.objects.filter(id=gpx_id).update(processed_status="success", points_imported=points_imported)


def failed_process_gpxtrack(gpx_id, error_msg=None):
    return GPXTrackFile.objects.filter(id=gpx_id).update(
        processed_status="failure", status_description=error_msg, points_imported=0
    )


@celery.app.task(base=TenantQueueOnceTask, once={"graceful": True})
def process_gpxtrack_file(gpx_id, **kwargs):
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


@celery.app.task(base=TenantQueueOnceTask, once={"graceful": True}, bind=True, track_started=True, ignore_result=False)
def process_gpxdata_api(self, filename, source_id, **kwargs):
    with default_storage.open(filename, "r") as file:
        data = file.read()

        response = parse_xml_to_dict(data)
        if isinstance(response, str):
            raise ValidationError(response)

        trkpoints = get_track_points(response)
        if isinstance(trkpoints, str):
            raise ValidationError(trkpoints)

    source = Source.objects.get(id=source_id)

    file_name = filename.split("/")[-1]
    obs_records, obs_errors = process_trackpoints(source, source_id, trkpoints, file_name)

    status, message = process_observation(observation_records=obs_records, observation_errors=obs_errors)
    if status:
        return message
    else:
        raise ValidationError(message)


@celery.app.task(base=OverAllTenantTask, once={"graceful": True})
def refresh_patrols_view():
    # FIXME By the time we consolidate all tenants in one DB we require rework on the DB view that refresh_view hit.
    patrols_view.refresh_view()


@celery.app.task(base=TenantQueueOnceTask, bind=True, once={"graceful": True}, max_retries=10)
def handle_outbox_message(self, message_id, user_email, **kwargs):
    try:
        _handle_outbox_message(message_id, user_email)
    except SendError as exc:
        logger.error("SendError in task handle_outbox_message %s", exc)
        self.retry(exc=exc, retry_backoff=True)


@celery.app.task(base=OverAllTenantTask, once={"graceful": True})
def poll_news_gcs_bucket():
    """poll record topics from GCS bucket"""

    blob_name = "topic_feeds.json"
    bucket_name = "er_notifications"

    try:
        storage_client = storage.Client()
    except exceptions.GoogleAPIError:
        return

    try:
        bucket = storage_client.get_bucket(bucket_name)
    except exceptions.GoogleAPIError as exc:
        logger.info(f"Error occured when getting bucket {bucket_name} -> {exc}")
        return

    with tempfile.NamedTemporaryFile(delete=False) as f:
        blob = bucket.blob(blob_name)
        storage_client.download_blob_to_file(blob, f)
        f.flush()
        f.seek(0)

        announcement = json.loads(f.read())

    logger.debug(f"Announcements data from gcs {announcement}")

    for post in announcement["topic_list"]["topics"]:
        # skip any posts missing the 'cooked' property
        if "cooked" not in post:
            continue

        # ignore announcements if they are already in the DB:
        if Announcement.objects.filter(additional__id=post["id"]).exists():
            continue

        announcement_at = dateparse(post["created_at"])
        Announcement.objects.create(
            title=post["title"],
            description=post["cooked"],
            additional=dict(
                slug=post["slug"],
                id=post["id"],
                fancy_title=post["fancy_title"],
                created_at=post["created_at"],
                category_id=post["category_id"],
                last_poster_username=post["last_poster_username"],
            ),
            announcement_at=announcement_at,
            link=f"https://community.earthranger.com/t/{post['id']}",
        )


@celery.app.task(
    base=QueueOnce,
    default_retry_delay=60,
    max_retries=5,
    retry_backoff=30,
    retry_backoff_max=10 * 60,
)
def run_partition_table_check() -> None:
    """
    Run the partition table check on the observations_observation table.
    """
    table_name = "observations_observation"
    schema = "public"
    logger.info(f"Running partition table check for '{schema}.{table_name}'")
    utils_db_task_helpers.run_partition_table_check(schema=schema, table_name=table_name, logger=logger)


@celery.app.task(
    base=TenantQueueOnceTask,
    bind=True,
    once={"graceful": True},
    max_retries=5,
    default_retry_delay=60,
    retry_backoff=30,
    retry_backoff_max=10 * 60,
)
def send_observations_to_gundi_async(self, observations, integration_id, **kwargs):
    """
    Send observations to Gundi asynchronously using Celery task.
    This provides retry logic and doesn't block the API endpoint.

    :param observations: List of observation dictionaries to send to Gundi
    :param integration_id: UUID of the Gundi integration
    :param kwargs: Additional parameters
    """
    try:
        from observations.services.gundi import send_observations_to_gundi

        logger.info("Sending %d observations to Gundi with integration_id: %s", len(observations), integration_id)

        # Convert async function to sync using async_to_sync
        result = async_to_sync(send_observations_to_gundi)(observations=observations, integration_id=integration_id)

        logger.info("Successfully sent %d observations to Gundi. Result: %s", len(observations), result)

        return result

    except Exception as exc:
        logger.error(
            "Failed to send observations to Gundi (attempt %d/%d): %s",
            self.request.retries + 1,
            self.max_retries + 1,
            exc,
        )
        self.retry(exc=exc, retry_backoff=True)
