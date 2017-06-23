import abc
import asyncio
import base64
import collections
import functools
import hashlib
import io
import pathlib
import urllib.parse
import sys

from datetime import datetime

import sqlalchemy

import aioxmpp.xml

from .. import utils
from .common import StorageLevel
from . import peer_model, identity_model, account_model, common


def encode_jid(jid):
    """
    Encode a :class:`aioxmpp.JID` as relative :class:`pathlib.Path` object.

    The encoding is not reversible. It is consistent independent of the
    environment and reasonably collision-resistant.

    The reason we do the encoding is that file systems may be very unhappy with
    full-length JIDs. Many file systems only allow 255 characters or bytes for
    file names (not path names, the limits on path names are usually much
    higher!). A full-length JID is 3071 bytes.
    """

    jid_b = str(jid).encode("utf-8")
    hashfun = hashlib.sha256()
    hashfun.update(jid_b)
    blob = hashfun.digest()
    full_digest = base64.b32encode(blob).decode("ascii").rstrip("=").lower()

    return pathlib.Path(full_digest[:2]) / full_digest[2:4] / full_digest[4:]


def encode_uuid(uid):
    return pathlib.Path(
        base64.b32encode(uid.bytes).decode("ascii").rstrip("=").lower()
    )


def escape_path_part(part):
    return urllib.parse.quote(part, safe=" ")


def _get_engine(path):
    utils.mkdir_exist_ok(path.parent)
    engine = sqlalchemy.create_engine(
        "sqlite:///{}".format(path),
    )

    # https://stackoverflow.com/questions/1654857/
    @sqlalchemy.event.listens_for(engine, "connect")
    def do_connect(dbapi_connection, connection_record):
        # disable pysqlite's emitting of the BEGIN statement entirely.
        # also stops it from emitting COMMIT before any DDL.
        dbapi_connection.isolation_level = None

    @sqlalchemy.event.listens_for(engine, "begin")
    def do_begin(conn):
        # emit our own BEGIN
        conn.execute("BEGIN")

    return engine


class LevelDescriptor(metaclass=abc.ABCMeta):
    @abc.abstractproperty
    def key_path(self):
        pass


class GlobalLevel(collections.namedtuple("GlobalLevel", [])):
    level = StorageLevel.GLOBAL

    @property
    def key_path(self):
        return pathlib.Path()


class IdentityLevel(collections.namedtuple("IdentityLevel", ["identity"])):
    level = StorageLevel.IDENTITY

    @property
    def key_path(self):
        return encode_uuid(self.identity)


class AccountLevel(collections.namedtuple("AccountLevel", ["account"])):
    level = StorageLevel.ACCOUNT

    @property
    def key_path(self):
        return encode_jid(self.account)


class PeerLevel(collections.namedtuple("PeerLevel", ["identity", "peer"])):
    level = StorageLevel.PEER

    @property
    def key_path(self):
        return encode_uuid(self.identity) / encode_jid(self.peer)


class Frontend:
    def __init__(self, backend):
        super().__init__()
        self._backend = backend

    async def clear(self, level):
        """
        Delete all objects within the given level key, across all storage
        types.

        :param level: The level descriptor of the key to remove.
        :type level: :class:`LevelDescriptor`
        :raises NotImplementedError: if the frontend does not support such
            deletion.
        :raises OSError: if not all data could be deleted.

        A common usecase is when an account/identity/peer has been removed.
        Using the :class:`GlobalLevel` as `level` is not supported.

        The deletion attempts to continue when the first error is encountered.
        The first error is re-raised.

        .. warning::

            This is a *very* destructive operation, which may also take some
            time.
        """
        raise NotImplementedError


class _PerLevelMixin:
    def _get_path(self, type_, level_type, namespace, frontend_name, name):
        return (self._backend.type_base_paths(type_, True)[0] /
                StorageLevel.GLOBAL.value /
                escape_path_part(namespace) /
                frontend_name /
                level_type.value /
                name)


class _PerLevelKeyFileMixin:
    def _get_path(self, type_, level, namespace, name):
        return (self._backend.type_base_paths(type_, True)[0] /
                level.level.value /
                level.key_path /
                escape_path_part(namespace) /
                name)


class DatabaseFrontend(Frontend):
    """
    Storage frontend for accessing :attr:`~.StorageLevel.GLOBAL` SQLite
    databases.

    .. automethod:: connect
    """

    def _get_path(self, type_, namespace, name):
        return (self._backend.type_base_paths(type_, True)[0] /
                StorageLevel.GLOBAL.value /
                escape_path_part(namespace) /
                "db" /
                name)

    @functools.lru_cache(32)
    def connect(self, type_, namespace, name):
        """
        Return a SQLAlchemy sessionmaker for a database.

        :param type_: The storage type of the database.
        :type type_: :class:`StorageType`
        :param namespace: The namespace of the database.
        :type namespace: :class:`str`
        :param name: The name of the database.
        :type name: :class:`str`
        :rtype: :class:`sqlalchemy.orm.sessionmaker`
        :return: A session maker for the given database.

        The sessionmakers returned by this function may be cached and shared.
        """
        path = self._get_path(type_, namespace, name)
        engine = _get_engine(path)
        return sqlalchemy.orm.sessionmaker(bind=engine)


class FileLikeFrontend(metaclass=abc.ABCMeta):
    @abc.abstractmethod
    async def open(self, type_, level, namespace, name, mode="r", *,
                   encoding=None):
        """
        Return a file-like object.

        :param type_: The storage type of the object to open.
        :type type_: :class:`StorageType`
        :param level: The information hierarchy level of the object to open.
        :type level: :class:`LevelDescriptor`
        :param namespace: The namespace of the object.
        :type namespace: :class:`str`
        :param name: The name of the object.
        :type name: :class:`str`
        :param mode: The file open mode to open the object with.
        :type mode: :class:`str` (see :func:`open` and the note below)
        :param encoding: The encoding to use to decode the file if it is
            opened in text mode (see :func:`open`)
        :type encoding: :class:`str` or :data:`None`
        :raises ValueError: if the `encoding` is not :data:`None` for a binary
            `mode`.
        :raises OSError: if the object could not be opened
        :return: The opened file
        :rtype: :class:`io.IOBase` or :class:`io.TextIOBase`, depending on
            `mode`

        Implementations *may* support additional keyword arguments.

        If the `mode` indicates the use of binary mode and `encoding` is not
        :data:`None`, :class:`ValueError` is raised and the object is not
        touched.

        .. note::

            Not all `mode` values supported by :func:`open` may be supported
            by implementations.

            However, the ``r``, ``rb`` (and implicitly ``rt``) modes are
            supported by all implementations.
        """

    @abc.abstractmethod
    async def stat(self, type_, level, namespace, name):
        """
        Return meta-information about an object.

        :param type_: The storage type of the object to look up.
        :type type_: :class:`StorageType`
        :param level: The information hierarchy level of the object to look up.
        :type level: :class:`LevelDescriptor`
        :param namespace: The namespace of the object.
        :type namespace: :class:`str`
        :param name: The name of the object.
        :type name: :class:`str`
        :raises OSError: if the object could not be queried
        :return: A structure (see below for the attributes) describing the
            metadata

        The returned object has the following attributes:

        .. attribute:: st_size

            The size of the object in bytes.

        .. attribute:: st_atime

            The time of last access of the object, as seconds since UNIX epoch,
            or absent if not supported.

        .. attribute:: st_mtime

            The time of last modification of the object, as seconds since
            UNIX epoch, or absent if not supported.

        .. attribute:: st_ctime

            See :attr:`os.stat_result.st_ctime`, or absent if not supported.

        .. attribute:: st_birthtime

            See :attr:`os.stat_result.st_birthtime`, or absent if not
            supported.

        .. note::

            The returned object is not fully compatible with
            :class:`os.stat_result`. Some attributes which are guaranteed to
            be there may be missing with some implementations.
        """

    @abc.abstractmethod
    async def unlink(self, type_, level, namespace, name):
        """
        Delete an object.

        :param type_: The storage type of the object to delete.
        :type type_: :class:`StorageType`
        :param level: The information hierarchy level of the object to delete.
        :type level: :class:`LevelDescriptor`
        :param namespace: The namespace of the object.
        :type namespace: :class:`str`
        :param name: The name of the object.
        :type name: :class:`str`
        :raises OSError: if the object could not be deleted

        The object is deleted from the storage. If the object could not be
        deleted, the :class:`OSError` explaining the cause is (re-)raised.

        Most notably, :class:`FileNotFoundError` is raised if the object does
        not exist.
        """


class SmallBlobFrontend(FileLikeFrontend, Frontend):
    """
    Storage frontend for storing a huge number of small pieces of data.

    This frontend is intended to be used especially with
    :attr:`~.StorageLevel.PEER` level data, i.e. where a high cardinality of
    level keys and/or names exist. Usage with blobs whose average size is above
    a few megabytes is discouraged.

    The storage is backed by one SQLite database per namespace,
    :class:`.StorageType` and :class:`.StorageLevel`. Within each namespace
    and :class:`.StorageType` and :class:`.StorageLevel`, the database is
    shared across all level keys and names.

    This has the key advantage that only a single file is required per
    namespace, :class:`.StorageType` and :class:`.StorageLevel`. In addition,
    the database allows easy assessment of current use of space as well as
    fast deletion of entries which haven’t been used for a long time.

    The :class:`SmallBlobFrontend` supports the :class:`FileLikeFrontend`
    interface, however, :meth:`open` can only be used for reading; to store
    blobs, :meth:`store` must be used. :meth:`stat` supports the
    :attr:`st_atime`, :attr:`st_mtime`, :attr:`st_birthtime`, and
    :attr:`st_size` attributes.

    .. automethod:: store

    .. automethod:: load

    Part of the file-like frontend interface:

    .. automethod:: open

    .. automethod:: stat

    .. automethod:: unlink

    """
    StatTuple = collections.namedtuple(
        "StatTuple",
        [
            "st_size",
            "st_atime",
            "st_mtime",
            "st_birthtime",
        ]
    )

    LEVEL_INFO = {
        StorageLevel.PEER: (
            peer_model.Base,
            peer_model.SmallBlob,
        ),
        StorageLevel.IDENTITY: (
            identity_model.Base,
            identity_model.SmallBlob,
        ),
        StorageLevel.ACCOUNT: (
            account_model.Base,
            account_model.SmallBlob,
        ),
    }

    def _get_path(self, type_, level_type, namespace):
        return (self._backend.type_base_paths(type_, True)[0] /
                StorageLevel.GLOBAL.value /
                namespace /
                "smallblobs" /
                (level_type.value + ".sqlite"))

    def _init_engine(self, engine, level_type):
        if level_type == StorageLevel.GLOBAL:
            raise ValueError("GLOBAL level not supported")

        try:
            base, *_ = self.LEVEL_INFO[level_type]
        except KeyError as exc:
            raise ValueError(
                "unknown storage level: {}".format(exc)
            ) from None

        base.metadata.create_all(engine)

    @functools.lru_cache(32)
    def _get_sessionmaker(self, type_, level_type, namespace):
        path = self._get_path(type_, level_type, namespace)
        engine = _get_engine(path)
        self._init_engine(engine, level_type)
        return sqlalchemy.orm.sessionmaker(bind=engine)

    def _store_blob(self, type_, level, namespace, name, data):
        sessionmaker = self._get_sessionmaker(
            type_,
            level.level,
            namespace)

        _, blob_type, *_ = self.LEVEL_INFO[level.level]

        blob = blob_type.from_level_descriptor(level)
        blob.data = data
        blob.name = name
        blob.touch_mtime()

        with common.session_scope(sessionmaker) as session:
            session.merge(blob)

    def _load_blob(self, type_, level, namespace, name, query, *,
                   touch=False):
        sessionmaker = self._get_sessionmaker(
            type_,
            level.level,
            namespace)

        _, blob_type, *_ = self.LEVEL_INFO[level.level]

        with common.session_scope(sessionmaker) as session:
            info = blob_type.get(session, level, name, query)
            if touch:
                blob_type.get(session, level, name).touch_atime()
            return info

    async def _load_in_executor(self, type_, level, namespace, name, query, *,
                                touch=False):
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            functools.partial(
                self._load_blob,
                type_, level, namespace, name,
                query,
                touch=touch,
            )
        )

    def _unlink_blob(self, type_, level, namespace, name):
        sessionmaker = self._get_sessionmaker(
            type_,
            level.level,
            namespace)

        _, blob_type, *_ = self.LEVEL_INFO[level.level]

        with common.session_scope(sessionmaker) as session:
            return blob_type.filter_by(
                session.query(blob_type), level, name
            ).delete()

    async def _unlink_in_executor(self, type_, level, namespace, name):
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            self._unlink_blob,
            type_, level, namespace, name,
        )

    async def store(self, type_, level, namespace, name, data):
        """
        Store `data` as a small blob.

        :param type_: The storage type to use.
        :type type_: :class:`~.StorageType`
        :param level: The storage level to store the data in.
        :type level: :class:`~.LevelDescriptor`
        :param namespace: The namespace to store the data in.
        :type namespace: :class:`str` (up to 255 UTF-8 bytes)
        :param name: The name of the data.
        :type name: :class:`str` (up to 255 codepoints)
        :param data: Data to store.
        :type data: :class:`bytes`

        The `data` is stored at the specified location. If an object with the
        same name in the same namespace, storage level and storage type exists,
        it is silently overwritten.
        """

        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None,
            self._store_blob,
            type_,
            level,
            namespace,
            name,
            data,
        )

    async def load(self, type_, level, namespace, name):
        """
        Load the data from a small blob.

        :param type_: The storage type to use.
        :type type_: :class:`~.StorageType`
        :param level: The storage level to load the data from.
        :type level: :class:`~.LevelDescriptor`
        :param namespace: The namespace to load the data from.
        :type namespace: :class:`str` (up to 255 UTF-8 bytes)
        :param name: The name of the data.
        :type name: :class:`str` (up to 255 codepoints)
        :raises KeyError: if no data is found with the given parameters.
        :rtype: :class:`bytes`
        :return: The stored data.
        """

        data, = await self._load_in_executor(
            type_, level, namespace, name,
            [
                common.SmallBlobMixin.data,
            ],
            touch=True,
        )
        return data

    async def open(self, type_, level, namespace, name, mode="r", *,
                   encoding=None):
        """
        See :meth:`.FileLikeFrontend.open` for general documentation of the
        :meth:`open` method.

        The following limitations apply:

        * `mode` must be one of ``r``, ``rb``, or ``rt``, otherwise
          :class:`ValueError` is raised.
        """
        if utils.is_write_mode(mode):
            raise ValueError(
                "writable open modes are not supported by SmallBlobFrontend"
            )

        binary_mode = mode.endswith("b")
        if binary_mode and encoding:
            raise ValueError(
                "binary mode doesn't take an encoding argument"
            )

        try:
            raw = await self.load(type_, level, namespace, name)
        except KeyError as exc:
            raise FileNotFoundError(
                "{!r} does not exist in namespace {!r} for {}".format(
                    name,
                    namespace,
                    level,
                )
            ) from exc

        if binary_mode:
            return io.BytesIO(raw)
        else:
            encoding = encoding or sys.getdefaultencoding()
            text = raw.decode(encoding)
            return io.StringIO(text)

    async def stat(self, type_, level, namespace, name):
        """
        See :meth:`.FileLikeFrontend.stat` for general documentation of the
        :meth:`stat` method.

        The following attributes are provided on the result object:

        * ``st_atime`` (updated on each :meth:`load`/:meth:`open`)
        * ``st_mtime`` (updated on each :meth:`store`)
        * ``st_birthtime`` (set if it doesn’t exist when :meth:`store` is
          called)
        * ``st_size``
        """

        epoch = datetime(1970, 1, 1)

        try:
            accessed, created, modified, size = await self._load_in_executor(
                type_, level, namespace, name,
                [
                    common.SmallBlobMixin.accessed,
                    common.SmallBlobMixin.created,
                    common.SmallBlobMixin.modified,
                    sqlalchemy.sql.func.length(common.SmallBlobMixin.data),
                ]
            )
        except KeyError as exc:
            raise FileNotFoundError(
                "{!r} does not exist in namespace {!r} for {}".format(
                    name,
                    namespace,
                    level,
                )
            ) from exc

        return self.StatTuple(
            st_atime=(accessed - epoch).total_seconds(),
            st_birthtime=(created - epoch).total_seconds(),
            st_mtime=(modified - epoch).total_seconds(),
            st_size=size,
        )

    async def unlink(self, type_, level, namespace, name):
        """
        See :meth:`.FileLikeFrontend.unlink` for general documentation of the
        :meth:`unlink` method.
        """

        deleted = await self._unlink_in_executor(type_, level, namespace, name)
        if deleted == 0:
            raise FileNotFoundError(
                "{!r} does not exist in namespace {!r} for {}".format(
                    name,
                    namespace,
                    level,
                )
            )


class LargeBlobFrontend(_PerLevelKeyFileMixin, FileLikeFrontend, Frontend):
    """
    Storage frontend for storing few and large pieces of data.

    This frontend is intended to be used especially with
    non-:attr:`~.StorageLevel.PEER` level data, i.e. where only few numbers of
    level keys and names exist. Usage with :attr:`~.StorageLevel.PEER` is
    discouraged due to the high load it places on the file system.

    Each blob is stored in its own file.

    The :class:`LargeBlobFrontend` supports the :class:`FileLikeFrontend`
    interface. :meth:`stat` supports all attributes :class:`os.stat_result`
    supports.

    .. automethod:: open

    .. automethod:: stat

    .. automethod:: unlink
    """

    async def open(self, type_, level, namespace, name, mode="r", **kwargs):
        """
        See :meth:`~.FileLikeFrontend.open`.
        """

        path = self._get_path(
            type_,
            level,
            namespace,
            pathlib.Path("largeblobs") / name,
        )

        if utils.is_write_mode(mode):
            utils.mkdir_exist_ok(path.parent)

        return path.open(mode, **kwargs)

    async def stat(self, type_, level, namespace, name):
        """
        See :meth:`~.FileLikeFrontend.stat`.
        """

        path = self._get_path(
            type_,
            level,
            namespace,
            pathlib.Path("largeblobs") / name,
        )
        return path.stat()

    async def unlink(self, type_, level, namespace, name):
        """
        See :meth:`~.FileLikeFrontend.unlink`.
        """

        path = self._get_path(
            type_,
            level,
            namespace,
            pathlib.Path("largeblobs") / name,
        )
        return path.unlink()


class AppendFrontend(_PerLevelKeyFileMixin, Frontend):
    """
    Storage frontend for data on which only append and read operations are
    made.
    """

    def submit(self, type_, level, namespace, name, data, ts=None):
        now = ts or datetime.utcnow()
        path = self._get_path(
            type_,
            level,
            namespace,
            pathlib.Path("append") /
            str(now.year) /
            "{:02d}-{:02d}".format(now.month, now.day) /
            name,
        )
        utils.mkdir_exist_ok(path.parent)
        with path.open("ab") as f:
            f.write(data)


class XMLFrontend(Frontend):
    """
    Manage snippets of XSO-defined XML data.

    The snippet XSO definitions need to be registered before they can be read
    or written. Data is stored in a single file for each level type and type
    combination.
    """

    LEVEL_INFO = {
        StorageLevel.IDENTITY: (
            identity_model.XMLStorage,
            lambda x: (x.level,),
            lambda x: x.identity.bytes
        ),
        StorageLevel.ACCOUNT: (
            account_model.XMLStorage,
            lambda x: (x.level,),
            lambda x: x.account
        ),
        StorageLevel.PEER: (
            peer_model.XMLStorage,
            lambda x: (x.level, x.identity),
            lambda x: (x.identity.bytes, x.peer)
        ),
    }

    def __init__(self, backend):
        super().__init__(backend)
        self.__open_storages = {}

    def _get_path(self, type_, level_type, identity=None):
        if level_type == StorageLevel.PEER:
            return (self._backend.type_base_paths(type_, True)[0] /
                    StorageLevel.IDENTITY.value /
                    encode_uuid(identity) /
                    escape_path_part("dns:mlxc.zombofant.net") /
                    "xml-storage" /
                    "{}.xml".format(level_type.value))
        else:
            return (self._backend.type_base_paths(type_, True)[0] /
                    StorageLevel.GLOBAL.value /
                    escape_path_part("dns:mlxc.zombofant.net") /
                    "xml-storage" /
                    "{}.xml".format(level_type.value))

    def _load(self, type_, level):
        path = self._get_path(
            type_,
            level.level,
            identity=getattr(level, "identity", None)
        )

        storage_cls, _, _ = self.LEVEL_INFO[level.level]

        try:
            with path.open("rb") as f:
                return aioxmpp.xml.read_single_xso(
                    f,
                    storage_cls,
                )
        except FileNotFoundError:
            return storage_cls()

    def _save(self, data, type_, level_type, *args):
        path = self._get_path(
            type_,
            level_type,
            *args,
        )
        utils.mkdir_exist_ok(path.parent)

        with utils.safe_writer(path) as f:
            aioxmpp.xml.write_single_xso(data, f)

    def _open(self, type_, level):
        _, cache_key_func, _ = self.LEVEL_INFO[level.level]
        cache_key = cache_key_func(level)
        try:
            return self.__open_storages[type_, cache_key]
        except KeyError:
            data = self._load(type_, level)
            self.__open_storages[type_, cache_key] = data
            return data

    @classmethod
    def register(cls, level_type, xso_type):
        """
        Register an XSO type for use with a level type.
        """
        storage_cls, _, _ = cls.LEVEL_INFO[level_type]
        for item_cls in storage_cls.items.type_.get_xso_types():
            item_cls.register_child(
                item_cls.data,
                xso_type,
            )

    def get_level_keys(self, type_, level_type):
        """
        Return all level keys which exist.

        This operation opens the corresponding XML storage.
        """
        return self._open(type_, level_type).items.keys()

    def get(self, type_, level, xso_type):
        """
        Return the first instance of an XSO.

        This operation opens the corresponding XML storage.

        .. note::

            Objects returned by this method **must not** be modified, unless
            they are queued for writing using :meth:`put` afterwards.

            Otherwise, it is possible that changes are partially or not at all
            written back to disk.
        """
        items = self.get_all(type_, level, xso_type)
        try:
            return items[0]
        except IndexError:
            return None

    def get_all(self, type_, level, xso_type):
        """
        Return all instances of an XSO.

        If there is no data for the given level and xso_type, an empty iterable
        is returned.

        This operation opens the corresponding XML storage.

        .. note::

            Objects returned by this method **must not** be modified, unless
            they are queued for writing using :meth:`put` afterwards.

            Otherwise, it is possible that changes are partially or not at all
            written back to disk.
        """
        data = self._open(type_, level)
        _, _, key_func = self.LEVEL_INFO[level.level]
        try:
            return data.items[key_func(level)][xso_type]
        except KeyError:
            return aioxmpp.xso.model.XSOList()

    @staticmethod
    def _put_into(items, key, xso):
        if isinstance(xso, aioxmpp.xso.XSO):
            xso_type = type(xso)
            xsos = [xso]
        else:
            xsos = list(xso)
            xso_type = type(xsos[0])

        try:
            data = items[key]
        except KeyError:
            data = {
                xso_type: aioxmpp.xso.model.XSOList(xsos)
            }
            items[key] = data
            return

        try:
            xso_items = data[xso_type]
        except KeyError:
            data[xso_type] = aioxmpp.xso.model.XSOList(xsos)
            return

        xso_items[:] = xsos

    def put(self, type_, level, xso):
        """
        Put one or more XSOs.

        The data is not written to disk immediately. It is required to call
        :meth:`flush` or :meth:`flush_all` to force a writeback to disk.

        However, it may be required to acquire a lock to prevent a concurrent
        flush operation to be disturbed, which is why this method is a
        coroutine method.
        """
        data = self._open(type_, level)
        _, _, key_func = self.LEVEL_INFO[level.level]
        self._put_into(data.items, key_func(level), xso)

    def _writeback(self, type_, key):
        try:
            data = self.__open_storages[type_, key]
        except KeyError:
            return
        self._save(data, type_, *key)

    def flush_all(self):
        """
        Write back all open XML storages and closes them.
        """
        for type_, key in self.__open_storages.keys():
            self._writeback(type_, key)
