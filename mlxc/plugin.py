import asyncio

import aioxmpp.service


class Base(metaclass=aioxmpp.service.Meta):
    """
    Base class to implement a plug-in for MLXC. Plug-in classes should inherit
    from this class. This class uses the :class:`aioxmpp.service.Meta`
    metaclass, thus allowing use of :attr:`~aioxmpp.service.Meta.ORDER_BEFORE`
    and :attr:`~aioxmpp.service.Meta.ORDER_AFTER` attributes.

    These attributes are respected by the client when loading and unloading
    plug-ins.
    """

    def __init__(self, client):
        super().__init__()
        self._client = client

    @property
    def client(self):
        return self._client

    @asyncio.coroutine
    def _close(self):
        pass

    @asyncio.coroutine
    def close(self):
        yield from self._close()
        self._client = None
