import asyncio
import functools
import logging
import os
import signal
import time

import asyncio_xmpp.presence

import mlxc.client
import mlxc.singletonify

from . import roster

from mlxc.utils import *

logger = logging.getLogger(__name__)

class QuitException(Exception):
    pass

class MLXCQt:
    """
    This class is a singleton \o/.
    """

    def __init__(self, loop):
        MLXCQt.__instance = self
        self._loop = loop
        self._loop.add_signal_handler(
            signal.SIGINT,
            self.handle_sigint_sigterm)
        self._loop.add_signal_handler(
            signal.SIGTERM,
            self.handle_sigint_sigterm)
        self._future = asyncio.Future()
        self._terminated_at = None
        self.returncode = 0
        self._task = logged_async(self.main(), loop=loop)

    def quit(self):
        if self._future.done():
            return
        self._future.set_exception(QuitException())

    def handle_sigint_sigterm(self):
        print()
        logger.debug("SIGINT / SIGTERM received")
        if self._terminated_at is not None and time.monotonic() - self._terminated_at > 3:
            logger.error("SIGTERM received several times, killing myself :(")
            self._loop.stop()
            return
        self.quit()
        if self._terminated_at is None:
            self._terminated_at = time.monotonic()

    @asyncio.coroutine
    def main(self):
        try:
            self._singleton = mlxc.singletonify.get_singleton_impl()
        except RuntimeError:
            logger.warning("failed to acquire singleton implementation for this platform",
                           exc_info=True)
            self._singleton = None
        else:
            logger.debug("starting singleton implementation")
            try:
                success = yield from self._singleton.start()
            except:
                logger.exception("singleton acquiration failed for unknown reason")
                self._loop.stop()
                return
            if not success:
                logger.error("singleton acquiration failed")
                print("Another instance of MLXC is running. Terminating.")
                self._loop.stop()

        try:
            self._client = roster.QtClient()
            yield from self._client.load()
            self._roster = roster.Roster(self._client)
            self._roster.show()
            try:
                yield from self._future
            except QuitException:
                pass
            yield from self._client.set_global_presence(
                asyncio_xmpp.presence.PresenceState()
            )
            yield from self._client.wait_for_all()
        except Exception:
            logger.exception("fatal error")
            if self.returncode is None:
                self.returncode = 1
            raise
        else:
            yield from self._client.save()
        finally:
            logger.debug("stopping singleton implementation")
            yield from self._singleton.stop()
            logger.debug("shutting down event loop")
            self._loop.remove_signal_handler(signal.SIGINT)
            self._loop.remove_signal_handler(signal.SIGTERM)
            self._loop.stop()


    @classmethod
    def get_instance(cls):
        try:
            return cls.__instance
        except AttributeError:
            raise RuntimeError("MLXCQt has not been initialized yet.")

def async_user_task_done(task):
    try:
        task.result()
    except:
        logger.exception("user task failed:")

def main_done(loop, task):
    try:
        task.result()
    except:
        logger.exception("main task failed:")
        loop.stop()

def run_async_user_task(coro):
    task = asyncio.async(coro)
    task.add_done_callback(async_user_task_done)
