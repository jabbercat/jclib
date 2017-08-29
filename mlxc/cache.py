import abc
import asyncio


class AbstractCache(metaclass=abc.ABCMeta):
    @abc.abstractmethod
    @asyncio.coroutine
    def store(self, key, value, ttl=None):
        pass

    @abc.abstractmethod
    @asyncio.coroutine
    def fetch(self, key):
        """
        Retrieve a value from the cache.

        :param key: The key under which the value is stored.
        :raises KeyError: if no value is associated with the `key`.
        :return: The stored value.
        """

    @abc.abstractmethod
    def expire(self, key):
        pass


class InMemoryCache(AbstractCache):
    """
    In-memory cache for arbitrary data.
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.__data = {}
        self.__data_used = {}
        self.__maxsize = 1
        self.__ctr = 0

    def _purge_old(self, n):
        keys_in_age_order = sorted(
            self.__data_used.items(),
            key=lambda x: x[1]
        )
        keys_to_delete = keys_in_age_order[:n]
        for key, _ in keys_to_delete:
            del self.__data[key]
            del self.__data_used[key]
        keys_to_keep = keys_in_age_order[n:]
        # avoid the counter becoming large
        self.__ctr = len(keys_to_keep)
        for i, (key, _) in enumerate(keys_to_keep):
            self.__data_used[key] = i

    @property
    def maxsize(self):
        """
        Maximum size of the cache. Changing this property purges overhanging
        entries immediately.

        If set to :data:`None`, no limit on the number of entries is imposed.
        Do **not** use a limit of :data:`None` for data where the `key` is
        under control of a remote entity.

        Use cases for :data:`None` are those where you only need the explicit
        expiry feature, but not the LRU feature.
        """
        return self.__maxsize

    @maxsize.setter
    def maxsize(self, value):
        if value is not None and value <= 0:
            raise ValueError("maxsize must be positive integer or None")
        self.__maxsize = value
        if self.__maxsize is not None and len(self.__data) > self.__maxsize:
            self._purge_old(len(self.__data) - self.__maxsize)

    @asyncio.coroutine
    def store(self, key, value, ttl=None):
        if self.__maxsize is not None and len(self.__data) >= self.__maxsize:
            self._purge_old(len(self.__data) - (self.__maxsize - 1))
        self.__data[key] = value
        self.__data_used[key] = self.__ctr

    @asyncio.coroutine
    def fetch(self, key):
        result = self.__data[key]
        counter = self.__ctr
        counter += 1
        self.__ctr = counter
        self.__data_used[key] = counter
        return result

    def expire(self, key):
        del self.__data[key]
        del self.__data_used[key]
