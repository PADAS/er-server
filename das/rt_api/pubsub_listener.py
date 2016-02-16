import logging

import eventlet

from activity.models import Event
from activity.serializers import EventSerializer
from das_server import pubsub
import das_utils
from observations.models import SubjectSource
from observations import serializers
from rt_api.server import DummyRequest


logger = logging.getLogger(__name__)


def start(realtime_server):

    def new_event_handler(data, message):
        try:
            event = Event.objects.get(id=data['event_id'])
            if event:
                event.event_time = str(event.event_time)
                serializer = EventSerializer(event)
                serializer.context = {'request': DummyRequest(uri='', http_method='GET')}
                event_data = serializer.data
                realtime_server.emit_new_event(event_id=str(data['event_id']), event_data=event_data)
        except Exception:
            logger.exception("Error handling new event for {0}".format(data,))

    def new_observation_handler(data, message):
        try:
            logger.info("Handling new observation: %s", data)
            subject = SubjectSource.objects \
                    .filter(source_id=data['source_id']) \
                    .order_by('-assigned_range') \
                    .first() \
                    .subject

            observations = subject.observations(last_days=3)

            observations = observations[:2]

            if not observations:
                logger.warning('Could not locate any observations')
                return

            coordinates, times = zip(*[
                (o.location.coords, str(o.recorded_at)) for o in observations
            ])

            request = DummyRequest(uri='', http_method='GET')
            feature = serializers.make_feature(request, coordinates, subject, times)
            rep = das_utils.json.empty_geojson_featurecollection()
            rep['features'].append(feature)
            realtime_server.emit_subject_update(subjectid=str(subject.pk), geo_json=rep)

        except Exception:
            logger.exception('Error handling new observation message: %s' % (data,))

    def pubsub_listener():

        logger.debug('Starting pubsub listener')
        subscriptions = [
            {'routing_key': 'das.tracking.source.observations.new', 'callback': new_observation_handler},
            {'routing_key': 'das.event.new', 'callback': new_event_handler},
        ]
        pubsub.subscribe(subscriptions)

    eventlet.greenthread.spawn_n(pubsub_listener)



