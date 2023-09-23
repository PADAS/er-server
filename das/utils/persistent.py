from abc import ABC, abstractmethod

import redis

from utils.decorator import apply_decorator_to_public_methods
from utils.tenant.cache import use_multitenant_cache_key


class PersistentStorage(ABC):
    """Interface for implementation of key, value engines like Redis, MongoDB."""

    @abstractmethod
    def insert_key(self, key, value, expiration):
        raise NotImplementedError

    @abstractmethod
    def get_key(self, key):
        raise NotImplementedError

    @abstractmethod
    def delete_key(self, key):
        raise NotImplementedError


class PersistentStorageReadOnly(ABC):
    @abstractmethod
    def get_key(self, key):
        raise NotImplementedError


class PersistentStorageWithSortedSet(PersistentStorage):
    """Interface for implementation of key, values and sorted set engines like Redis."""

    @abstractmethod
    def insert_in_sorted_set(self, key, value, score):
        raise NotImplementedError

    def get_size_sorted_set(self, key):
        raise NotImplementedError

    def get_latest_item_in_sorted_set(self, key):
        raise NotImplementedError

    def get_sorted_set(self, key):
        raise NotImplementedError


class RedisStorage(PersistentStorageWithSortedSet):
    def __init__(self, config):
        self.host = config["HOST"]
        self.port = config["PORT"]
        self.db = config["DATABASE"]
        self._connection = redis.Redis(host=self.host, port=self.port, db=self.db)

    def insert_key(self, key, value, ttl=3600):
        self._connection.set(key, value, ttl)

    def get_key(self, key):
        return self._connection.get(key)

    def delete_key(self, key):
        return self._connection.delete(key)

    def insert_set_key(self, key, value, ttl=3600):
        self._connection.setex(name=key, time=ttl, value=value)

    def insert_in_sorted_set(self, key, value, score):
        self._connection.zadd(key, {value: score})

    def get_size_sorted_set(self, key):
        data = self._connection.zrange(key, 0, -1)
        return len(data)

    def get_latest_item_in_sorted_set(self, key):
        size = self.get_size_sorted_set(key)
        return self._connection.zrange(key, -1, size - 1)

    def get_sorted_set(self, key, desc=True):
        return self._connection.zrange(key, 0, -1, desc)

    def slice_sorted_set(self, key, maximum):
        self._connection.zremrangebyscore(key, min=0, max=maximum)

    def increment_key_by_value(self, key: str, increment: int = 1) -> int:
        return self._connection.incrby(key, increment)

    def insert_set(self, key: str, member: str) -> int:
        return self._connection.sadd(key, member)

    def delete_set(self, key: str, member: str) -> int:
        return self._connection.srem(key, member)

    def get_set_size(self, key: str) -> int:
        return self._connection.scard(key)


class RedisStorageReadOnly(PersistentStorageReadOnly):
    def __init__(self, config):
        self.host = config["HOST"]
        self.database = int(config["DATABASE"])
        self.api_key = config["API_KEY"]
        self.port = int(config["PORT"])
        self._pool = redis.ConnectionPool(host=self.host, password=self.api_key, port=self.port, db=self.database)
        self._connection = redis.Redis(connection_pool=self._pool, password=self.api_key, health_check_interval=10)

    def get_key(self, key):
        return self._connection.get(str(key))

    def get_all_keys(self):
        return self._connection.keys()


@apply_decorator_to_public_methods(use_multitenant_cache_key)
class MultitenantRedisStorage(RedisStorage):
    pass
