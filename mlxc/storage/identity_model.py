import sqlalchemy

from sqlalchemy import (
    Column,
)
from sqlalchemy.ext.declarative import declarative_base

import aioxmpp.xso

from .common import UUID, SmallBlobMixin
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

    @classmethod
    def from_level_descriptor(cls, level):
        instance = cls()
        instance.identity = level.identity
        return instance

    @classmethod
    def filter_by(cls, query, level, name):
        return query.filter(
            cls.identity == level.identity,
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
    TAG = mlxc_namespaces.xml_storage_identity, "identity"

    uid = aioxmpp.xso.Attr(
        "uid",
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
        return obj.uid, obj.data

    def format(self, t):
        uid, data = t
        obj = XMLStorageItem()
        obj.uid = uid
        obj.data.update(data)
        return obj


class XMLStorage(aioxmpp.xso.XSO):
    TAG = mlxc_namespaces.xml_storage_identity, "identities"

    items = aioxmpp.xso.ChildValueMap(
        type_=XMLStorageItemType()
    )
