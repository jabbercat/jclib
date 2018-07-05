import abc
import asyncio
import enum
import functools
import typing

import aioxmpp
import aioxmpp.cache

import jclib.client
import jclib.identity


UNSET = object()


class Tempfail(KeyError):
    """
    Raised by providers if the data is temporarily unavailable.

    Tempfails may not be cached. If a cache entry is available, cached data
    may be returned instead of the tempfail.

    Tempfails may be aliased to :data:`None` in the frontend.
    """


# on_change -> invalidate cache
# fetch -> fetch from service and set cache
# get -> try service, then cache; if both miss, spawn fetch return miss

# display name:
# - via roster or MUC
# - pushed
# - can be fetched without coroutine
# - does not need extra cache
# - not gettable equivalent to unset

# presence:
# - via RFC 6120
# - pushed
# - can be fetched without coroutine
# - does not need extra cache
# - not gettable equivalent to unset

# subscription: like presence

# last_message:
# - via archive
# - pushed
# - needs coroutine to fetch
# - should use extra cache
# - not gettable equivalent to unset

# conversation_type:
# - via whatever service
# - pushed
# - may not be fetchable at all
# - needs extra cache
# - not gettable equivalent to unset

# avatar:
# - via avatar
# - metadata and data is pushed
# - fetch may require coroutine
# - get may not work despite changed signal
# - needs extra cache, and needs caching to disk
# - not gettable may mean that fetch hasn’t completed yet or
#   that no avatar is set -> tempfail and permfail distinction needed

# chat states:
# - via messages / archive most likely
# - pushed
# - fetch is not possible
# - needs cache, no persistence


class PresenceMetadata(enum.Enum):
    STANZA = 'stanza'


class AbstractMetadataProviderService(metaclass=abc.ABCMeta):
    """
    .. signal:: on_changed(key, peer, value)

        Emits when metadata changes.
    """

    # service mixin!
    PUBLISHED_KEYS = ...

    on_changed = aioxmpp.callbacks.Signal()

    @abc.abstractmethod
    @asyncio.coroutine
    def fetch(self, key: object, peer: aioxmpp.JID):
        """
        Fetch the metadata value.

        Must not fail with :class:`Tempfail`.
        """

    def get(self, key: object, peer: aioxmpp.JID):
        """
        Return the metadata value.

        :raises Tempfail: if the metadata value is currently unavailable or if
            a :meth:`fetch` call is required to obtain it.
        """

        raise Tempfail((key, peer))


class PresenceMetadataProviderService(AbstractMetadataProviderService,
                                      aioxmpp.service.Service):
    ORDER_AFTER = [
        aioxmpp.PresenceClient,
    ]

    PUBLISHED_KEYS = PresenceMetadata

    def __init__(self, client, **kwargs):
        super().__init__(client, **kwargs)
        self._svc = self.dependencies[aioxmpp.PresenceClient]

    @aioxmpp.service.depsignal(aioxmpp.PresenceClient, "on_available")
    def _on_available(self, full_jid, stanza):
        self.on_changed(PresenceMetadata.STANZA, full_jid, stanza)

    @aioxmpp.service.depsignal(aioxmpp.PresenceClient, "on_changed")
    def _on_changed(self, full_jid, stanza):
        self.on_changed(PresenceMetadata.STANZA, full_jid, stanza)

    @aioxmpp.service.depsignal(aioxmpp.PresenceClient, "on_unavailable")
    def _on_unavailable(self, full_jid, stanza):
        self.on_changed(PresenceMetadata.STANZA, full_jid, stanza)

    @asyncio.coroutine
    def fetch(self, key: PresenceMetadata, peer: aioxmpp.JID):
        return self.get(key, peer)

    def get(self, key: PresenceMetadata, peer: aioxmpp.JID):
        assert key == PresenceMetadata.STANZA
        if peer.is_bare:
            stanza = self._svc.get_most_available_stanza(peer)
        else:
            stanza = self._svc.get_stanza(peer)

        if stanza is None:
            return None

        return stanza


class AbstractMetadataProvider(metaclass=abc.ABCMeta):
    on_changed = aioxmpp.callbacks.Signal()

    @abc.abstractproperty
    def published_keys(self) -> typing.Iterable[object]:
        pass

    @abc.abstractmethod
    @asyncio.coroutine
    def fetch(self,
              key: object,
              account: jclib.identity.Account,
              peer: aioxmpp.JID) -> object:
        pass

    def get(self,
            key: object,
            account: jclib.identity.Account,
            peer: aioxmpp.JID) -> object:
        raise Tempfail((key, account, peer))


class SynthesisMetadataProvider(AbstractMetadataProvider):
    @staticmethod
    def join_or(key, account, peer, values):
        for value in values:
            if value:
                return value
        raise Tempfail

    def __init__(self, key, backends, join_func=join_or):
        self._published_keys = (key,)
        super().__init__()
        self._backends = backends
        self._join_func = join_func

    @property
    def published_keys(self):
        return self._published_keys

    @asyncio.coroutine
    def fetch(self,
              key: object,
              account: jclib.identity.Account,
              peer: aioxmpp.JID):
        funcs = []
        for backend in self._backends:
            funcs.append(backend.fetch(key, account, peer))

        return self._join_func(
            key, account, peer,
            (yield from asyncio.gather(*funcs))
        )

    def get(self, key, account, peer):
        return self._join_func(
            key, account, peer,
            [
                backend.get(key, account, peer)
                for backend in self._backends
            ]
        )


class ServiceMetadataProvider(AbstractMetadataProvider):
    def __init__(self,
                 service_class: type,
                 client: jclib.client.Client):
        self._published_keys = tuple(service_class.PUBLISHED_KEYS)
        super().__init__()
        self._service_class = service_class
        self._client = client
        self._client.on_client_prepare.connect(self._on_client_prepare)
        self._client.on_client_stopped.connect(self._on_client_stopped)
        self._instances = {}

    @property
    def published_keys(self):
        return self._published_keys

    def _forwarder(self, account, dest):
        @functools.wraps(dest)
        def f(key, *args):
            return dest(key, account, *args)
        return f

    def _on_client_prepare(self, account, client):
        svc = client.summon(self._service_class)
        tokens = [
            (
                svc.on_changed,
                svc.on_changed.connect(
                    self._forwarder(account, self.on_changed)
                )
            ),
        ]

        self._instances[account] = (
            client,
            svc,
            tokens,
        )

    def _on_client_stopped(self, account, client):
        _, _, tokens = self._instances.pop(account)
        for signal, token in tokens:
            signal.disconnect(token)

    def _get_service(self, account: jclib.identity.Account):
        _, svc, _ = self._instances[account]
        return svc

    @asyncio.coroutine
    def fetch(self,
              key: object,
              account: jclib.identity.Account,
              peer: aioxmpp.JID):
        return (yield from self._get_service(account).fetch(key, peer))

    def get(self,
            key: object,
            account: jclib.identity.Account,
            peer: aioxmpp.JID):
        return self._get_service(account).get(key, peer)

    def __repr__(self):
        return "<{}.{} service={!r} [provides: {!r}]>".format(
            type(self).__module__,
            type(self).__qualname__,
            self._service_class,
            self.published_keys,
        )


class LRUMetadataProvider(ServiceMetadataProvider):
    def __init__(self, service_class, client, *, cache_size=128):
        super().__init__(service_class, client)
        self._cache_size = cache_size
        self._caches = {}
        for key in self.published_keys:
            self._caches[key] = aioxmpp.cache.LRUDict()
            self._caches[key].maxsize = cache_size
        self.on_changed.connect(self._on_changed)

    def _on_changed(self, key, account, peer, value):
        cache = self._caches[key]
        if value is None:
            cache.pop((account, peer), None)
        else:
            cache[account, peer] = value

    @asyncio.coroutine
    def fetch(self,
              key: object,
              account: jclib.identity.Account,
              peer: aioxmpp.JID) -> object:
        existing = self._caches[key].get((account, peer))
        result = yield from self._get_service(account).fetch(key, peer)
        print(existing, result)
        if result != existing:
            self.on_changed(key, account, peer, result)
        return result

    def get(self,
            key: object,
            account: jclib.identity.Account,
            peer: aioxmpp.JID) -> object:
        try:
            return self._get_service(account).get(key, peer)
        except Tempfail:
            # need to check Tempfail first because it inherits from KeyError
            # value currently not available -> try to use cached value
            pass
        except KeyError:
            # account not connected, raise
            raise

        return self._caches[key].get((account, peer))

    def __repr__(self):
        return "<{}.{} cache_size={!r} service={!r} [provides: {!r}]>".format(
            type(self).__module__,
            type(self).__qualname__,
            self._cache_size,
            self._service_class,
            self.published_keys,
        )


def presence_metadata_provider(client: jclib.client.Client):
    return ServiceMetadataProvider(PresenceMetadataProviderService, client)


class MetadataFrontend:
    def __init__(self):
        self._provider_map = {}
        self._signals = {}

    def register_provider(self, provider: AbstractMetadataProvider):
        if any(key in self._provider_map for key in provider.published_keys):
            raise ValueError(
                "key conflict between new provider and existing providers"
            )

        for key in provider.published_keys:
            self._provider_map[key] = provider
            self._signals[key] = aioxmpp.callbacks.AdHocSignal()

        provider.on_changed.connect(self._distribute_on_changed)

    def _distribute_on_changed(self,
                               key: object,
                               account: jclib.identity.Account,
                               peer: aioxmpp.JID,
                               value: object):
        try:
            signal = self._signals[key]
        except KeyError:
            return

        signal(key, account, peer, value)

    @asyncio.coroutine
    def fetch(self,
              key: object,
              account: jclib.identity.Account,
              peer: aioxmpp.JID) -> object:
        try:
            provider = self._provider_map[key]
        except KeyError:
            raise LookupError("no provider for key: {!r}".format(key))

        return (yield from provider.fetch(key, account, peer))

    def get(self,
            key: object,
            account: jclib.identity.Account,
            peer: aioxmpp.JID) -> object:
        try:
            provider = self._provider_map[key]
        except KeyError:
            raise LookupError("no provider for key: {!r}".format(key))

        return provider.get(key, account, peer)

    def changed_signal(self, key: object) -> aioxmpp.callbacks.AdHocSignal:
        try:
            return self._signals[key]
        except KeyError:
            raise LookupError("no provider for key: {!r}".format(key))
