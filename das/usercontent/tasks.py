import logging

from versatileimagefield.image_warmer import VersatileImageFieldWarmer

from django.dispatch import Signal

from das_server import celery
from usercontent.models import ImageFileContent
from utils.tenant.celery import TenantQueueOnceTask

logger = logging.getLogger(__name__)

# the old providing_args=["usercontent_id"], is not used by Django. Here for documentation purposes.
imagefile_rendered = Signal()


@celery.app.task(base=TenantQueueOnceTask, bind=True)
def warm_imagefilecontent(self, imagefile_content_id, **kwargs):
    try:
        logger.info("Warming images for imagefile_content_id=%s", imagefile_content_id)
        instance = ImageFileContent.objects.get(id=imagefile_content_id)
        warmer = VersatileImageFieldWarmer(
            instance_or_queryset=instance, rendition_key_set="default", image_attr="file"
        )

        num_created, failed_to_create = warmer.warm()
        logger.info("Warmed images for imagefile_content_id=%s", imagefile_content_id)

        # If any images have been created, signal receivers.
        if num_created:
            imagefile_rendered.send(sender=None, usercontent_id=instance.id)

    except Exception:
        logger.error("Failed when warming images for imagefile_content_id %s", imagefile_content_id)
