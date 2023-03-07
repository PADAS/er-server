from abc import ABC, abstractmethod

import redis


class PersistentStorage(ABC):
    """ Interface for implementation of key, value engines like Redis, MongoDB. """

    @abstractmethod
    def insert_key(self, key, value, expiration):
        pass

    @abstractmethod
    def get_key(self, key):
        pass

    @abstractmethod
    def delete_key(self, key):
        pass


class PersistentStorageWitSortedSet(PersistentStorage):
    """ Interface for implementation of key, values and sorted set engines like Redis. """

    @abstractmethod
    def insert_in_sorted_set(self, key, value, score):
        pass

    def get_size_sorted_set(self, key):
        pass

    def get_latest_item_in_sorted_set(self, key):
        pass

    def get_sorted_set(self, key):
        pass


class RedisStorage(PersistentStorageWitSortedSet):
    def __init__(self, config):
        self.host = config["HOST"]
        self.port = config["PORT"]
        self._connection = redis.Redis(host=self.host, port=self.port)

    def insert_key(self, key, value, expiration=3600):
        self._connection.set(key, value, expiration)

    def get_key(self, key):
        return self._connection.get(key)

    def delete_key(self, key):
        return self._connection.delete(key)

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
