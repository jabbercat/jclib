import asyncio
import logging

from datetime import timedelta

import aioxmpp.callbacks

import mlxc.storage


logger = logging.getLogger(__name__)


class WriteManager:
    """
    Manage storage writebacks.

    :param writeback_interval: The interval in which the :meth:`on_writeback`
        signal is emitted.
    :type writeback_interval: :class:`datetime.timedelta`

    The write manager has a single signal which is periodically called. The
    call interval is determined by `writeback_interval`.

    .. signal:: on_writeback()

        Emits when a scheduled writeback occurs.

    .. autoattribute:: writeback_interval

    .. automethod:: request_writeback
    """

    on_writeback = aioxmpp.callbacks.Signal()

    def __init__(self, writeback_interval: timedelta):
        super().__init__()
        self._writeback_interval = writeback_interval
        self._wakeup = asyncio.Event()
        self._task = asyncio.ensure_future(self._loop())

    @property
    def writeback_interval(self) -> timedelta:
        """
        The interval in which the :meth:`on_writeback` signal is emitted.

        Writing this attribute changes the interval and also schedules a
        writeback as if per :meth:`request_writeback`.
        """
        return self._writeback_interval

    @writeback_interval.setter
    def writeback_interval(self, value: timedelta):
        self._writeback_interval = value
        self._wakeup.set()
        logger.debug(
            "writeback interval changed to %s, scheduling writeback now",
            value
        )

    @asyncio.coroutine
    def _loop(self):
        while True:
            logger.debug("next writeback in %s seconds",
                         self._writeback_interval)
            yield from asyncio.wait(
                [
                    asyncio.sleep(self._writeback_interval.total_seconds()),
                    self._wakeup.wait()
                ],
                return_when=asyncio.FIRST_COMPLETED
            )
            self._wakeup.clear()
            logger.debug("writeback triggered")
            self.on_writeback()
            mlxc.storage.xml.flush_all()

    def close(self):
        """
        Stop the writeback loop.
        """
        self._task.cancel()

    def request_writeback(self):
        """
        Schedule a writeback soon.

        The writeback will occur during the event loop step. Multiple calls to
        :meth:`request_writeback` without a yield inbetween will only lead to
        a single writeback being issued.
        """
        self._wakeup.set()
        logger.debug("writeback requested")
