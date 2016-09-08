import datetime
import json
import logging
import redis

from accounts.models.user import User
from activity.models import Event
from activity.views import EventView
from das_server import celery, pubsub
from django.conf import settings
from django.db import close_old_connections
from observations.models import SubjectSource
from observations.views import SubjectTracksView
from rt_api.rest_api_interface.dummy_request import DummyRequest
from uuid import UUID


redis_client = redis.from_url(settings.REALTIME_BROKER_URL)

logger = logging.getLogger(__name__)


def get_context():
    return {'request': DummyRequest(uri='', http_method='GET')}


def dumps_helper(obj):
    if isinstance(obj, datetime.datetime):
        serial = obj.isoformat()
        return serial
    elif isinstance(obj, UUID):
        return str(obj)
    raise TypeError("Type not serializable: " + type(obj).__name__)

def _event_handler(event_id, type):
    try:
        view = EventView.as_view()
        connected_sids = redis_client.hkeys('realtime_connections')

        for connected_sid in connected_sids:
            try:
                connected_sid = connected_sid.decode('UTF-8')
                username = redis_client.hget('realtime_connections',
                                             connected_sid).decode('UTF-8')
                user = User.objects.filter(username=username).first()
                if not user:
                    # Probably shouldn't get here, but maybe the user got
                    # deleted just now?
                    redis_client.hdel('realtime_connections', connected_sid)
                    continue

                # Fake an API call for free permission enforcement
                request = DummyRequest('/event/', 'GET', user=user)
                result = view(request, id=event_id)

                # If there's nothing to send, no need to send it
                if result.status_code != 200 or not result.data:
                    continue

                emit_data = {
                    'type': type,
                    'sid': connected_sid,
                    'object_id': event_id,
                    'data': result.data
                }
                count_data = {
                    'type': 'count_event',
                    'sid': connected_sid,
                    'data': Event.objects.new_count()
                }

                pubsub.publish(json.dumps(emit_data), 'das.realtime.emit')
                pubsub.publish(json.dumps(count_data), 'das.realtime.emit')

            except Exception as ex:
                logger.exception('Error creating custom payload for event: %s' %
                                 (event_id,), ex)
            finally:
                close_old_connections()

    finally:
        close_old_connections()

def _observation_handler(subject_id):
    try:
        view = SubjectTracksView.as_view()
        connected_sids = redis_client.hkeys('realtime_connections')

        for connected_sid in connected_sids:

            try:
                connected_sid = connected_sid.decode('UTF-8')
                username = redis_client.hget('realtime_connections',
                                             connected_sid).decode('UTF-8')
                user = User.objects.filter(username=username).first()
                if not user:
                    # Probably shouldn't get here, but maybe the user got
                    # deleted just now?
                    redis_client.hdel('realtime_connections', connected_sid)
                    continue

                # Create a dummy request with the user's info so we get the permission enforcement for free
                request = DummyRequest('/subject/{0}/'.format(subject_id), 'GET',
                                       {'limit': 2}, user=user)
                result = view(request, id=subject_id)

                # If there's nothing to send, no need to send it
                if result.status_code != 200 or not result.data or 'features' not in result.data or len(result.data['features']) == 0:
                    continue

                geojson_data = result.data['features'][0]

                # If there are no coordinates the user is allowed to see, no reason to send a notification
                if len(geojson_data['geometry']['coordinates']) == 0:
                    continue

                # also need to send subject status if it exists
                if 'subject_state' in result.data.serializer.context:
                    state = result.data.serializer.context['subject_state']
                else:
                    state = None

                emit_data = {
                    'type': 'subject_position_update',
                    'sid': connected_sid,
                    'object_id': subject_id,
                    'data': {'geo_json': geojson_data, 'state': state}
                }

                pubsub.publish(json.dumps(emit_data, default=dumps_helper), 'das.realtime.emit')

            except Exception as ex:
                logger.exception('Error creating payload data for observation: %s' %
                                 (subject_id,), ex)
            finally:
                close_old_connections()
    finally:
        close_old_connections()


@celery.app.task()
def handle_new_event(event_id):
    logger.info('Celery worker handling new event_id: {}'.format(event_id))
    _event_handler(event_id, 'new_event')

@celery.app.task()
def handle_update_event(event_id):
    logger.info('Celery worker handling update event_id: {}'.format(event_id))
    _event_handler(event_id, 'update_event')

@celery.app.task()
def handle_delete_event(event_id):
    logger.info('Celery worker handling delete event_id: {}'.format(event_id))
    _event_handler(event_id, 'delete_event')

@celery.app.task()
def handle_new_source_observation(source_id):
    logger.info('Celery worker handling new source observation: {}'.format(source_id))
    subject_source = SubjectSource.objects.filter(source=source_id)\
        .order_by('assigned_range').reverse().first()
    _observation_handler(subject_source.subject_id)

@celery.app.task()
def handle_new_subject_observation(subject_id):
    logger.info('Celery worker handling new subject observation: {}'.format(subject_id))
    _observation_handler(subject_id)

@celery.app.task()
def handle_emit_data(event_id):
    logger.info('event mailer event_id: {}'.format(event_id))


