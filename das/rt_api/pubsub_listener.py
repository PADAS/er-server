import utils.json as json
import logging

from das_server import pubsub, celery
import threading

logger = logging.getLogger(__name__)


def start(realtime_server):

    def new_event_handler(data, message):
        logger.debug('new_event_handler. data=%s, message=%s', data, message)
        celery.app.send_task('rt_api.tasks.handle_new_event',
                             args=(data['event_id'],))

    def update_event_handler(data, message):
        logger.debug(
            'update_event_handler. data=%s, message=%s', data, message)
        celery.app.send_task('rt_api.tasks.handle_update_event',
                             args=(data['event_id'],))

    def delete_event_handler(data, message):
        logger.debug(
            'delete_event_handler. data=%s, message=%s', data, message)
        celery.app.send_task('rt_api.tasks.handle_delete_event',
                             args=(data['event_id'],))

    def new_observation_handler(data, message):

        # Resolve the subject from either subject_id or source_id provided in data dict.
        # TODO: Move this resolution logic into Subject Manager.
        if 'subject_id' in data:
            subject_id = data['subject_id']
        elif 'source_id' in data:
            from observations.models import Subject
            try:
                subject = Subject.objects.filter(
                    subjectsource__source__id=data['source_id']).latest('subjectsource__assigned_range')
                subject_id = str(subject.id)
            except Subject.DoesNotExist:
                subject_id = None

        if subject_id:
            from observations.models import Subject
            try:
                if Subject.objects.get(id=subject_id).is_active:
                    celery.app.send_task(
                        'rt_api.tasks.handle_new_subject_observation', args=(subject_id,))
            except Subject.DoesNotExist:
                pass

    def subjectstatus_update_handler(data, message):
        logger.debug('das.subjectstatus.update %s', data)
        if 'subject_id' in data:
            celery.app.send_task('rt_api.tasks.handle_subjectstatus_update',
                                 args=(data['subject_id'],))

    def new_patrol_handler(data, message):
        logger.debug('new_patrol_handler. data=%s, message=%s', data, message)
        celery.app.send_task('rt_api.tasks.handle_new_patrol',
                             args=(data['patrol_id'],))

    def update_patrol_handler(data, message):
        logger.debug(
            'update_patrol_handler. data=%s, message=%s', data, message)
        celery.app.send_task('rt_api.tasks.handle_update_patrol',
                             args=(data['patrol_id'],))

    def delete_patrol_handler(data, message):
        logger.debug(
            'delete_patrol_handler. data=%s, message=%s', data, message)
        celery.app.send_task('rt_api.tasks.handle_delete_patrol',
                             args=(data['patrol_id'],))

    def emit_handler(data, message):
        message_data = json.loads(data)
        realtime_server.send_realtime_message(message_data)

    def new_message_handler(data, message):
        logger.debug(
            'new_message_handler. data=%s, message=%s', data, message)
        celery.app.send_task(
            'rt_api.tasks.handle_new_message', args=(data['message_id'],))

    def update_message_handler(data, message):
        logger.debug(
            'update_message_handler. data=%s, message=%s', data, message)
        celery.app.send_task(
            'rt_api.tasks.handle_update_message', args=(data['message_id'],))

    def delete_message_handler(data, message):
        logger.debug(
            'delete_message_handler. data=%s, message=%s', data, message)
        celery.app.send_task(
            'rt_api.tasks.handle_delete_message', args=(data['message_id'],))

    def new_announcement_handler(data, message):
        logger.debug(
            'new_announcement_handler. data=%s, message=%s', data, message)
        celery.app.send_task(
            'rt_api.tasks.handle_new_announcement', args=(data['announcement_id'],))


    def pubsub_listener():

        logger.info('Starting pubsub listener')
        subscriptions = [
            {
                'routing_key': 'das.tracking.source.observations.new',
                'callback': new_observation_handler},
            {
                'routing_key': 'das.subjectstatus.update',
                'callback': subjectstatus_update_handler,
            },
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
                'routing_key': 'das.patrol.new',
                'callback': new_patrol_handler},
            {
                'routing_key': 'das.patrol.update',
                'callback': update_patrol_handler},
            {
                'routing_key': 'das.patrol.delete',
                'callback': delete_patrol_handler},
            {
                'routing_key': 'das.realtime.emit',
                'callback': emit_handler},
            {
                'routing_key': 'das.message.new',
                'callback': new_message_handler,
            },
            {
                'routing_key': 'das.message.update',
                'callback': update_message_handler,
            },
            {
                'routing_key': 'das.message.delete',
                'callback': delete_message_handler,
            },
            {
                'routing_key': 'das.announcement.new',
                'callback': new_announcement_handler,
            },

        ]
        for subscription in subscriptions:
            subscription['name'] = 'rt_api.{0}'.format(
                subscription['callback'].__name__)

            logger.info('Adding subscription for "%s"', subscription['name'])
        pubsub.subscribe(subscriptions)

    logger.info("Starting pubsub listener threads.")
    for x in range(5):
        logger.info("Starting pubsub listener thread (%s).", x)
        threading.Thread(target=pubsub_listener,
                         name=f'pubsub-listener-{x}', args=()).start()
