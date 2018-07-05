import asyncio
import logging

from datetime import timedelta

import aioxmpp.callbacks

import jclib.storage
import jclib.utils


logger = logging.getLogger(__name__)


class WriteManager:
    """
    Manage storage writebacks.

    :param delay: Approximate lower bound for the delay between the request
        for a writeback and the actual writeback.
    :param max_delay: Hard upper bound for the delay between the request for
        a writeback and the actual writeback.

    Writebacks are **not** emitted regularly; instead, users have to
    call :meth:`request_writeback` to schedule a writeback. When a writeback
    occurs, :meth:`on_writeback` is emitted.

    .. signal:: on_writeback()

        Emits when a writeback occurs.

    .. automethod:: request_writeback
    """

    on_writeback = aioxmpp.callbacks.Signal()

    def __init__(self, delay, max_delay, *, loop=None):
        super().__init__()
        self._scheduler = jclib.utils.DelayedInvocation(
            self._writeback_scheduled,
            delay,
            max_delay=max_delay,
            loop=loop,
        )

    def _writeback_scheduled(self, invocations):
        logger.debug("executing scheduled writeback for %d clients",
                     len(invocations))
        self.on_writeback()
        jclib.storage.xml.flush_all()

    def request_writeback(self):
        """
        Schedule a writeback in at most `max_delay` and at least approximately
        `delay` seconds.
        """
        self._scheduler()
