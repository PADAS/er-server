import logging

from versatileimagefield.image_warmer import VersatileImageFieldWarmer

from activity.models import Event
from das_server import celery, pubsub
from usercontent.models import ImageFileContent

logger = logging.getLogger(__name__)


# @celery.app.task(bind=True)
def warm_imagefilecontent(imagefile_content_id):
    event = Event.objects.filter(file__usercontent_id=imagefile_content_id)

    try:
        logger.info('Warming images for imagefile_content_id=%s', imagefile_content_id)
        instance = ImageFileContent.objects.get(id=imagefile_content_id)
        warmer = VersatileImageFieldWarmer(
            instance_or_queryset=instance,
            rendition_key_set='default',
            image_attr='file'
        )
        print('warmed images.')
        num_created, failed_to_create = warmer.warm()
        pubsub.publish({'event_id': str(event.id)}, 'das.event.update')
        logger.info('Warmed images for imagefile_content_id=%s', imagefile_content_id)
    except Exception as e:
        logger.exception('Failed when warming images for imagefile_content_id {}'.format(imagefile_content_id))
