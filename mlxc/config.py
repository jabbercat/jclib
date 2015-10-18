import itertools
import pathlib
import urllib.parse

import aioxmpp.callbacks

import mlxc.utils as utils


def escape_dirname(path):
    return urllib.parse.quote(path, safe=" ")


def unescape_dirname(path):
    return urllib.parse.unquote(path)


class ConfigManager:
    on_writeback = aioxmpp.callbacks.Signal()

    def __init__(self, pathprovider):
        super().__init__()
        self.pathprovider = pathprovider

    def get_config_paths(self, uid, filename):
        escaped = escape_dirname(uid)
        return (
            self.pathprovider.user_config_dir() / escaped / filename,
            [
                path / escaped / filename
                for path
                in reversed(list(self.pathprovider.site_config_dirs()))
            ]
        )

    def open_single(self, uid, filename, *, mode="rb", **kwargs):
        user_path, site_paths = self.get_config_paths(uid, filename)
        if utils.is_write_mode(mode):
            user_path.parent.mkdir(parents=True, exist_ok=True)
            return user_path.open(mode, **kwargs)

        excs = []
        for path in [user_path] + site_paths:
            try:
                return path.open(mode, **kwargs)
            except OSError as exc:
                excs.append(exc)
                continue
        raise aioxmpp.errors.MultiOSError(
            "could not open {!r} for uid {}".format(filename, uid),
            excs)

    def open_incremental(self, uid, filename, *, mode="rb", **kwargs):
        user_path, site_paths = self.get_config_paths(uid, filename)
        if not utils.is_write_mode(mode):
            for path in reversed(site_paths):
                try:
                    yield path.open(mode, **kwargs), True
                except OSError:
                    continue

        try:
            yield user_path.open(mode, **kwargs), False
        except OSError:
            pass

    def load_incremental(self, uid, filename, callback):
        for f, sitewide in self.open_incremental(uid, filename):
            with f:
                callback(f, sitewide)

    def writeback(self):
        self.on_writeback()


class XDGProvider:
    def __init__(self, appname):
        import xdg.BaseDirectory
        self._impl = xdg.BaseDirectory
        self.appname = appname

    def user_config_dir(self):
        return pathlib.Path(self._impl.xdg_config_home) / self.appname

    def site_config_dirs(self):
        for path in self._impl.xdg_config_dirs[1:]:
            yield pathlib.Path(path) / self.appname

    def user_data_dir(self):
        return pathlib.Path(self._impl.xdg_data_home) / self.appname

    def site_data_dirs(self):
        for path in self._impl.xdg_data_dirs[1:]:
            yield pathlib.Path(path) / self.appname
