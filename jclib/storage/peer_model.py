import sqlalchemy

from sqlalchemy import (
    Column,
)
from sqlalchemy.ext.declarative import declarative_base

import aioxmpp.xso

from .common import UUID, JID, SmallBlobMixin
from ..utils import jabbercat_ns


class Base(declarative_base()):
    __abstract__ = True
    __table_args__ = {}


class SmallBlob(SmallBlobMixin, Base):
    __tablename__ = "smallblobs"

    account = Column(
        "account",
        JID(),
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
        instance.account = level.account
        instance.peer = level.peer
        return instance

    @classmethod
    def filter_by(cls, query, level, name):
        return query.filter(
            cls.account == level.account,
            cls.peer == level.peer,
            cls.name == name,
        )

    @classmethod
    def get(cls, session, level, name, which=None):
        which = which or [cls]
        try:
            return cls.filter_by(session.query(*which), level, name).one()
        except sqlalchemy.orm.exc.NoResultFound:
            raise KeyError(level) from None


class XMLStorageItem(aioxmpp.xso.XSO):
    TAG = jabbercat_ns.xml_storage_peer, "peer"

    peer = aioxmpp.xso.Attr(
        "peer",
        type_=aioxmpp.xso.JID(),
    )

    account = aioxmpp.xso.Attr(
        "account",
        type_=aioxmpp.xso.JID(),
    )

    data = aioxmpp.xso.ChildMap(
        [],
    )


class XMLStorageItemType(aioxmpp.xso.AbstractElementType):
    @classmethod
    def get_xso_types(self):
        return [XMLStorageItem]

    def unpack(self, obj):
        return (obj.account, obj.peer), obj.data

    def pack(self, t):
        (account, peer), data = t
        obj = XMLStorageItem()
        obj.account = account
        obj.peer = peer
        obj.data.update(data)
        return obj


class XMLStorage(aioxmpp.xso.XSO):
    TAG = jabbercat_ns.xml_storage_peer, "peers"

    items = aioxmpp.xso.ChildValueMap(
        type_=XMLStorageItemType()
    )

