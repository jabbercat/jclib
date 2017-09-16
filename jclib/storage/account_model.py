import sqlalchemy

from sqlalchemy import (
    Column,
)
from sqlalchemy.ext.declarative import declarative_base

import aioxmpp.xso

from .common import JID, SmallBlobMixin
from ..utils import mlxc_namespaces


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


class XMLStorageItem(aioxmpp.xso.XSO):
    TAG = mlxc_namespaces.xml_storage_account, "account"

    jid = aioxmpp.xso.Attr(
        "jid",
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
        return obj.jid, obj.data

    def pack(self, t):
        jid, data = t
        obj = XMLStorageItem()
        obj.jid = jid
        obj.data.update(data)
        return obj


class XMLStorage(aioxmpp.xso.XSO):
    TAG = mlxc_namespaces.xml_storage_account, "accounts"

    items = aioxmpp.xso.ChildValueMap(
        type_=XMLStorageItemType()
    )
