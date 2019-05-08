
import logging

from accounts.models import User
from activity.alerts import get_alert_users
from activity.models import Event
from activity.views import EventView
from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist
from das_server import celery, mailer
from observations.views import SubjectView
from rt_api.rest_api_interface.dummy_request import DummyRequest
from utils import redis as redis_utils
import redis

logger = logging.getLogger(__name__)

LOCK_TIMEOUT = 30  # seconds

REFRESH_USER_KEY = "{0}:queue"
REFRESH_USER_LOCK_KEY = "{0}:lock"

EVENT_REVISION_KEY = "e;{0}"
DETAILS_REVISION_KEY = "d;{0};{1}"

DELAY_PERIOD = 5  # seconds


@celery.app.task()
def queue_event_alert(event_id):
    event = Event.objects.get(id=event_id)
    revision = event.revision.all_user().order_by('sequence').last()
    try:
        details_revision = event.event_details.order_by('updated_at').last(
        ).revision.all_user().order_by('sequence').last()
    except AttributeError:
        event_change_cooldown_period(event_id, revision, None)
        return

    # We end up in this code path in a few ways. Some data associated with the
    # event has changed, but it could be the event itself or the event_details
    # which contains the schema data. Or it could be both. It all depends on
    # what fields were changed in the event update.
    #
    # To figure out what change(s) brought us here, we need to look at the
    # timestamps on the latest revisions to both the event and eventdetails
    # objects and see which one is newer.
    diff = (revision.revision_at - details_revision.revision_at).total_seconds()

    # If the timestamps are < 1 second apart, they were very likely made
    # together
    if abs(diff) < 1:
        event_change_cooldown_period(
            event_id, revision, details_revision)
    # If the changes are farther apart, take the later one only
    elif diff < 0:
        event_change_cooldown_period(event_id, None, details_revision)
    else:
        event_change_cooldown_period(event_id, revision, None)


def event_change_cooldown_period(event_id, event_revision=None, details_revision=None):
    """
    Instead of sending an alert immediately, wait a few seconds in case other
    updates come through, then send all updates in one single alert
    """

    # We always want to alert for the parent event if there is one, so do some
    # queries to figure out the event hierarchy
    redis_client = redis.from_url(settings.CELERY_BROKER_URL)
    changed_event = Event.objects.get(id=event_id)
    parent_event = Event.objects.filter(
        out_relationship__to_event=changed_event,
        out_relationship__type__value='contains').first() or changed_event

    child_events = Event.objects.filter(in_relationship__from_event=parent_event,
                                        in_relationship__type__value='contains')

    # Save all the revision ids under the parent event's kay in redis
    parent_key = REFRESH_USER_KEY.format(parent_event.id)
    consolidate_all_child_alerts_into_parent(parent_event, child_events)
    if event_revision is not None:
        redis_client.rpush(parent_key,
                           EVENT_REVISION_KEY.format(event_revision.id))
    if details_revision is not None:
        redis_client.rpush(parent_key,
                           DETAILS_REVISION_KEY.format(details_revision.id, details_revision.object_id))

    # In DELAY_PERIOD seconds, send an alert if there hasn't been any more
    # churn
    count = redis_client.llen(parent_key)
    check_event_activity.apply_async(
        args=(event_id, count), countdown=DELAY_PERIOD)


def consolidate_all_child_alerts_into_parent(parent_key, child_events):
    redis_client = redis.from_url(settings.CELERY_BROKER_URL)

    for child_event in child_events:
        child_event_key = REFRESH_USER_KEY.format(child_event.id)
        while redis_client.llen(child_event_key) > 0:
            redis_client.rpush(parent_key, redis_client.rpop(child_event_key))
        redis_client.delete(child_event_key)


@celery.app.task()
def check_event_activity(event_id, queue_len):
    logger.info('Event mailer for Event ID %s', event_id)

    redis_client = redis.from_url(
        settings.CELERY_BROKER_URL, decode_responses=True)
    key = REFRESH_USER_KEY.format(event_id)

    # quick check to see if it's worth acquiring a lock, we'll do a threadsafe
    # check after we get the lock
    count = redis_client.llen(key)
    if count and count == queue_len:
        lock_key = REFRESH_USER_LOCK_KEY.format(event_id)
        with redis_utils.lock(redis_client, lock_key, LOCK_TIMEOUT) as l:
            if l and redis_client.llen(key) == queue_len:
                try:
                    logger.debug("sending alert for %s", event_id)
                    queue_alert_for_all_users.delay(
                        event_id, redis_client.lrange(key, 0, count))
                    logger.debug("Finished sending alert for %s", event_id)
                finally:
                    redis_client.ltrim(key, count, -1)


@celery.app.task()
def queue_alert_for_all_users(event_id, revision_ids):
    event = Event.objects.get(pk=event_id)

    priorities = {event.priority}
    for revision_id in revision_ids:
        rev_info = revision_id.split(';')
        if rev_info[1] == '0' or rev_info[0] == 'd':
            continue
        try:
            revision = event.revision.all_user().get(id=rev_info[1])
            if revision and 'priority' in revision.data:
                priorities.add(revision.data['priority'])
        except ObjectDoesNotExist:
            pass

    logger.info('Sending Event Alert for Event %s for revisions (%s)', f'{event.serial_number}: {event.title}', revision_ids)

    # Get alert user list based on priority history
    user_list = get_alert_users(priorities)

    for user in user_list:
        celery.app.send_task(
            'das_server.tasks.send_alert_to_specific_user', args=(user.username, event_id, revision_ids))


@celery.app.task()
def send_alert_to_specific_user(username, event_id, revision_ids=None):
    user = User.objects.get(username=username)
    event = Event.objects.get(pk=event_id)

    # Fake API requests to apply user's permissions
    request = DummyRequest('/event/', 'GET', user=user)
    result = EventView.as_view()(request, id=event_id)
    if result.status_code != 200 or not result.data:
        return

    for subject in event.related_subjects.all():
        request = DummyRequest('/subject/', 'GET', user=user)
        result = SubjectView.as_view()(request, id=str(subject.id))
        if result.status_code != 200 or not result.data:
            return

    if user.is_email_alert:
        mailer.send_event_mail(event, user, revision_ids)

    if user.is_sms_alert:
        mailer.send_event_sms(event, user, revision_ids)
