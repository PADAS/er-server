import redis
import contextlib
shared_cache = None
from django.conf import settings


def get_cache():
    global shared_cache
    if not shared_cache:
        shared_cache = redis.StrictRedis(**settings.CACHE_REDIS)
    return shared_cache


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

