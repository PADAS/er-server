
import logging

from accounts.models import User
from activity.alerts import AlertUtils
from activity.models import Event
from activity.views import EventView
from django.conf import settings
from das_server import celery, mailer
from observations.views import SubjectView
from rt_api.rest_api_interface.dummy_request import DummyRequest
from utils import redis as redis_utils
import redis

logger = logging.getLogger(__name__)

LOCK_TIMEOUT = 300  # 5 minutes

REFRESH_USER_KEY = "{0}:queue"
REFRESH_USER_LOCK_KEY = "{0}:lock"

DELAY_PERIOD = 5  # seconds


@celery.app.task()
def send_user_event_notification(username, event_id, revision_id=None):
    # First load the user and the event
    user = User.objects.get(username=username)

    # Do a fake API request to make sure the user has
    # permission to view this event
    request = DummyRequest('/event/', 'GET', user=user)
    result = EventView.as_view()(request, id=event_id)
    if result.status_code != 200 or not result.data:
        return

    event = Event.objects.get(pk=event_id)

    for subject in event.subjects:
        request = DummyRequest('/subject/', 'GET', user=user)
        result = SubjectView.as_view()(request, id=str(subject.id))
        if result.status_code != 200 or not result.data:
            return

    if revision_id == None:
        if user.is_email_alert:
            mailer.send_event_mail(event, user, None)

        if user.is_sms_alert:
            mailer.send_new_event_sms(event, user)
    else:
        revision = event.revision.all_user().get(id=revision_id)
        if user.is_email_alert:
            mailer.send_event_mail(event, user, revision)

        if user.is_sms_alert:
            mailer.send_update_event_sms(event, revision, user)


@celery.app.task()
def event_change_cooldown_period(event_id):
    # Queue an update for the parent event and clear all updates for child
    # events
    changed_event = Event.objects.get(id=event_id)
    parent_event = Event.objects.filter(
        out_relationship__to_event=changed_event,
        out_relationship__type__value='contains').first() or changed_event

    child_events = Event.objects.filter(in_relationship__from_event=parent_event,
                                        in_relationship__type__value='contains')

    redis_client = redis.from_url(settings.CELERY_BROKER_URL)
    parent_key = REFRESH_USER_KEY.format(parent_event.id)
    redis_client.rpush(parent_key, 0)
    for child_event in child_events:
        redis_client.delete(REFRESH_USER_KEY.format(child_event.id))

    count = redis_client.llen(parent_key)
    notify_event.apply_async(
        args=(event_id, count), countdown=DELAY_PERIOD)


@celery.app.task()
def notify_event(event_id, queue_len):
    logger.info('event mailer event_id: {}'.format(event_id))

    redis_client = redis.from_url(settings.CELERY_BROKER_URL)
    key = REFRESH_USER_KEY.format(event_id)
    lock_key = REFRESH_USER_LOCK_KEY.format(event_id)
    count = redis_client.llen(key)

    if count and count == queue_len:
        with redis_utils.lock(redis_client, lock_key, LOCK_TIMEOUT) as l:
            if l and count and count == queue_len:
                try:
                    logger.debug("sending alert for %s", event_id)
                    send_alerts_for_event.delay(event_id)
                    logger.debug("Finished sending alert for %s", event_id)
                finally:
                    redis_client.ltrim(key, count, -1)


@celery.app.task()
def send_alerts_for_event(event_id):
    event = Event.objects.get(pk=event_id)

    # Get all priorities this alert has ever had
    priorities = []
    revisions = list(iter(event.revision.all_user().order_by('sequence')))
    for revision in revisions:
        if 'priority' in revision.data:
            priorities.append(revision.data['priority'])

    # Get alert user list based on priority history
    user_list = AlertUtils.get_alert_users(priorities)

    # Alert each user according to their contact preferences
    for user in user_list:
        celery.app.send_task(
            'das_server.tasks.send_user_event_notification', args=(user.username, event_id))
