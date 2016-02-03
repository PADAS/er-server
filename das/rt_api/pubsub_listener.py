import logging
from threading import Thread
from das_server import pubsub
from observations.models import Subject
from observations.serializers import ObservationSerializer
from rt_api.server import RTServer

logger = logging.getLogger(__name__)

coord_offset = 0

def new_observation_handler(data):
    # global coord_offset
    # coord_offset += 0.01
    # if coord_offset > 0.1:
    #     coord_offset = 0.0
    try:
    #     subject = Subject.objects.get(id=data['source_id'])
    #     last_observation = ObservationSerializer().to_representation(subject.last_observation)
    #     coords = [subject.last_observation.location.x + coord_offset,
    #               subject.last_observation.location.y + coord_offset]
    #     observation = {'location': coords}
    #
    #     geo_json={'type': 'Feature',
    #               'properties': {
    #                   'title': subject.name,
    #                   "stroke-width": 2,
    #                   "stroke-opacity": 1.0,
    #                   'coordinateProperties': {
    #                       'times': [
    #                           last_observation['recorded_at'], ], },
    #                   "image": "http://dev.pamdas.org/static/elephant-black-female.svg", },
    #               'geometry': {
    #                   'type': 'LineString',
    #                   'coordinates': [coords]},
    #               'style': {
    #                   'opacity': 1,
    #                   'deprecating': 'use https://github.com/mapbox/simplestyle-spec/tree/master/1.1.0',
    #                   'color': '#FF0000',
    #                   'iconUrl': 'http://dev.pamdas.org/static/elephant-black-female.svg'}, }
    #
    #     RTServer.broadcast_subject_update(subjectid=str(data['source_id']), geo_json=geo_json)

        RTServer.broadcast_subject_update(subjectid=str(data['source_id']))
    except Exception as ex:
        logger.error('problem sending subject update', ex)

def new_event_handler(data, message):
    pass

def pubsub_callback(data, message):
    routing_key = message.delivery_info['routing_key']
    if routing_key == 'das.tracking.source.observations.new':
        new_observation_handler(data)
    elif routing_key == 'das.event.new':
        new_event_handler(data)

def pubsub_listener():
    logger.debug('Starting pubsub listener')
    pubsub.subscribe(routing_key='das.#', callback=pubsub_callback)

Thread(target=pubsub_listener, args=()).start()
