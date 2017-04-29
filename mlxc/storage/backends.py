import abc
import pathlib

from .common import StorageType


class Backend(metaclass=abc.ABCMeta):
    @abc.abstractmethod
    def type_base_paths(self, type_, writable):
        """
        Return an iterable of base paths to search for a given type and
        access mode.

        :param type_: The type of data to be read/written.
        :type type_: :class:`StroageType`
        :param writable: If set to true, only writable paths are returned.
        :type writable: :class:`bool`
        :return: An iterable of paths which can be used.
        :rtype: :class:`~collections.abc.Iterable` of :class:`pathlib.Path`

        The paths returned depend on the platform and environment. When
        multiple paths are returned, they are ordered by precedence with the
        most precedent path first.

        Only a single writable path is ever returned, and it is equal to the
        most precedent readable path so that data written is always read back.

        The paths are not guaranteed to exist, however, creation of directories
        to make them usable will work for writable paths.
        """


class XDGBackend(Backend):
    def __init__(self, appname):
        import xdg.BaseDirectory
        super().__init__()
        self._impl = xdg.BaseDirectory
        self.appname = appname

    def type_base_paths(self, type_, writable):
        if type_ == StorageType.CACHE:
            return [pathlib.Path(self._impl.xdg_cache_home) / self.appname]

        elif type_ == StorageType.DATA:
            if writable:
                return [pathlib.Path(self._impl.xdg_data_home) / self.appname]
            else:
                return [
                    pathlib.Path(p) / self.appname
                    for p in self._impl.xdg_data_dirs
                ]

        elif type_ == StorageType.CONFIG:
            if writable:
                return [pathlib.Path(self._impl.xdg_config_home) /
                        self.appname]
            else:
                return [
                    pathlib.Path(p) / self.appname
                    for p in self._impl.xdg_config_dirs
                ]

        raise ValueError("unknown StorageType")
