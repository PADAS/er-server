
import eventlet
import logging

from activity.models import Event
from activity.serializers import EventSerializer
from das_server import pubsub
from datetime import datetime, timedelta
from observations.views import SubjectTracksView
from rt_api.rest_api_interface.dummy_request import DummyRequest

logger = logging.getLogger(__name__)

def start(realtime_server):

    def new_event_handler(data, message):
        try:
            event = Event.objects.get(id=data['event_id'])
            if event:
                serializer = EventSerializer(event)
                serializer.context = {'request': DummyRequest(uri='', http_method='GET')}
                event_data = serializer.data
                realtime_server.emit_new_event(event_id=str(data['event_id']), event_data=event_data)
        except Exception:
            logger.exception("Error handling new event for {0}".format(data,))
        send_count()

    def update_event_handler(data, message):
        try:
            event = Event.objects.get(id=data['event_id'])
            if event:
                serializer = EventSerializer(event)
                serializer.context = {
                    'request': DummyRequest(uri='', http_method='GET')}
                event_data = serializer.data
                realtime_server.emit_update_event(event_id=str(data['event_id']),
                                               event_data=event_data)
        except Exception:
            logger.exception("Error handling new event for {0}".format(data, ))
        send_count()

    def delete_event_handler(data, message):
        try:
                realtime_server.emit_delete_event(
                    event_id=str(data['event_id']))
        except Exception:
            logger.exception("Error handling delete event for {0}".format(data))
        send_count()

    def send_count():
        try:
            count = Event.objects.new_count()
            realtime_server.emit_count_event(count)
        except Exception:
            logger.exception(
                "Error sending count")

    def new_observation_handler(data, message):
        try:
            logger.info("Handling new observation: %s", data)
            connected_clients = realtime_server.connected_clients()
            subject_id = data['subject_id']
            view = SubjectTracksView.as_view()

            # Loop over all connected clients because they may have different permissions for this subject
            for socket_id in connected_clients:
                try:
                    # Create a dummy request with the user's info so we get the permission enforcement for free
                    request = DummyRequest(uri='/subject/{0}/'.format(subject_id), headers={},
                                           body={'since':datetime.now() - timedelta(days=3)}, http_method='GET')
                    request.user = connected_clients[socket_id]['user']
                    request._force_auth_user = request.user
                    result = view(request, id=subject_id)

                    # if we get location data, package it up and send it out
                    if 'features' in result.data and len(result.data['features']) > 0:
                        geojson_data = result.data['features'][0]

                        # only want the latest 2 observations
                        geojson_data['properties']['coordinateProperties']['times'] = \
                            geojson_data['properties']['coordinateProperties']['times'][:2]
                        geojson_data['geometry']['coordinates'] = \
                            geojson_data['geometry']['coordinates'][:2]
                        realtime_server.emit_subject_update(subjectid=str(subject_id),
                                                            geo_json=geojson_data, user=socket_id)

                except Exception as ex:
                    logger.exception('Error creating custom payload for subject position update: %s' % (data,), ex)

        except Exception as ex:
            logger.exception('Error handling new observation message: %s' % (data,), ex)

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