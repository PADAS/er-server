
import eventlet
import logging

from activity.models import Event
from activity.views import EventView
# from activity.serializers import EventSerializer
from das_server import pubsub
from datetime import datetime, timedelta
import pytz
from observations.views import SubjectTracksView
from rt_api.rest_api_interface.dummy_request import DummyRequest
from observations.models import SubjectSource

logger = logging.getLogger(__name__)


def get_context():
    return {'request': DummyRequest(uri='', http_method='GET')}


def start(realtime_server):

    def _event_handler(data, emit, type=None):
        try:
            connected_clients = realtime_server.connected_clients()
            event_id = data['event_id']
            view = EventView.as_view()

            # Loop over all connected clients because they may have different event permissions
            for socket_id in connected_clients:
                try:
                    user = connected_clients[socket_id]['user']
                    if not user:
                        continue

                    # Create a dummy request with the user's info so we get the permission enforcement for free
                    request = DummyRequest(uri='/event/', http_method='GET', user=user)
                    result = view(request, id=event_id)

                    # if we get location data, package it up and send it out
                    if result.status_code == 200 and result.data:
                        emit(event_id=str(data['event_id']),
                             event_data=result.data,
                             user=socket_id)

                    send_count(socket_id)

                except Exception as ex:
                    logger.exception(
                        'Error creating custom payload for event: %s' % (data,),
                        ex)

        except Exception:
            logger.exception("Error handling {0} event for {1}".format(
                type, data))

    def _new_event_handler(data, message):
        logger.info("Handling new event: %s", data)
        _event_handler(data, realtime_server.emit_new_event, type='new')

    def new_event_handler(data, message):
        eventlet.spawn_n(_new_event_handler, data, message)

    def _update_event_handler(data, message):
        logger.info("Handling update event: %s", data)
        _event_handler(data, realtime_server.emit_update_event, type='update')

    def update_event_handler(data, message):
        eventlet.spawn_n(_update_event_handler, data, message)

    def _delete_event_handler(data, message):
        logger.info("Handling delete event: %s", data)
        _event_handler(data, realtime_server.emit_delete_event, type='delete')

    def delete_event_handler(data, message):
        eventlet.spawn_n(_delete_event_handler, data, message)

    def send_count(user):
        try:
            count = Event.objects.new_count()
            realtime_server.emit_count_event(count, user=user)
        except Exception:
            logger.exception(
                "Error sending count")

    def _new_observation_handler(data, message):
        try:
            logger.info("Handling new observation: %s", data)
            connected_clients = realtime_server.connected_clients()
            if 'subject_id' in data:
                subject_id = data['subject_id']
            elif 'source_id' in data:
                # get the most recent Subject for this Source
                subject_source = SubjectSource.objects.filter(source=data['source_id']) \
                    .order_by('assigned_range').reverse().first()
                subject_id = subject_source.subject_id
            view = SubjectTracksView.as_view()

            # Loop over all connected clients because they may have different permissions for this subject
            for socket_id in connected_clients:
                try:

                    user = connected_clients[socket_id]['user']
                    if not user:
                        continue

                    # Create a dummy request with the user's info so we get the permission enforcement for free
                    request = DummyRequest(
                        uri='/subject/{0}/'.format(subject_id), headers={},
                        body={'since': datetime.now(tz=pytz.UTC) - timedelta(days=30)},
                        http_method='GET', user=user)
                    result = view(request, id=subject_id)

                    # if we get location data, package it up and send it out
                    if 'features' in result.data and len(result.data['features']) > 0:
                        geojson_data = result.data['features'][0]

                        # If there are no coordinates the user is allowed to see, no reason to send a notification
                        if len(geojson_data['geometry']['coordinates']) == 0:
                            continue

                        # only want the latest 2 observations
                        geojson_data['properties']['coordinateProperties']['times'] = \
                            geojson_data['properties']['coordinateProperties']['times'][:2]
                        geojson_data['geometry']['coordinates'] = \
                            geojson_data['geometry']['coordinates'][:2]

                        # also need to send subject status if it exists
                        if 'subject_state' in result.data.serializer.context:
                            state = result.data.serializer.context['subject_state']
                        else:
                            state = None

                        # ok, now the object is ready to send
                        realtime_server.emit_subject_update(subjectid=str(subject_id),
                                                            geo_json=geojson_data, user=socket_id, state=state)

                except Exception as ex:
                    logger.exception('Error creating custom payload for subject position update: %s' % (data,), ex)

        except Exception as ex:
            logger.exception('Error handling new observation message: %s' % (data,), ex)

    def new_observation_handler(data, message):
        eventlet.spawn_n(_new_observation_handler, data, message)

    def pubsub_listener():

        logger.debug('Starting pubsub listener')
        subscriptions = [
            {'routing_key': 'das.tracking.source.observations.new', 'callback': new_observation_handler, },
            {'routing_key': 'das.event.new', 'callback': new_event_handler},
            {'routing_key': 'das.event.update', 'callback': update_event_handler},
            {'routing_key': 'das.event.delete', 'callback': delete_event_handler},
        ]
        for subscription in subscriptions:
            subscription['name'] = 'rt_api.{0}'.format(subscription['callback'].__name__)
        pubsub.subscribe(subscriptions)

    eventlet.spawn_n(pubsub_listener)