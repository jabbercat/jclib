import sqlalchemy

from sqlalchemy import (
    Column,
    LargeBinary,
)
from sqlalchemy.ext.declarative import declarative_base

from .common import UUID, JID, SmallBlobMixin


class Base(declarative_base()):
    __abstract__ = True
    __table_args__ = {}


class SmallBlob(SmallBlobMixin, Base):
    __tablename__ = "smallblobs"

    identity = Column(
        "identity",
        UUID(),
        primary_key=True
    )

    peer = Column(
        "peer",
        JID(),
        primary_key=True,
    )

    @classmethod
    def from_level_descriptor(cls, level):
        instance = cls()
        instance.identity = level.identity
        instance.peer = level.peer
        return instance

    @classmethod
    def get(cls, session, level, which=None):
        which = which or [cls]
        try:
            return session.query(*which).filter(
                cls.identity == level.identity,
                cls.peer == level.peer,
            ).one()
        except sqlalchemy.orm.exc.NoResultFound:
            raise KeyError(level) from None
