import asyncio
import logging
import os
import os.path
import signal
import socket
import stat
import time

import xdg.BaseDirectory

import mlxc.config

from . import identity, client, conversation, utils


logger = logging.getLogger(__spec__.name)


class _UnixGlobalSingleton:
    def __init__(self, loop):
        if not hasattr(loop, "create_unix_server"):
            raise RuntimeError("not supported on this platform")

        super().__init__()
        self.loop = loop
        self.listener = None
        self.socket_path = None

    def _on_connected(self, reader, writer):
        writer.close()

    @classmethod
    def test_liveness(self, path):
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM, 0)
        try:
            sock.connect(path)
            return True
        except ConnectionError:
            logger.debug("peer socket at %s is dead", path)
            return None
        finally:
            sock.close()

    @classmethod
    def get_socket_path(cls):
        return os.path.join(
            xdg.BaseDirectory.get_runtime_dir(),
            mlxc.config.UNIX_APPNAME
        )

    @classmethod
    def bind_socket(cls, path):
        try:
            os.makedirs(os.path.dirname(path), mode=0o700)
        except FileExistsError:
            pass
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            os.chmod(sock.fileno(), stat.S_ISVTX | stat.S_IRWXU)
        except OSError:
            sock.close()
            raise

        try:
            sock.bind(path)
        except OSError:
            if cls.test_liveness(path) is None:
                logger.info("removing stale socket from %s", path)
                os.unlink(path)
                sock.bind(path)
                return sock
            sock.close()
            raise
        return sock

    @asyncio.coroutine
    def start(self):
        base_path = self.get_socket_path()
        path = os.path.join(base_path, "singletonify.sock")
        try:
            sock = self.bind_socket(path)
        except OSError:
            logger.warning("failed to acquire singleton", exc_info=True)
            return False

        try:
            self.listener = yield from asyncio.start_unix_server(
                self._on_connected,
                sock=sock,
                loop=self.loop
            )
        except OSError:
            sock.close()
            return False

        self.socket_path = path

        return True

    @asyncio.coroutine
    def stop(self):
        if self.listener is None:
            raise RuntimeError("Singleton not started")

        try:
            os.unlink(self.socket_path)
        except OSError:
            pass

        self.listener.close()
        yield from self.listener.wait_closed()


def get_singleton_impl(loop):
    if hasattr(loop, "create_unix_server"):
        return _UnixGlobalSingleton(loop)


class Main:
    Identities = identity.Identities
    Client = client.Client

    def __init__(self, loop):
        super().__init__()
        self.loop = loop
        self.identities = self.Identities()
        self.client = self.Client(self.identities)

        self._terminated_at = None

    def setup(self):
        self.loop.add_signal_handler(
            signal.SIGINT,
            self.handle_sigint_sigterm
        )
        self.loop.add_signal_handler(
            signal.SIGTERM,
            self.handle_sigint_sigterm
        )
        self.main_future = asyncio.Future(loop=self.loop)

    def teardown(self):
        self.loop.remove_signal_handler(signal.SIGTERM)
        self.loop.remove_signal_handler(signal.SIGINT)
        del self.main_future

    def quit(self):
        if self.main_future.done():
            return

        self.main_future.set_result(0)

    def handle_sigint_sigterm(self):
        if (self._terminated_at is not None and
                (time.monotonic() - self._terminated_at >= 3)):
            self.loop.stop()
            return

        self.quit()

        if self._terminated_at is None:
            self._terminated_at = time.monotonic()

    @asyncio.coroutine
    def acquire_singleton(self):
        try:
            singleton = get_singleton_impl(self.loop)
        except RuntimeError:
            logger.warning(
                "failed to acquire singleton implementation for this platform",
                exc_info=True)
            return None

        try:
            success = yield from singleton.start()
        except Exception:
            logger.exception(
                "singleton acquiration failed for unexpected reason"
            )
            return False

        if not success:
            logger.error("failed to acquire singleton "
                         "(another instance is running)")
            return False

        return singleton

    @asyncio.coroutine
    def run_core(self):
        yield from self.main_future

    @asyncio.coroutine
    def run(self):
        returncode = None
        self.setup()
        try:
            singleton = yield from self.acquire_singleton()
            if singleton is False:
                returncode = 1
                return returncode

            self.identities.load()

            try:
                returncode = yield from self.run_core()
            finally:
                mlxc.config.config_manager.writeback()
                if singleton is not None:
                    yield from singleton.stop()
        except Exception as exc:
            if returncode is None:
                returncode = 1
            logger.exception("failure in Main.run()")
        finally:
            self.teardown()
            return returncode
