import logging

from celery.result import AsyncResult

from django.contrib.contenttypes.models import ContentType
from django.core.cache import cache
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
    data = {"task_id": task.id, "location": reverse("task-status", args=[task.id]), "status": task.status}
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


SOURCE_DELETING_CACHE_KEY = "source_deleting:{}"


@celery.app.task(base=TenantTask, bind=True, track_started=True)
def delete_source_task(self, source_id, *args, **kwargs):
    """Async wrapper around the shared cascade delete.

    Sets/clears the admin "being deleted" marker so the change_view can show a
    warning while the task runs, and enqueues one
    ``maintain_subjectstatus_for_subject`` per affected subject after the
    cascade completes.
    """
    # Imports kept inside the task body: observations.services and
    # observations.tasks both pull in observations.models, and core.tasks is
    # imported during celery worker boot — moving them to module top creates a
    # cross-app import at Django app-load time which has bitten us before.
    from observations.services import delete_source_cascade
    from observations.tasks import maintain_subjectstatus_for_subject

    cache_key = SOURCE_DELETING_CACHE_KEY.format(source_id)
    # Always clear the admin "being deleted" marker on exit, including unexpected
    # failures during the cascade — otherwise the admin refuses to show the
    # source for the full TTL even though it may still exist.
    try:
        _, subject_ids = delete_source_cascade(source_id)
        for subject_id in subject_ids:
            maintain_subjectstatus_for_subject.apply_async(args=[str(subject_id)])
    finally:
        cache.delete(cache_key)


def get_task_status(task_id):
    result = AsyncResult(task_id)
    return {
        "task_id": task_id,
        "status": result.status,
        "result": result.result,
        "location": reverse("task-status", args=[task_id]),
    }
