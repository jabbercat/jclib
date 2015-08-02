import asyncio
import os
import os.path
import socket
import stat

import xdg.BaseDirectory

import mlxc.xdginfo


class _UnixGlobalSingleton:
    def __init__(self, loop):
        if not hasattr(loop, "create_unix_server"):
            raise RuntimeError("not supported on this platform")

        super().__init__()
        self.loop = loop
        self.listener = None
        self.socket_path = None

    def _on_connected(self, reader, writer):
        pass

    @classmethod
    def get_socket_path(cls):
        return os.path.join(
            xdg.BaseDirectory.get_runtime_dir(),
            mlxc.xdginfo.RESOURCE
        )

    @classmethod
    def bind_socket(cls, path):
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            os.chmod(sock.fileno(), stat.S_ISVTX | stat.S_IRWXU)
            sock.bind(path)
        except OSError:
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
