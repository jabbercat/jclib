import unittest

import mlxc.client
import mlxc.roster

from mlxc.testutils import (
    ClientMock
)


class TestClientMock(unittest.TestCase):
    def setUp(self):
        self.mock = ClientMock()

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

    def tearDown(self):
        del self.mock
