import unittest
import unittest.mock
import uuid

import aioxmpp

import sqlalchemy.sql

import jclib.storage.common
import jclib.storage.frontends
import jclib.storage.peer_model as peer_model

from jclib.storage.common import session_scope

from jclib.testutils import (
    inmemory_database
)


other_jid = aioxmpp.JID.fromstr("foo@server.example")


class TestSmallBlob(unittest.TestCase):
    def setUp(self):
        self.account = aioxmpp.JID.fromstr("juliet@capulet.lit")
        self.peer = aioxmpp.JID.fromstr("romeo@montague.lit")
        self.db = inmemory_database(peer_model.Base)

    def test_from_level_descriptor(self):
        descriptor = unittest.mock.Mock(["account", "peer"])
        blob = peer_model.SmallBlob.from_level_descriptor(descriptor)
        self.assertIsInstance(blob, peer_model.SmallBlob)
        self.assertEqual(blob.account, descriptor.account)
        self.assertEqual(blob.peer, descriptor.peer)

    def test_filter_selects_by_primary_key(self):
        descriptor = jclib.storage.frontends.PeerLevel(
            self.account,
            self.peer,
        )

        with session_scope(self.db) as session:
            blob = peer_model.SmallBlob.from_level_descriptor(descriptor)
            blob.data = b"foo"
            blob.name = "name"
            session.add(blob)
            session.commit()

            q_base = session.query(peer_model.SmallBlob)
            q = peer_model.SmallBlob.filter_by(q_base, descriptor, "name")
            otherblob = q.one()
            self.assertEqual(otherblob.data, b"foo")

            q = peer_model.SmallBlob.filter_by(q_base, descriptor,
                                               "other name")
            with self.assertRaises(sqlalchemy.orm.exc.NoResultFound):
                q.one()

            q = peer_model.SmallBlob.filter_by(
                q_base,
                jclib.storage.frontends.PeerLevel(
                    self.account,
                    aioxmpp.JID.fromstr("juliet@capulet.lit"),
                ),
                "other name"
            )
            with self.assertRaises(sqlalchemy.orm.exc.NoResultFound):
                q.one()

            q = peer_model.SmallBlob.filter_by(
                q_base,
                jclib.storage.frontends.PeerLevel(
                    other_jid,
                    self.peer,
                ),
                "other name"
            )
            with self.assertRaises(sqlalchemy.orm.exc.NoResultFound):
                q.one()

    def test_get_finds_by_primary_key(self):
        descriptor = jclib.storage.frontends.PeerLevel(
            self.account,
            self.peer,
        )

        with session_scope(self.db) as session:
            blob = peer_model.SmallBlob.from_level_descriptor(descriptor)
            blob.data = b"foo"
            blob.name = "name"
            session.add(blob)
            session.commit()

            otherblob = peer_model.SmallBlob.get(session, descriptor, "name")
            self.assertEqual(otherblob.data, b"foo")

    def test_get_allows_specification_of_query(self):
        descriptor = jclib.storage.frontends.PeerLevel(
            self.account,
            self.peer,
        )

        with session_scope(self.db) as session:
            blob = peer_model.SmallBlob.from_level_descriptor(descriptor)
            blob.data = b"foo"
            blob.name = "name"
            session.add(blob)
            session.commit()

            result = peer_model.SmallBlob.get(
                session,
                descriptor,
                "name",
                [
                    jclib.storage.common.SmallBlobMixin.accessed,
                    sqlalchemy.sql.func.length(
                        jclib.storage.common.SmallBlobMixin.data
                    ),
                ]
            )

            self.assertSequenceEqual(
                result,
                [
                    blob.accessed,
                    3,
                ]
            )

    def test_get_raises_KeyError_if_not_found(self):
        descriptor = jclib.storage.frontends.PeerLevel(
            self.account,
            self.peer,
        )

        with session_scope(self.db) as session:
            blob = peer_model.SmallBlob.from_level_descriptor(descriptor)
            blob.data = b"foo"
            blob.name = "foo"
            session.add(blob)
            session.commit()

            with self.assertRaises(KeyError):
                peer_model.SmallBlob.get(
                    session,
                    jclib.storage.frontends.PeerLevel(
                        self.account,
                        aioxmpp.JID.fromstr("juliet@capulet.lit")
                    ),
                    "name",
                )

            with self.assertRaises(KeyError):
                peer_model.SmallBlob.get(
                    session,
                    descriptor,
                    "othername"
                )
