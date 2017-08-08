"""Redis utilities"""

import redis
import logging
import contextlib

from django.conf import settings

logger = logging.getLogger(__name__)

shared_cache = None


def clear_keys(redis, wildcard, pipeline=None):
    keys = redis.keys(wildcard)
    if not keys:
        return

    p = pipeline
    if not pipeline:
        p = redis.pipeline()

    for key in keys:
        logger.debug("clearing key:  %s", key)
        p.delete(key)

    if not pipeline:
        p.execute()


@contextlib.contextmanager
def lock(redis_client=None, key=None, timeout=60, blocking=False):
    """Use a redis based key to provide a distributed lock.
    :param timeout: if the lock is left open, time before it expires
    """
    lock_acquired = None
    lock = redis_client.lock(key, timeout=timeout)

    try:
        lock_acquired = lock.acquire(blocking=blocking)
        yield lock_acquired
    finally:
        if lock_acquired:
            lock.release()
