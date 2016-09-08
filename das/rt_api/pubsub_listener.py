
import eventlet
import json
import logging

from das_server import pubsub, celery

logger = logging.getLogger(__name__)


def start(realtime_server):

    def new_event_handler(data, message):
        celery.app.send_task('rt_api.tasks.handle_new_event',
                             args=(data['event_id'],))

    def update_event_handler(data, message):
        celery.app.send_task('rt_api.tasks.handle_update_event',
                             args=(data['event_id'],))

    def delete_event_handler(data, message):
        celery.app.send_task('rt_api.tasks.handle_delete_event',
                             args=(data['event_id'],))

    def new_observation_handler(data, message):
        celery.app.send_task('rt_api.tasks.handle_new_subject_observation',
                             args=(data['subject_id'],))

    def emit_handler(data, message):
        message_data = json.loads(data)
        realtime_server.send_realtime_message(message_data)

    def pubsub_listener():

        logger.debug('Starting pubsub listener')
        subscriptions = [
            {
                'routing_key': 'das.tracking.source.observations.new',
                'callback': new_observation_handler},
            {
                'routing_key': 'das.event.new',
                'callback': new_event_handler},
            {
                'routing_key': 'das.event.update',
                'callback': update_event_handler},
            {
                'routing_key': 'das.event.delete',
                'callback': delete_event_handler},
            {
                'routing_key': 'das.realtime.emit',
                'callback': emit_handler},
        ]
        for subscription in subscriptions:
            subscription['name'] = 'rt_api.{0}'.format(subscription['callback'].__name__)
        pubsub.subscribe(subscriptions)

    eventlet.spawn_n(pubsub_listener)