import logging

from versatileimagefield.image_warmer import VersatileImageFieldWarmer

from activity.models import Event
from das_server import celery, pubsub
from django.dispatch import Signal
from usercontent.models import ImageFileContent

logger = logging.getLogger(__name__)

thumbnails_verified = Signal(providing_args=["file_id"])

@celery.app.task(bind=True)
def warm_imagefilecontent(self, imagefile_content_id):

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
        logger.info('Warmed images for imagefile_content_id=%s', imagefile_content_id)

        pubsub.publish({'imagefilecontent_id': str(instance.id)}, 'das.event.update')
        thumbnails_verified.send(sender=ImageFileContent, file_id=instance.id)

    except Exception as e:
       logger.exception('Failed when warming images for imagefile_content_id {}'.format(imagefile_content_id))
