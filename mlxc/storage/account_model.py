import sqlalchemy

from sqlalchemy import (
    Column,
    LargeBinary,
)
from sqlalchemy.ext.declarative import declarative_base

from .common import JID, SmallBlobMixin


class Base(declarative_base()):
    __abstract__ = True
    __table_args__ = {}


class SmallBlob(SmallBlobMixin, Base):
    __tablename__ = "smallblobs"

    account = Column(
        "account",
        JID(),
        primary_key=True,
    )

    @classmethod
    def from_level_descriptor(cls, level):
        instance = cls()
        instance.account = level.account
        return instance

    @classmethod
    def filter_by(cls, query, level, name):
        return query.filter(
            cls.account == level.account,
            cls.name == name,
        )

    @classmethod
    def get(cls, session, level, name, which=None):
        which = which or [cls]
        try:
            return cls.filter_by(session.query(*which), level, name).one()
        except sqlalchemy.orm.exc.NoResultFound:
            raise KeyError(level) from None
