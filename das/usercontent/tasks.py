import logging

from django.dispatch import Signal
from versatileimagefield.image_warmer import VersatileImageFieldWarmer

from das_server import celery
from usercontent.models import ImageFileContent

logger = logging.getLogger(__name__)

imagefile_rendered = Signal(providing_args=["usercontent_id"])

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

        num_created, failed_to_create = warmer.warm()
        logger.info('Warmed images for imagefile_content_id=%s', imagefile_content_id)

        # If any images have been created, signal receivers.
        if num_created:
            imagefile_rendered.send(sender=None, usercontent_id=instance.id)

    except Exception as e:
       logger.exception('Failed when warming images for imagefile_content_id {}'.format(imagefile_content_id))
