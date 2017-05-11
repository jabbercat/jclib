import sqlalchemy

from sqlalchemy import (
    Column,
)
from sqlalchemy.ext.declarative import declarative_base

import aioxmpp.xso

from .common import UUID, JID, SmallBlobMixin
from ..utils import mlxc_namespaces


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
    def filter_by(cls, query, level, name):
        return query.filter(
            cls.identity == level.identity,
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
    TAG = mlxc_namespaces.xml_storage_peer, "peer"

    jid = aioxmpp.xso.Attr(
        "jid",
        type_=aioxmpp.xso.JID(),
    )

    identity = aioxmpp.xso.Attr(
        "identity",
        type_=aioxmpp.xso.Base64Binary(),
    )

    data = aioxmpp.xso.ChildMap(
        [],
    )


class XMLStorageItemType(aioxmpp.xso.AbstractType):
    @classmethod
    def get_formatted_type(self):
        return XMLStorageItem

    def parse(self, obj):
        return (obj.identity, obj.jid), obj.data

    def format(self, t):
        (identity, jid), data = t
        obj = XMLStorageItem()
        obj.identity = identity
        obj.jid = jid
        obj.data.update(data)
        return obj


class XMLStorage(aioxmpp.xso.XSO):
    TAG = mlxc_namespaces.xml_storage_peer, "peers"

    items = aioxmpp.xso.ChildValueMap(
        type_=XMLStorageItemType()
    )

