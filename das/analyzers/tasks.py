import json
import logging
import textwrap
from datetime import datetime

import requests
from celery_once import QueueOnce
from django.core.cache import cache
from requests.exceptions import Timeout
from rest_framework import status

from analyzers import gfw_inbound
from analyzers.exceptions import InsufficientDataAnalyzerException
from analyzers.finder import get_subject_analyzers
from analyzers.gfw_alert_schema import GFWGladEventTypeSpec
from analyzers.gfw_utils import get_gfw_user, make_alert_infos
from analyzers.models import GlobalForestWatchSubscription as gfw_model
from analyzers.models import ObservationAnnotator
from analyzers.utils import get_analyzer_key
from das_server import celery
from observations.models import Subject
from observations.utils import convert_date_string

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
            'No active Subject found by ID in analyze_subject. id=%s', subject_id)

    if subject:
        logger.info('Running analyzers for subject: %s', subject)
        for analyzer in get_subject_analyzers(subject):
            analyzer_key = get_analyzer_key(analyzer, subject)
            if analyzer_key and cache.get(analyzer_key):
                logger.info(
                    f"The analyzer {analyzer.config.id} is quiet for a while")
                continue

            try:
                analyzer_results = analyzer.analyze(analyzer_key=analyzer_key)
                for result in analyzer_results:
                    logger.debug('Analyzer Result: %s', result[0])

            except InsufficientDataAnalyzerException:
                logger.warning(
                    'insufficient observations exist to support analyzer {}'.format(analyzer))
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
            'Unable to run annotation for subject ID: %s, because it does not exist.', subject_id)
        return


@celery.app.task()
def handle_observation(observation_id):

    logger.debug('Handling observation: %s', observation_id)

    subjects = Subject.objects.get_subjects_from_observation_id(
        observation_id, values=('id', 'name'))

    if not subjects:
        logger.debug(
            'Handling observation %s, but it has no associated subject.', observation_id)

    for subject in subjects:
        subject_id = subject['id']

        # Execute in one minute, which will allow squashing a succession of observations for a single subject.
        # See 'handle_subject' and it's use of QueueOnce to do the squashing.
        if get_active_subject(subject_id):
            handle_subject.apply_async(args=(subject_id,), countdown=60)


@celery.app.task(bind=True, max_retries=5)
def download_gfw_alerts(self, download_url, event_dict, user_id):
    subscription_id = event_dict['event_details']['subscription_id']
    try:
        model = gfw_model.objects.get(subscription_id=subscription_id)
    except gfw_model.DoesNotExist:
        logger.error(
            f"{subscription_id} does not exist in database. Aborting download")
        return
    else:
        result = fetch_alerts(self, event_dict, download_url, user_id)
        update_status(model, result)


@celery.app.task()
def poll_gfw():
    gfw_user = get_gfw_user()
    for layer_slug, gfw_subscription in get_model_slug_pairs():
        for alert_info in make_alert_infos(layer_slug, gfw_subscription):
            logger.info(
                f'poll_gfw for {gfw_subscription.name} {layer_slug} download url: {alert_info["downloadUrls"]["json"]}')
            gfw_inbound.process_alert_for_subscription(layer_slug,
                                                       gfw_subscription.subscription_id,
                                                       alert_info,
                                                       str(gfw_user.id),
                                                       True)


def fetch_alerts(self, event_dict, download_url, user_id):
    try:
        connect_timeout, read_timeout = 3, 30
        if event_dict.get('event_type') == GFWGladEventTypeSpec.value:
            logger.info('Processing GFW payload for %s. Downloading from: %s', event_dict.get('event_type'),
                        download_url)
            resp = requests.get(url=download_url, timeout=(
                connect_timeout, read_timeout))
        else:
            base_url, param = download_url['URL'], download_url['param']
            logger.info('Processing GFW payload for %s. Downloading from query params: %s',
                        event_dict.get('event_type'),
                        download_url)
            resp = requests.post(url=base_url, data=param,
                                 timeout=(connect_timeout, read_timeout))
    except Timeout as tex:
        # TODO: revisit to figure out other failures that should be retried.
        logger.exception('Failed downloading GFW alert data for url: %s', download_url,
                         extra={'Exception': tex})
        self.retry(countdown=60)
        result = f'Failure: {tex}'
    except Exception as ex:
        logger.exception('Failed downloading GFW alert data for url: %s', download_url,
                         extra={'Exception': ex})
        result = f'Failure: {ex}'
    else:
        result = process_response(event_dict, download_url, resp, user_id)
    return result


def process_response(event_dict, download_url, http_response, user_id):
    if http_response and http_response.status_code == status.HTTP_200_OK:
        gfw_alerts_payload = json.loads(http_response.text)
        data_field = 'data' if event_dict.get(
            'event_type') == GFWGladEventTypeSpec.value else 'rows'
        if gfw_alerts_payload.get(data_field) is not None:
            alert_data = gfw_alerts_payload.get(data_field)
            logger.info(
                'Valid response from GFW. %d alerts received.', len(alert_data))
            logger.info('First alert payload %s', alert_data[0]) if len(
                alert_data) else None
            gfw_inbound.process_downloaded_alerts(
                alert_data, event_dict, user_id)
            result = 'Success'
        else:
            logger.error('GFW API returned error: %s', gfw_alerts_payload)
            result = f'Failure: {gfw_alerts_payload}'
    else:
        logger.error('GFW Alerts cannot be downloaded. Result is %s, \ndownload url is: %s\n Response is: %s',
                     http_response.status_code, download_url, http_response.text)
        result = f'Failure: {http_response.text}'
    return result


def get_model_slug_pairs():
    for subscription in gfw_model.objects.all():
        for slug in subscription.additional['alert_types']:
            yield slug, subscription


def update_status(model, status_message):
    model.last_check_time = convert_date_string(str(datetime.now()))
    model.last_check_status = textwrap.shorten(status_message,
                                               gfw_model._meta.get_field('last_check_status').max_length)
    model.save()
