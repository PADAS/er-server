import json
import logging

import requests
from celery_once import QueueOnce
from requests.exceptions import Timeout
from rest_framework import status

from analyzers import gfw_inbound
from analyzers.exceptions import InsufficientDataAnalyzerException
from analyzers.finder import get_subject_analyzers
from analyzers.gfw_alert_schema import GFWGladEventTypeSpec
from analyzers.gfw_utils import get_geostore_id, rebuild_glad_download_url
from analyzers.models import GlobalForestWatchSubscription as gfw_model
from analyzers.models import ObservationAnnotator
from das_server import celery
from observations.models import Subject

logger = logging.getLogger(__name__)


def get_active_subject(subject_id):
    # Check existence of active subject object with provided subject_id
    try:
        if Subject.objects.get(id=subject_id, is_active=True):
            return True
    except Subject.DoesNotExist as e:
        logger.error('No active Subject found with id=%s', subject_id)
        return False


@celery.app.task(base=QueueOnce, once={'graceful': True, 'timeout': 3 * 60})
def handle_subject(subject_id):
    """
    Subject-centric task to run when new observations are recorded.

    Using QueueOnce as a base-class to squash a succession of tasks for the same subject_id.
    """
    subject_id = str(subject_id)
    logger.info('Handling subject %s', subject_id)

    # Call annotator first
    annotate_observations_for_subject(subject_id)

    # Queue analyzer tasks.
    analyze_subject.apply_async(args=(subject_id,))


@celery.app.task()
def handle_source(source_id):
    logger.info('Handling source %s', str(source_id))

    subjects = Subject.objects.get_current_subjects_from_source_id(
        source_id=source_id, values=('id', 'name'))

    for subject in subjects:
        subject_id = subject['id']

        # Execute in one minute, which will allow squashing a succession of observations for a single subject.
        # See 'handle_subject' and it's use of QueueOnce to do the squashing.
        if get_active_subject(subject_id):
            handle_subject.apply_async(args=(subject_id,), countdown=60)


@celery.app.task(base=QueueOnce)
def analyze_subject(subject_id):
    subject = None
    logger.info('Analyze subject for id=%s', subject_id)
    try:
        subject = Subject.objects.get(id=subject_id, is_active=True)
    except Subject.DoesNotExist:
        logger.warning(
            'No active Subject found by ID in analyze_subject. id=%s',
            subject_id)

    if subject:
        logger.info('Running analyzers for subject: %s', subject)
        for analyzer in get_subject_analyzers(subject):

            try:
                analyzer_results = analyzer.analyze()
                for result in analyzer_results:
                    logger.debug('Analyzer Result: %s', result[0])

            except InsufficientDataAnalyzerException:
                logger.warning(
                    'insufficient observations exist to support analyzer {}'.format(
                        analyzer))
            except Exception:
                logger.exception(
                    'Programming error in analyzer. analyzer=%s', analyzer)


@celery.app.task()
def annotate_observations_for_subject(subject_id):
    logger.debug('Annotating observations for subject: %s', str(subject_id))

    try:
        sub = Subject.objects.get(id=subject_id)
        annotator = ObservationAnnotator.get_for_subject(sub)
        if annotator:
            annotator.annotate()

    except Subject.DoesNotExist:
        logger.warning(
            'Unable to run annotation for subject ID: %s, because it does not exist.',
            subject_id)
        return


@celery.app.task()
def handle_observation(observation_id):
    logger.debug('Handling observation: %s', observation_id)

    subjects = Subject.objects.get_subjects_from_observation_id(
        observation_id, values=('id', 'name'))

    if not subjects:
        logger.debug(
            'Handling observation %s, but it has no associated subject.',
            observation_id)

    for subject in subjects:
        subject_id = subject['id']

        # Execute in one minute, which will allow squashing a succession of observations for a single subject.
        # See 'handle_subject' and it's use of QueueOnce to do the squashing.
        if get_active_subject(subject_id):
            handle_subject.apply_async(args=(subject_id,), countdown=60)


@celery.app.task(bind=True, max_retries=5)
def download_gfw_alerts(self, download_url, common_event_fields, user_id):
    try:
        connect_timeout, read_timeout = 3, 30
        logger.info('Processing GFW payload for %s. Downloading from: %s',
                    common_event_fields.get('event_type'),
                    download_url)
        resp = requests.get(url=download_url,
                            timeout=(connect_timeout, read_timeout))
    except Timeout as tex:
        # TODO: revisit to figure out other failures that should be retried.
        logger.exception('Failed downloading GFW alert data for url: %s',
                         download_url,
                         extra={'Exception': tex})
        self.retry(countdown=60)
    except Exception as ex:
        logger.exception('Failed downloading GFW alert data for url: %s',
                         download_url,
                         extra={'Exception': ex})
    else:
        if resp and resp.status_code == status.HTTP_200_OK:
            gfw_alerts_payload = json.loads(resp.text)
            gfw_alerts_payload = {
                "data": [
                    {
                        "year": 2019,
                        "long": 22.246625000000066,
                        "lat": -1.3636250000000303,
                        "julian_day": 183,
                        "confidence": 3
                    },
                    {
                        "year": 2019,
                        "long": 22.402625000000064,
                        "lat": -1.3696250000000303,
                        "julian_day": 183,
                        "confidence": 3
                    },
                    {
                        "year": 2019,
                        "long": 22.251375000000063,
                        "lat": -1.3943750000000301,
                        "julian_day": 183,
                        "confidence": 3
                    },
                    {
                        "year": 2019,
                        "long": 22.479625000000063,
                        "lat": -1.3998750000000302,
                        "julian_day": 183,
                        "confidence": 3
                    },
                    {
                        "year": 2019,
                        "long": 22.475875000000066,
                        "lat": -1.4003750000000301,
                        "julian_day": 183,
                        "confidence": 3
                    },
                    {
                        "year": 2019,
                        "long": 22.199125000000063,
                        "lat": -1.4016250000000303,
                        "julian_day": 183,
                        "confidence": 3
                    },
                    {
                        "year": 2019,
                        "long": 22.198625000000064,
                        "lat": -1.4018750000000302,
                        "julian_day": 183,
                        "confidence": 3
                    },
                    {
                        "year": 2019,
                        "long": 22.343125000000065,
                        "lat": -1.4088750000000303,
                        "julian_day": 183,
                        "confidence": 3
                    },
                    {
                        "year": 2019,
                        "long": 22.343375000000066,
                        "lat": -1.4088750000000303,
                        "julian_day": 183,
                        "confidence": 3
                    },
                    {
                        "year": 2019,
                        "long": 22.273375000000065,
                        "lat": -1.4103750000000301,
                        "julian_day": 183,
                        "confidence": 3
                    },
                    {
                        "year": 2019,
                        "long": 22.340875000000064,
                        "lat": -1.4136250000000303,
                        "julian_day": 183,
                        "confidence": 3
                    },
                    {
                        "year": 2019,
                        "long": 22.260625000000065,
                        "lat": -1.4181250000000303,
                        "julian_day": 183,
                        "confidence": 3
                    },
                    {
                        "year": 2019,
                        "long": 22.487125000000063,
                        "lat": -1.4271250000000302,
                        "julian_day": 183,
                        "confidence": 3
                    },
                    {
                        "year": 2019,
                        "long": 22.299375000000065,
                        "lat": -1.4521250000000303,
                        "julian_day": 183,
                        "confidence": 3
                    },
                    {
                        "year": 2019,
                        "long": 22.299625000000063,
                        "lat": -1.4521250000000303,
                        "julian_day": 183,
                        "confidence": 3
                    },
                    {
                        "year": 2019,
                        "long": 22.299375000000065,
                        "lat": -1.4523750000000302,
                        "julian_day": 183,
                        "confidence": 3
                    },
                    {
                        "year": 2019,
                        "long": 22.299625000000063,
                        "lat": -1.4523750000000302,
                        "julian_day": 183,
                        "confidence": 3
                    },
                    {
                        "year": 2019,
                        "long": 22.376875000000066,
                        "lat": -1.4533750000000303,
                        "julian_day": 183,
                        "confidence": 3
                    },
                    {
                        "year": 2019,
                        "long": 22.377625000000066,
                        "lat": -1.4533750000000303,
                        "julian_day": 183,
                        "confidence": 3
                    },
                    {
                        "year": 2019,
                        "long": 22.463875000000066,
                        "lat": -1.4723750000000302,
                        "julian_day": 183,
                        "confidence": 3
                    },
                    {
                        "year": 2019,
                        "long": 22.463875000000066,
                        "lat": -1.4726250000000303,
                        "julian_day": 183,
                        "confidence": 3
                    },
                    {
                        "year": 2019,
                        "long": 22.070625000000064,
                        "lat": -2.0513750000000304,
                        "julian_day": 183,
                        "confidence": 3
                    }
                ]
            }
            data_field = 'data' if common_event_fields.get(
                'event_type') == GFWGladEventTypeSpec.value else 'rows'
            if gfw_alerts_payload.get(data_field) is not None:
                alert_data = gfw_alerts_payload.get(data_field)
                logger.info('Valid response from GFW. %d alerts received.',
                            len(alert_data))
                logger.info('First alert payload %s', alert_data[0]) if len(
                    alert_data) else None
                gfw_inbound.process_downloaded_alerts(alert_data,
                                                      common_event_fields,
                                                      user_id)
            else:
                logger.error('GFW API returned error: %s', gfw_alerts_payload)
        else:
            logger.error(
                'GFW Alerts cannot be downloaded. Result is %s, \ndownload url is: %s\n Response is: %s',
                resp.status_code, download_url, resp.text)
