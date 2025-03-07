import logging

from celery.result import AsyncResult

from django.contrib.contenttypes.models import ContentType
from django.urls import reverse
from rest_framework import status
from rest_framework.response import Response

from das_server import celery
from utils.tenant import get_tenant_settings
from utils.tenant.celery import TenantTask

logger = logging.getLogger(__name__)


def delete_object(object):
    """Delete this object asynchronously.

    Args:
        object (Model): The object to delete

    Returns:
        Response: A response with the task id and the location of the status endpoint
    """
    content_type_id = ContentType.objects.get_for_model(object).id
    args = (content_type_id, object.id)
    kwargs = dict(domain=get_tenant_settings().domain)
    task = delete_object_task.apply_async(args=args, kwargs=kwargs)
    data = {"task_id": task.id, "location": reverse("delete-object-status", args=[task.id]), "status": task.status}
    return Response(status=status.HTTP_204_NO_CONTENT, data=data)


@celery.app.task(base=TenantTask, bind=True, track_started=True)
def delete_object_task(self, content_type_id, object_id, *args, **kwargs):
    logger.info("Deleting object %s of type %s", str(object_id), str(content_type_id))

    try:
        content_type = ContentType.objects.get_for_id(content_type_id)
        model_class = content_type.model_class()
        obj = model_class.objects.get(id=object_id)
        obj.delete()

    except model_class.DoesNotExist:
        logger.warning("Object %s of type %s does not exist", str(object_id), str(content_type_id))
    except Exception:
        logger.exception("Failed to delete object %s of type %s", str(object_id), str(content_type_id))


def delete_object_status(task_id):
    result = AsyncResult(task_id)
    return {"task_id": task_id, "status": result.status, "result": result.result}
