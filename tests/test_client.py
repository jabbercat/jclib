import contextlib
import unittest

import aioxmpp

import jclib.client as client
import jclib.identity
import jclib.instrumentable_list

from aioxmpp.testutils import (
    make_connected_client,
    make_listener,
)


TEST_JID = aioxmpp.JID.fromstr("romeo@montague.lit")


class TestRosterGroups(unittest.TestCase):
    def setUp(self):
        self.cc = make_connected_client()
        self.roster_client = aioxmpp.RosterClient(self.cc, dependencies={
            aioxmpp.dispatcher.SimplePresenceDispatcher: aioxmpp.dispatcher.SimplePresenceDispatcher(self.cc)
        })
        self.s = client.RosterGroups(self.cc, dependencies={
            aioxmpp.RosterClient: self.roster_client,
        })

    def test_is_service(self):
        self.assertTrue(issubclass(client.RosterGroups,
                                   aioxmpp.service.Service))

    def test_depends_on_RosterClient(self):
        self.assertIn(aioxmpp.RosterClient, client.RosterGroups.ORDER_AFTER)

    def test_listens_to_on_group_added(self):
        self.assertTrue(
            aioxmpp.service.is_depsignal_handler(
                aioxmpp.RosterClient,
                "on_group_added",
                client.RosterGroups.handle_group_added,
            )
        )

    def test_listens_to_on_group_removed(self):
        self.assertTrue(
            aioxmpp.service.is_depsignal_handler(
                aioxmpp.RosterClient,
                "on_group_removed",
                client.RosterGroups.handle_group_removed,
            )
        )

    def test_init(self):
        self.assertCountEqual(
            self.s.groups,
            [],
        )
        self.assertIsInstance(
            self.s.groups,
            jclib.instrumentable_list.ModelList
        )

    def test_handle_group_added_adds_group(self):
        self.s.handle_group_added("foo")
        self.assertCountEqual(
            self.s.groups,
            ["foo"]
        )

        self.s.handle_group_added("bar")
        self.assertCountEqual(
            self.s.groups,
            ["foo", "bar"]
        )

    def test_handle_group_removed_removes_group(self):
        self.s.handle_group_added("foo")
        self.s.handle_group_added("bar")
        self.s.handle_group_removed("foo")
        self.assertCountEqual(
            self.s.groups,
            ["bar"]
        )


class TestClient(unittest.TestCase):
    def setUp(self):
        self.accounts = jclib.identity.Accounts()
        self.acc = self.accounts.new_account(TEST_JID, None)
        self.accounts.set_account_enabled(self.acc, False)
        self.keyring = unittest.mock.Mock(["priority"])
        self.keyring.priority = 1
        self.c = client.Client(self.accounts, use_keyring=self.keyring)
        self.listener = make_listener(self.c)

    def test_no_client_for_disabled_account(self):
        with self.assertRaises(KeyError):
            self.c.client_by_account(self.acc)

    def test_create_client_for_account(self):
        with contextlib.ExitStack() as stack:
            PresenceManagedClient = stack.enter_context(
                unittest.mock.patch("aioxmpp.PresenceManagedClient")
            )

            self.accounts.set_account_enabled(self.acc, True)

        PresenceManagedClient.assert_called_once_with(
            self.acc.jid,
            unittest.mock.ANY,
        )

        self.assertIn(
            unittest.mock.call(aioxmpp.DiscoServer),
            PresenceManagedClient().summon.mock_calls,
        )

        self.assertIn(
            unittest.mock.call(aioxmpp.MUCClient),
            PresenceManagedClient().summon.mock_calls,
        )

        self.assertIn(
            unittest.mock.call(aioxmpp.AdHocClient),
            PresenceManagedClient().summon.mock_calls,
        )

        self.assertIn(
            unittest.mock.call(aioxmpp.PresenceClient),
            PresenceManagedClient().summon.mock_calls,
        )

        self.assertIn(
            unittest.mock.call(aioxmpp.RosterClient),
            PresenceManagedClient().summon.mock_calls,
        )

        self.assertIn(
            unittest.mock.call(aioxmpp.im.p2p.Service),
            PresenceManagedClient().summon.mock_calls,
        )

        self.listener.on_client_prepare.assert_called_once_with(
            self.acc, PresenceManagedClient()
        )
