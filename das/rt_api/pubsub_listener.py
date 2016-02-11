import logging
from das_server import pubsub
from observations.models import Subject
from rt_api.server import RTServer, DummyRequest
from observations import models, serializers
from activity.models import Event
from activity.serializers import EventSerializer
import das_utils
import datetime
logger = logging.getLogger(__name__)


def new_observation_handler(data, message):
    try:
        subject = Subject.objects.get(id=data['source_id'])
        if subject:
            sources = models.SubjectSource.objects.get_subject_sources(subject)
            if sources:
                observations = models.Observation.objects.get_source_range_observations_last(sources, datetime.timedelta(days=3))
                if observations:
                    coordinates = []
                    times = []
                    for i in range(0, 1):
                        coordinates.append(observations[i].location.coords)
                        times.append(str(observations[i].recorded_at))

                    request = DummyRequest(uri='', http_method='GET')
                    feature = serializers.make_feature(request, coordinates, subject,times)
                    rep = das_utils.json.empty_geojson_featurecollection()
                    rep['features'].append(feature)

                    RTServer.emit_subject_update(subjectid=str(data['source_id']), geo_json=rep)
    except Exception as ex:
        logger.error('problem sending subject update', ex)


def new_event_handler(data, message):
    try:
        event = Event.objects.get(id=data['event_id'])
        if event:
            event.event_time = str(event.event_time)
            serializer = EventSerializer(event)
            serializer.context = {'request': DummyRequest(uri='', http_method='GET')}
            event_data = serializer.data
            RTServer.emit_new_event(event_id=str(data['event_id']), event_data=event_data)
    except Exception as ex:
        logger.error("Error sending new event message", ex)


def pubsub_listener():
    logger.debug('Starting pubsub listener')
    subscriptions = [
        {'routing_key': 'das.tracking.source.observations.new', 'callback': new_observation_handler},
        {'routing_key': 'das.event.new', 'callback': new_event_handler},
    ]
    pubsub.subscribe(subscriptions)

import eventlet
eventlet.spawn(pubsub_listener)
