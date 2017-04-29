import unittest
import unittest.mock
import uuid

import sqlalchemy.sql

import mlxc.storage.frontends
import mlxc.storage.identity_model as identity_model

from mlxc.storage.common import session_scope

from mlxc.testutils import (
    inmemory_database
)


class TestSmallBlob(unittest.TestCase):
    def setUp(self):
        self.identity = uuid.uuid4()
        self.db = inmemory_database(identity_model.Base)

    def test_from_level_descriptor(self):
        descriptor = unittest.mock.Mock(["identity"])
        blob = identity_model.SmallBlob.from_level_descriptor(descriptor)
        self.assertIsInstance(blob, identity_model.SmallBlob)
        self.assertEqual(blob.identity, descriptor.identity)

    def test_get_finds_by_primary_key(self):
        descriptor = mlxc.storage.frontends.IdentityLevel(
            self.identity,
        )

        with session_scope(self.db) as session:
            blob = identity_model.SmallBlob.from_level_descriptor(descriptor)
            blob.data = b"foo"
            session.add(blob)
            session.commit()

            otherblob = identity_model.SmallBlob.get(session, descriptor)
            self.assertEqual(otherblob.data, b"foo")

    def test_get_allows_specification_of_query(self):
        descriptor = mlxc.storage.frontends.IdentityLevel(
            self.identity,
        )

        with session_scope(self.db) as session:
            blob = identity_model.SmallBlob.from_level_descriptor(descriptor)
            blob.data = b"foo"
            session.add(blob)
            session.commit()

            result = identity_model.SmallBlob.get(
                session,
                descriptor,
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
        descriptor = mlxc.storage.frontends.IdentityLevel(
            self.identity,
        )

        with session_scope(self.db) as session:
            blob = identity_model.SmallBlob.from_level_descriptor(descriptor)
            blob.data = b"foo"
            session.add(blob)
            session.commit()

            with self.assertRaises(KeyError):
                identity_model.SmallBlob.get(
                    session,
                    mlxc.storage.frontends.IdentityLevel(
                        uuid.uuid4(),
                    )
                )
