import unittest
import unittest.mock

import sqlalchemy.sql

import aioxmpp

import mlxc.storage.frontends
import mlxc.storage.account_model as account_model

from mlxc.storage.common import session_scope

from mlxc.testutils import (
    inmemory_database
)


class TestSmallBlob(unittest.TestCase):
    def setUp(self):
        self.account = aioxmpp.JID.fromstr("romeo@montague.lit")
        self.db = inmemory_database(account_model.Base)

    def test_from_level_descriptor(self):
        descriptor = unittest.mock.Mock(["account"])
        blob = account_model.SmallBlob.from_level_descriptor(descriptor)
        self.assertIsInstance(blob, account_model.SmallBlob)
        self.assertEqual(blob.account, descriptor.account)

    def test_get_finds_by_primary_key(self):
        descriptor = mlxc.storage.frontends.AccountLevel(
            self.account,
        )

        with session_scope(self.db) as session:
            blob = account_model.SmallBlob.from_level_descriptor(descriptor)
            blob.data = b"foo"
            session.add(blob)
            session.commit()

            otherblob = account_model.SmallBlob.get(session, descriptor)
            self.assertEqual(otherblob.data, b"foo")

    def test_get_allows_specification_of_query(self):
        descriptor = mlxc.storage.frontends.AccountLevel(
            self.account,
        )

        with session_scope(self.db) as session:
            blob = account_model.SmallBlob.from_level_descriptor(descriptor)
            blob.data = b"foo"
            session.add(blob)
            session.commit()

            result = account_model.SmallBlob.get(
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
        descriptor = mlxc.storage.frontends.AccountLevel(
            self.account,
        )

        with session_scope(self.db) as session:
            blob = account_model.SmallBlob.from_level_descriptor(descriptor)
            blob.data = b"foo"
            session.add(blob)
            session.commit()

            with self.assertRaises(KeyError):
                account_model.SmallBlob.get(
                    session,
                    mlxc.storage.frontends.AccountLevel(
                        aioxmpp.JID.fromstr("juliet@capulet.lit")
                    )
                )
