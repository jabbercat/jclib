import unittest

import aioxmpp

import mlxc.client as client
import mlxc.instrumentable_list

from aioxmpp.testutils import (
    make_connected_client,
)


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
            mlxc.instrumentable_list.ModelList
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
