"""
Lightweight Redis-based job status tracking for CSV observation imports.

We store state directly in Redis rather than relying on Celery's result backend
because CELERY_TASK_IGNORE_RESULT=True is set globally, which makes AsyncResult
always return PENDING regardless of actual task state.

Scoping policy: state is keyed via MultitenantRedisClient, which prefixes every
key with the current tenant id. The pending-jobs list is therefore visible to
*every* staff user in the same tenant — by design, so multiple admins
coordinating an import see the same view. It is **not** scoped per-user.
"""

import json
import logging

from django.conf import settings

from utils.tenant.cache import MultitenantRedisClient

logger = logging.getLogger(__name__)

_KEY_PREFIX = "csv_import_job:"
_PENDING_KEY = "csv_import_pending"
_TTL_SECONDS = 3600  # 1 hour


def _redis():
    return MultitenantRedisClient(settings.CELERY_BROKER_URL)


def _decode(value):
    return value.decode() if isinstance(value, (bytes, bytearray)) else value


def set_job_status(task_id, status, result=None, error=None, **extra):
    key = _KEY_PREFIX + task_id
    # Preserve existing fields (e.g. filename, queued_at) when updating status
    raw = _redis().get(key)
    data = json.loads(raw) if raw else {}
    data["status"] = status
    if result is not None:
        data["result"] = result
    if error is not None:
        data["error"] = error
    data.update(extra)
    logger.debug("csv_import_jobs.set: key=%s status=%s has_error=%s", key, data.get("status"), "error" in data)
    _redis().setex(key, _TTL_SECONDS, json.dumps(data))


def get_job_status(task_id):
    key = _KEY_PREFIX + task_id
    raw = _redis().get(key)
    logger.debug("csv_import_jobs.get: key=%s found=%s", key, raw is not None)
    if raw is None:
        return {"status": "PENDING"}
    return json.loads(raw)


def delete_job_status(task_id):
    _redis().delete(_KEY_PREFIX + task_id)


def add_pending_task(task_id):
    """Mark a task as pending for the current tenant."""
    _redis().sadd(_PENDING_KEY, task_id)
    _redis().expire(_PENDING_KEY, _TTL_SECONDS)


def remove_pending_task(task_id):
    """Remove a task from the tenant's pending list (used by dismiss)."""
    _redis().srem(_PENDING_KEY, task_id)


def list_pending_tasks():
    """Return the tenant's pending task IDs, pruning any whose status has expired."""
    members = _redis().smembers(_PENDING_KEY) or set()
    task_ids = []
    expired = []
    for member in members:
        tid = _decode(member)
        if _redis().exists(_KEY_PREFIX + tid):
            task_ids.append(tid)
        else:
            expired.append(tid)
    if expired:
        _redis().srem(_PENDING_KEY, *expired)
    return task_ids
