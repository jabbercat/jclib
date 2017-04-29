import contextlib
import enum
import uuid

from datetime import datetime

import sqlalchemy.types
import sqlalchemy.dialects.postgresql
from sqlalchemy import (
    Column,
    DateTime,
    LargeBinary,
    Unicode,
)

import aioxmpp


class StorageType(enum.Enum):
    CACHE = 'cache'
    DATA = 'data'
    CONFIG = 'config'


class StorageLevel(enum.Enum):
    GLOBAL = 'glbl'
    IDENTITY = 'idty'
    ACCOUNT = 'acct'
    PEER = 'peer'


class DataModel(enum.Enum):
    DATABASE = 'db'
    APPEND = 'append'
    XML = 'xml'
    SMALL_BLOB = 'sblob'
    LARGE_BLOB = 'lblob'


class TimestampsMixin:
    created = Column(
        "st_birthtime",
        DateTime(),
        default=datetime.utcnow,
    )

    modified = Column(
        "st_mtime",
        DateTime(),
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    accessed = Column(
        "st_atime",
        DateTime(),
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    def touch(self, now=None):
        self.accessed = now or datetime.utcnow()


class SmallBlobMixin(TimestampsMixin):
    data = Column(
        "data",
        LargeBinary()
    )

    name = Column(
        "name",
        Unicode(255),
        primary_key=True,
    )


class UUID(sqlalchemy.types.TypeDecorator):
    """Platform-independent GUID type.

    Uses Postgresql's UUID type, otherwise uses
    BINARY(16), storing as stringified hex values.

    Copied from
    http://docs.sqlalchemy.org/en/latest/core/custom_types.html#backend-agnostic-guid-type
    """
    impl = sqlalchemy.types.BINARY

    def load_dialect_impl(self, dialect):
        if dialect.name == 'postgresql':
            return dialect.type_descriptor(
                sqlalchemy.dialects.postgresql.UUID()
            )
        else:
            return dialect.type_descriptor(
                sqlalchemy.types.BINARY(16)
            )

    def process_bind_param(self, value, dialect):
        if value is None:
            return value
        elif dialect.name == 'postgresql':
            return str(value)
        else:
            if not isinstance(value, uuid.UUID):
                return uuid.UUID(value).bytes
            else:
                return value.bytes

    def process_result_value(self, value, dialect):
        if value is None:
            return value
        elif dialect.name == 'postgresql':
            return uuid.UUID(value)
        else:
            return uuid.UUID(bytes=value)


class JID(sqlalchemy.types.TypeDecorator):
    impl = sqlalchemy.types.VARCHAR

    def load_dialect_impl(self, dialect):
        return sqlalchemy.types.VARCHAR(3071)

    def process_bind_param(self, value, dialect):
        if value is None:
            return value
        return str(value)

    def process_result_value(self, value, dialect):
        if value is None:
            return value
        return aioxmpp.JID.fromstr(value)


@contextlib.contextmanager
def session_scope(sessionmaker):
    """Provide a transactional scope around a series of operations."""
    session = sessionmaker()
    try:
        yield session
    except:
        session.rollback()
        raise
    else:
        session.commit()
    finally:
        session.close()
