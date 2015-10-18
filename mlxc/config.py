import itertools
import pathlib
import urllib.parse

import aioxmpp.callbacks


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

    def get_non_incremental_config_file(self, uid, filename):
        user_path, site_paths = self.get_config_paths(uid, filename)
        for path in [user_path] + site_paths:
            try:
                return path.open("rb")
            except OSError:
                continue
        raise FileNotFoundError()

    def get_incremental_config_files(self, uid, filename):
        user_path, site_paths = self.get_config_paths(uid, filename)
        for path in reversed(site_paths):
            try:
                yield path.open("rb"), True
            except OSError:
                continue

        try:
            yield user_path.open("rb"), False
        except OSError:
            pass

    def load_incremental(self, uid, filename, callback):
        for f, sitewide in self.get_incremental_config_files(uid, filename):
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
