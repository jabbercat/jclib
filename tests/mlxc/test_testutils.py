import unittest
import unittest.mock

import aioxmpp.callbacks

import mlxc.client
import mlxc.roster

from mlxc.testutils import (
    ClientMock
)


class TestClientMock(unittest.TestCase):
    def setUp(self):
        self.mock = ClientMock()

    def test_account_state(self):
        self.assertIsInstance(
            self.mock.account_state,
            unittest.mock.Mock
        )
        self.mock.account_state("foo")

    def test_accounts(self):
        self.assertIsInstance(
            self.mock.accounts,
            mlxc.client.AccountManager
        )

    def test_roster(self):
        self.assertIsInstance(
            self.mock.roster,
            mlxc.roster.Tree
        )

    def test_on_account_enabling(self):
        self.assertIsInstance(
            self.mock.on_account_enabling,
            aioxmpp.callbacks.AdHocSignal
        )

    def test_on_account_disabling(self):
        self.assertIsInstance(
            self.mock.on_account_disabling,
            aioxmpp.callbacks.AdHocSignal
        )

    def test_signals_are_adhoc_only(self):
        self.assertFalse(hasattr(ClientMock, "on_account_enabling"))
        self.assertFalse(hasattr(ClientMock, "on_account_disabling"))

    def tearDown(self):
        del self.mock
