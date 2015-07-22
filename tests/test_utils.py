import unittest

import aioxmpp.utils as aioxmpp_utils

import mlxc.utils as utils


class Test_imports_from_aioxmpp(unittest.TestCase):
    def test_imports(self):
        self.assertIs(
            utils.namespaces,
            aioxmpp_utils.namespaces
        )


class Testmlxc_namespaces(unittest.TestCase):
    def test_account_namespace(self):
        self.assertEqual(
            "https://xmlns.zombofant.net/mlxc/core/account/1.0",
            utils.mlxc_namespaces.account
        )

    def test_roster_namespace(self):
        self.assertEqual(
            "https://xmlns.zombofant.net/mlxc/core/roster/1.0",
            utils.mlxc_namespaces.roster
        )
