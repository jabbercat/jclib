import unittest
import unittest.mock
import uuid

import aioxmpp

import sqlalchemy.sql

import mlxc.storage.common
import mlxc.storage.frontends
import mlxc.storage.peer_model as peer_model

from mlxc.storage.common import session_scope

from mlxc.testutils import (
    inmemory_database
)


class TestSmallBlob(unittest.TestCase):
    def setUp(self):
        self.identity = uuid.uuid4()
        self.peer = aioxmpp.JID.fromstr("romeo@montague.lit")
        self.db = inmemory_database(peer_model.Base)

    def test_from_level_descriptor(self):
        descriptor = unittest.mock.Mock(["identity", "peer"])
        blob = peer_model.SmallBlob.from_level_descriptor(descriptor)
        self.assertIsInstance(blob, peer_model.SmallBlob)
        self.assertEqual(blob.identity, descriptor.identity)
        self.assertEqual(blob.peer, descriptor.peer)

    def test_get_finds_by_primary_key(self):
        descriptor = mlxc.storage.frontends.PeerLevel(
            self.identity,
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
        descriptor = mlxc.storage.frontends.PeerLevel(
            self.identity,
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
                    mlxc.storage.common.SmallBlobMixin.accessed,
                    sqlalchemy.sql.func.length(
                        mlxc.storage.common.SmallBlobMixin.data
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
        descriptor = mlxc.storage.frontends.PeerLevel(
            self.identity,
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
                    mlxc.storage.frontends.PeerLevel(
                        self.identity,
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
