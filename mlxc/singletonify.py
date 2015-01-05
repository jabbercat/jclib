import asyncio
import logging
import os
import socket
import stat

import xdg.BaseDirectory

import mlxc.xdg

class _GlobalSingletonBase:
    def __init__(self, loop):
        super().__init__()
        self._loop = loop

class _UnixGlobalSingleton(_GlobalSingletonBase):
    SINGLETON_NAME = "\0unix:socket:net.zombofant.mlxc"

    def __init__(self, loop):
        super().__init__(loop)
        self._listener = None
        self._socket_path = None
        self.logger = logging.getLogger(__name__ + ".unix")

    def _on_connected(self, stream_reader, stream_writer):
        stream_writer.close()

    @asyncio.coroutine
    def start(self):
        try:
            socket_dir = os.path.join(
                xdg.BaseDirectory.get_runtime_dir(),
                *mlxc.xdg.XDG_RESOURCE)
            try:
                os.makedirs(socket_dir)
            except FileExistsError:
                pass
        except KeyError:
            self.logger.warning("XDG_RUNTIME_DIR unset, using cache")
            socket_dir = xdg.BaseDirectory.save_cache_path(
                *mlxc.xdg.XDG_RESOURCE)

        self._socket_path = os.path.join(
            socket_dir, "singletonify.sock")

        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        # set permissions /before/ binding
        os.chmod(sock.fileno(), stat.S_ISVTX | stat.S_IRWXU)
        try:
            sock.bind(self._socket_path)
            self._listener = yield from asyncio.start_unix_server(
                self._on_connected,
                sock=sock,
                loop=self._loop)
        except OSError:
            self.logger.warning("failed to create listening socket at %s",
                                self._socket_path,
                                exc_info=True)
            return False
        return True

    @asyncio.coroutine
    def stop(self):
        try:
            os.unlink(self._socket_path)
        except OSError:
            logger.warning("failed to remove socket", exc_info=True)
        self._listener.close()
        yield from self._listener.wait_closed()

def get_singleton_impl(for_loop=None):
    for_loop = for_loop or asyncio.get_event_loop()
    if hasattr(for_loop, "create_unix_server"):
        return _UnixGlobalSingleton(for_loop)
    raise RuntimeError("No singleton implementation for this platform")
