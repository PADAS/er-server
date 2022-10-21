import logging

from django.db.models.signals import post_save, post_delete
from django.db import transaction
from django.dispatch import receiver

from das_server import celery

from usercontent.models import ImageFileContent
from das_server import pubsub

logger = logging.getLogger(__name__)

@receiver(post_save, sender=ImageFileContent)
def warm_imagefile_content_image(sender, instance, **kwargs):
    transaction.on_commit(lambda:
        celery.app.send_task('usercontent.tasks.warm_imagefilecontent', args=(str(instance.id),))
    )

@receiver(post_delete, sender=ImageFileContent)
def delete_imagefile_content_files(sender, instance, **kwargs):
    logger.info('delete sized images for ImageFileContent.id: {}'.format(instance.pk))
    instance.file.delete_all_created_images()
