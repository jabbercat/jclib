import abc
import contextlib
import logging
import os
import pathlib
import tempfile
import urllib.parse

import aioxmpp.callbacks

import mlxc.utils as utils


UNIX_APPNAME = "mlxc.zombofant.net"


logger = logging.getLogger(__name__)


def escape_dirname(path):
    return urllib.parse.quote(path, safe=" ")


def unescape_dirname(path):
    return urllib.parse.unquote(path)


def mkdir_exist_ok(path):
    try:
        path.mkdir(parents=True)
    except FileExistsError:
        if not path.is_dir():
            raise


@contextlib.contextmanager
def safe_writer(destpath, mode="wb"):
    destpath = pathlib.Path(destpath)
    with tempfile.NamedTemporaryFile(
            mode=mode,
            dir=str(destpath.parent),
            delete=False) as tmpfile:
        try:
            yield tmpfile
        except:
            os.unlink(tmpfile.name)
            raise
        else:
            os.replace(tmpfile.name, str(destpath))


class SimpleConfigurable(metaclass=abc.ABCMeta):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        config_manager.on_writeback.connect(self.save)

    @abc.abstractmethod
    def _do_load(self, f):
        pass

    @abc.abstractmethod
    def _do_save(self, f):
        pass

    def load(self):
        try:
            with config_manager.open_single(
                    self.UID,
                    self.FILENAME) as f:
                self._do_load(f)
        except OSError:
            logger.info(
                "failed to load data for %s.%s",
                type(self).__module__,
                type(self).__name__,
            )

    def save(self):
        logger.info(
            "saving data for %s.%s",
            type(self).__module__,
            type(self).__name__,
        )
        user_path, _ = config_manager.get_config_paths(
            self.UID, self.FILENAME
        )
        with safe_writer(user_path) as f:
            self._do_save(f)


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
            mkdir_exist_ok(user_path.parent)
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

    def cache_dir(self):
        return pathlib.Path(self._impl.xdg_cache_home) / self.appname

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


def make_config_manager():
    try:
        provider = XDGProvider(UNIX_APPNAME)
    except ImportError:
        raise RuntimeError("no path provider for platform") from None
    return ConfigManager(provider)


config_manager = make_config_manager()
