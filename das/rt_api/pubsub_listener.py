import logging
import threading
from das_server import pubsub
from observations.models import Subject
from observations.serializers import ObservationSerializer
from rt_api.server import RTServer

logger = logging.getLogger(__name__)

def subject_update_handler(data, message):
    try:
        subject = Subject.objects.get(id=data['source_id'])
        last_observation = ObservationSerializer().to_representation(subject.last_observation)
        coords = [subject.last_observation.location.x, subject.last_observation.location.y]
        observation = {'recorded_at': last_observation['recorded_at'], 'location':coords}
        RTServer.broadcast_subject_update(subjectid=str(data['source_id']), observation=observation)
    except Exception as ex:
        logger.error(ex.message. ex)

def subject_listener():
    logger.debug('Starting rt_api subject_listener')
    pubsub.subscribe(routing_key='das.#', callback=subject_update_handler)

threading.Timer(1.0, subject_listener, []).start()