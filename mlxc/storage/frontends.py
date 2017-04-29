import abc
import asyncio
import base64
import collections
import functools
import hashlib
import io
import pathlib
import sys

from datetime import datetime

import sqlalchemy

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
        return pathlib.Path(self.identity)


class AccountLevel(collections.namedtuple("AccountLevel", ["account"])):
    level = StorageLevel.ACCOUNT

    @property
    def key_path(self):
        return pathlib.Path(encode_jid(self.account))


class PeerLevel(collections.namedtuple("PeerLevel", ["identity", "peer"])):
    level = StorageLevel.PEER

    @property
    def key_path(self):
        return pathlib.Path(self.identity) / encode_jid(self.peer)


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


class DatabaseFrontend(Frontend):
    def connect(self, type_, namespace, name):
        """
        Return a SQLAlchemy sessionmaker for a database.
        """
        path = (self._backend.type_base_path(type_) /
                StorageLevel.GLOBAL.value /
                namespace /
                "db" /
                name)


class _PerLevelMixin:
    def _get_path(self, type_, level_type, namespace, frontend_name, name):
        return (self._backend.type_base_paths(type_, True)[0] /
                StorageLevel.GLOBAL.value /
                namespace /
                frontend_name /
                level_type.value /
                name)


class FileLikeFrontend(metaclass=abc.ABCMeta):
    @abc.abstractmethod
    async def open(self, type_, level, namespace, name, mode, *,
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

    # @abc.abstractmethod
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

    def _get_engine(self, type_, level_type, namespace):
        path = self._get_path(type_, level_type, namespace)
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
        engine = self._get_engine(type_, level_type, namespace)
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

        with common.session_scope(sessionmaker) as session:
            session.merge(blob)

    def _load_blob(self, type_, level, namespace, name, query):
        sessionmaker = self._get_sessionmaker(
            type_,
            level.level,
            namespace)

        _, blob_type, *_ = self.LEVEL_INFO[level.level]

        with common.session_scope(sessionmaker) as session:
            return blob_type.get(session, level, name, query)

    async def store(self, type_, level, namespace, name, data):
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

    async def _load_in_executor(self, type_, level, namespace, name, query):
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            self._load_blob,
            type_, level, namespace, name,
            query,
        )

    async def load(self, type_, level, namespace, name):
        data, = await self._load_in_executor(
            type_, level, namespace, name,
            [
                common.SmallBlobMixin.data,
            ]
        )
        return data

    async def open(self, type_, level, namespace, name, mode, *,
                   encoding=None):
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


class _PerLevelKeyFileMixin:
    def _get_path(self, type_, level, namespace, name):
        return (self._backend.type_base_paths(type_, True)[0] /
                level.level.value /
                level.key_path /
                namespace /
                name)


class LargeBlobFrontend(_PerLevelKeyFileMixin, FileLikeFrontend, Frontend):
    async def open(self, type_, level, namespace, name, mode, **kwargs):
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
        path = self._get_path(
            type_,
            level,
            namespace,
            pathlib.Path("largeblobs") / name,
        )
        return path.stat()

    async def unlink(self, type_, level, namespace, name):
        path = self._get_path(
            type_,
            level,
            namespace,
            pathlib.Path("largeblobs") / name,
        )
        return path.unlink()


class AppendFrontend(_PerLevelKeyFileMixin, Frontend):
    def submit(self, type_, level, namespace, name, data, ts=None):
        now = ts or datetime.utcnow()
        with self._get_path(
                type_,
                level,
                namespace,
                pathlib.Path("append") /
                str(now.year) /
                "{}-{}".format(now.month, now.day) /
                name).open("ab") as f:
            f.write(data)


class XMLFrontend(_PerLevelMixin):
    def register(self, type_, level_type, xso_type):
        pass

    def get(self, type_, level, xso_type):
        pass

    def put(self, type_, level, xso):
        pass
