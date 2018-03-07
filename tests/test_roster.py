import contextlib
import itertools
import unittest
import unittest.mock

import jclib.client
import jclib.identity
import jclib.roster as roster
import jclib.storage
import jclib.xso

import aioxmpp

from aioxmpp.testutils import (
    make_connected_client,
    make_listener,
    CoroutineMock,
    run_coroutine,
)


TEST_JID1 = aioxmpp.JID.fromstr("romeo@montague.lit")
TEST_JID2 = aioxmpp.JID.fromstr("juliet@capulet.lit")
TEST_JID3 = aioxmpp.JID.fromstr("alice@hub.sotecware.net")
TEST_JID4 = aioxmpp.JID.fromstr("bob@hub.sotecware.net")
TEST_JID5 = aioxmpp.JID.fromstr("carol@hub.sotecware.net")
TEST_JID_CHAT = aioxmpp.JID.fromstr("chat@switch.hub.sotecware.net")


class TestContactRosterItem(unittest.TestCase):
    def setUp(self):
        self.upstream_item = unittest.mock.Mock([
            "jid",
            "name",
            "groups",
            "subscription",
            "approved",
            "ask",
        ])
        self.upstream_item.groups = [
            unittest.mock.sentinel.g1,
            unittest.mock.sentinel.g2,
        ]

    def test_wrap(self):
        result = roster.ContactRosterItem.wrap(
            unittest.mock.sentinel.account,
            unittest.mock.sentinel.owner,
            self.upstream_item,
        )

        self.assertEqual(result.account, unittest.mock.sentinel.account)
        self.assertEqual(result.owner, unittest.mock.sentinel.owner)
        self.assertEqual(result.address, self.upstream_item.jid)
        self.assertEqual(result.label, self.upstream_item.name)
        self.assertCountEqual(result.tags, self.upstream_item.groups)
        self.assertEqual(result.subscription, self.upstream_item.subscription)
        self.assertEqual(result.approved, self.upstream_item.approved)
        self.assertEqual(result.ask, self.upstream_item.ask)

    def test_wrap_is_resistant_against_modification_of_source(self):
        result = roster.ContactRosterItem.wrap(
            unittest.mock.sentinel.account,
            unittest.mock.sentinel.owner,
            self.upstream_item,
        )

        self.assertEqual(result.account, unittest.mock.sentinel.account)
        self.assertEqual(result.owner, unittest.mock.sentinel.owner)
        self.assertEqual(result.address, self.upstream_item.jid)
        self.assertEqual(result.label, self.upstream_item.name)
        self.assertCountEqual(result.tags, self.upstream_item.groups)
        self.assertEqual(result.subscription, self.upstream_item.subscription)
        self.assertEqual(result.approved, self.upstream_item.approved)
        self.assertEqual(result.ask, self.upstream_item.ask)

        self.upstream_item.groups.remove(unittest.mock.sentinel.g1)

        self.assertCountEqual(
            result.tags,
            {
                unittest.mock.sentinel.g1,
                unittest.mock.sentinel.g2,
            }
        )

    def test_from_xso(self):
        obj = jclib.xso.RosterContact()
        obj.address = TEST_JID2
        obj.label = "Juliet Capulet"
        obj.tags.update(["foo", "bar"])
        obj.approved = True
        obj.ask = True
        obj.subscription = "foo"

        item = roster.ContactRosterItem.from_xso(
            unittest.mock.sentinel.account,
            unittest.mock.sentinel.owner,
            obj,
        )

        self.assertIsInstance(item, roster.ContactRosterItem)

        self.assertEqual(item.account, unittest.mock.sentinel.account)
        self.assertEqual(item.owner, unittest.mock.sentinel.owner)
        self.assertEqual(item.address, TEST_JID2)
        self.assertEqual(item.label, "Juliet Capulet")
        self.assertCountEqual(item.tags, ["foo", "bar"])
        self.assertEqual(item.ask, True)
        self.assertEqual(item.approved, True)
        self.assertEqual(item.subscription, "foo")

    def test_to_xso(self):
        item = roster.ContactRosterItem(
            unittest.mock.sentinel.account,
            unittest.mock.sentinel.owner,
            TEST_JID1,
            label="Romeo Montague",
            tags=["foo", "bar"],
            subscription="both",
            ask=True,
            approved=True,
        )

        obj = item.to_xso()

        self.assertEqual(obj.address, TEST_JID1)
        self.assertEqual(obj.label, "Romeo Montague")
        self.assertSetEqual(obj.tags, {"foo", "bar"})
        self.assertEqual(obj.subscription, "both")
        self.assertTrue(obj.ask)
        self.assertTrue(obj.approved)

    def test_to_xso_with_empty_label(self):
        item = roster.ContactRosterItem(
            unittest.mock.sentinel.account,
            unittest.mock.sentinel.owner,
            TEST_JID1,
            tags=["foo", "bar"],
            subscription="both",
            ask=True,
            approved=True,
        )

        obj = item.to_xso()

        self.assertIsInstance(obj, jclib.xso.RosterContact)
        self.assertEqual(obj.address, TEST_JID1)
        self.assertIsNone(obj.label)
        self.assertSetEqual(obj.tags, {"foo", "bar"})
        self.assertEqual(obj.subscription, "both")
        self.assertTrue(obj.ask)
        self.assertTrue(obj.approved)

    def test_update_updates_contents(self):
        item = roster.ContactRosterItem(
            unittest.mock.sentinel.account,
            unittest.mock.sentinel.owner,
            TEST_JID1,
        )
        item.update(self.upstream_item)

        self.assertEqual(item.account, unittest.mock.sentinel.account)
        self.assertEqual(item.owner, unittest.mock.sentinel.owner)

        self.assertEqual(item.label, self.upstream_item.name)
        self.assertCountEqual(item.tags, self.upstream_item.groups)
        self.assertEqual(item.subscription, self.upstream_item.subscription)
        self.assertEqual(item.approved, self.upstream_item.approved)
        self.assertEqual(item.ask, self.upstream_item.ask)

    def test_create_conversation_uses_p2p_service(self):
        client = unittest.mock.Mock()
        item = roster.ContactRosterItem(
            unittest.mock.sentinel.account,
            unittest.mock.sentinel.owner,
            TEST_JID1,
        )

        result = item.create_conversation(client)

        client.summon.assert_called_once_with(
            aioxmpp.im.p2p.Service,
        )

        client.summon().get_conversation.assert_called_once_with(
            item.address,
        )

        self.assertEqual(result, client.summon().get_conversation())

    def test_set_label_forwards_to_owner(self):
        owner = unittest.mock.Mock()
        owner.set_label = CoroutineMock()
        owner.set_label.return_value = unittest.mock.sentinel.result

        item = roster.ContactRosterItem(
            unittest.mock.sentinel.account,
            owner,
            unittest.mock.sentinel.address,
        )

        result = run_coroutine(
            item.set_label(unittest.mock.sentinel.new_label)
        )

        owner.set_label.assert_called_once_with(
            item,
            unittest.mock.sentinel.new_label,
        )

        self.assertEqual(
            result,
            unittest.mock.sentinel.result,
        )

    def test_update_tags_forwards_to_owner(self):
        owner = unittest.mock.Mock()
        owner.update_tags = CoroutineMock()
        owner.update_tags.return_value = unittest.mock.sentinel.result

        item = roster.ContactRosterItem(
            unittest.mock.sentinel.account,
            owner,
            unittest.mock.sentinel.address,
        )

        result = run_coroutine(item.update_tags(
            unittest.mock.sentinel.add_tags,
            unittest.mock.sentinel.remove_tags,
        ))

        owner.update_tags.assert_called_once_with(
            item,
            unittest.mock.sentinel.add_tags,
            unittest.mock.sentinel.remove_tags,
        )

        self.assertEqual(
            result,
            unittest.mock.sentinel.result,
        )

    def test_can_manage_tags(self):
        item = roster.ContactRosterItem(
            unittest.mock.sentinel.account,
            unittest.mock.sentinel.owner,
            unittest.mock.sentinel.address,
        )

        self.assertTrue(item.can_manage_tags)

    def test_can_set_label(self):
        item = roster.ContactRosterItem(
            unittest.mock.sentinel.account,
            unittest.mock.sentinel.owner,
            unittest.mock.sentinel.address,
        )

        self.assertTrue(item.can_set_label)


class TestMUCRosterItem(unittest.TestCase):
    def test_init_bare(self):
        item = roster.MUCRosterItem(
            unittest.mock.sentinel.account,
            unittest.mock.sentinel.owner,
            TEST_JID_CHAT,
        )

        self.assertEqual(item.account, unittest.mock.sentinel.account)
        self.assertEqual(item.owner, unittest.mock.sentinel.owner)
        self.assertIsNone(item.subject)
        self.assertFalse(item.autojoin)
        self.assertIsNone(item.nick)
        self.assertIsNone(item.password)
        self.assertEqual(item.label, str(TEST_JID_CHAT))
        self.assertCountEqual(item.tags, [])

    def test_init_label(self):
        item = roster.MUCRosterItem(
            unittest.mock.sentinel.account,
            unittest.mock.sentinel.owner,
            TEST_JID_CHAT,
            label="test",
        )

        self.assertEqual(item.account, unittest.mock.sentinel.account)
        self.assertEqual(item.owner, unittest.mock.sentinel.owner)
        self.assertIsNone(item.subject)
        self.assertFalse(item.autojoin)
        self.assertIsNone(item.nick)
        self.assertIsNone(item.password)
        self.assertEqual(item.label, "test")
        self.assertCountEqual(item.tags, [])

    def test_wrap(self):
        obj = aioxmpp.bookmarks.xso.Conference(
            "some name",
            TEST_JID_CHAT,
            autojoin=True,
            nick="fnord",
            password="no password",
        )

        item = roster.MUCRosterItem.wrap(
            unittest.mock.sentinel.account,
            unittest.mock.sentinel.owner,
            obj,
        )

        self.assertIsInstance(item, roster.MUCRosterItem)
        self.assertEqual(item.account, unittest.mock.sentinel.account)
        self.assertEqual(item.owner, unittest.mock.sentinel.owner)
        self.assertEqual(item.label, "some name")
        self.assertEqual(item.address, TEST_JID_CHAT)
        self.assertEqual(item.nick, "fnord")
        self.assertEqual(item.password, "no password")
        self.assertTrue(item.autojoin)

    def test_create_conversation_uses_p2p_service(self):
        client = unittest.mock.Mock()
        client.summon().join.return_value = \
            unittest.mock.sentinel.room, unittest.mock.sentinel.fut
        client.summon.reset_mock()
        item = roster.MUCRosterItem(
            unittest.mock.sentinel.account,
            unittest.mock.sentinel.owner,
            TEST_JID1,
            nick="foo",
        )

        result = item.create_conversation(client)

        client.summon.assert_called_once_with(
            aioxmpp.MUCClient,
        )

        client.summon().join.assert_called_once_with(
            item.address,
            "foo",
            password=None,
        )

        self.assertEqual(result, unittest.mock.sentinel.room)

    def test_create_conversation_invents_nickname_if_None(self):
        account = unittest.mock.Mock()
        client = unittest.mock.Mock()
        client.summon().join.return_value = \
            unittest.mock.sentinel.room, unittest.mock.sentinel.fut
        client.summon.reset_mock()
        item = roster.MUCRosterItem(
            account,
            unittest.mock.sentinel.owner,
            TEST_JID1,
            nick=None,
        )

        result = item.create_conversation(client)

        client.summon.assert_called_once_with(
            aioxmpp.MUCClient,
        )

        client.summon().join.assert_called_once_with(
            item.address,
            account.jid.localpart,
            password=None,
        )

        self.assertEqual(result, unittest.mock.sentinel.room)

    def test_set_label_forwards_to_owner(self):
        owner = unittest.mock.Mock()
        owner.set_label = CoroutineMock()
        owner.set_label.return_value = unittest.mock.sentinel.result

        item = roster.MUCRosterItem(
            unittest.mock.sentinel.account,
            owner,
            unittest.mock.sentinel.address,
        )

        result = run_coroutine(
            item.set_label(unittest.mock.sentinel.new_label)
        )

        owner.set_label.assert_called_once_with(
            item,
            unittest.mock.sentinel.new_label,
        )

        self.assertEqual(
            result,
            unittest.mock.sentinel.result,
        )

    def test_update_tags_forwards_to_owner(self):
        owner = unittest.mock.Mock()
        owner.update_tags = CoroutineMock()
        owner.update_tags.return_value = unittest.mock.sentinel.result

        item = roster.MUCRosterItem(
            unittest.mock.sentinel.account,
            owner,
            unittest.mock.sentinel.address,
        )

        result = run_coroutine(item.update_tags(
            unittest.mock.sentinel.add_tags,
            unittest.mock.sentinel.remove_tags,
        ))

        owner.update_tags.assert_called_once_with(
            item,
            unittest.mock.sentinel.add_tags,
            unittest.mock.sentinel.remove_tags,
        )

        self.assertEqual(
            result,
            unittest.mock.sentinel.result,
        )

    def test_can_manage_tags(self):
        item = roster.MUCRosterItem(
            unittest.mock.sentinel.account,
            unittest.mock.sentinel.owner,
            unittest.mock.sentinel.address,
        )

        self.assertFalse(item.can_manage_tags)

    def test_can_set_label(self):
        item = roster.MUCRosterItem(
            unittest.mock.sentinel.account,
            unittest.mock.sentinel.owner,
            unittest.mock.sentinel.address,
        )

        self.assertTrue(item.can_set_label)

    def test_to_bookmark(self):
        item = roster.MUCRosterItem(
            unittest.mock.sentinel.account,
            unittest.mock.sentinel.owner,
            unittest.mock.sentinel.address,
            label=unittest.mock.sentinel.label,
            nick=unittest.mock.sentinel.nick,
            autojoin=unittest.mock.sentinel.autojoin,
            password=unittest.mock.sentinel.password,
        )

        with contextlib.ExitStack() as stack:
            Conference = stack.enter_context(unittest.mock.patch(
                "aioxmpp.bookmarks.xso.Conference"
            ))

            obj = item.to_bookmark()

        Conference.assert_called_once_with(
            unittest.mock.sentinel.label,
            unittest.mock.sentinel.address,
            autojoin=unittest.mock.sentinel.autojoin,
            nick=unittest.mock.sentinel.nick,
            password=unittest.mock.sentinel.password,
        )

        self.assertEqual(obj, Conference())

    def test_update(self):
        item = roster.MUCRosterItem(
            unittest.mock.sentinel.account,
            unittest.mock.sentinel.owner,
            unittest.mock.sentinel.address,
            label=unittest.mock.sentinel.old_label,
            autojoin=unittest.mock.sentinel.old_autojoin,
            nick=unittest.mock.sentinel.old_nick,
            password=unittest.mock.sentinel.old_password,
        )

        new_obj = unittest.mock.Mock(["name", "jid", "autojoin", "nick",
                                      "password"])

        item.update(new_obj)

        self.assertEqual(
            item.label,
            new_obj.name,
        )

        self.assertEqual(
            item.autojoin,
            new_obj.autojoin,
        )

        self.assertEqual(
            item.password,
            new_obj.password,
        )

        self.assertEqual(
            item.nick,
            new_obj.nick,
        )


class Testcontacts_to_json(unittest.TestCase):
    def test_minimal(self):
        contacts = [
            roster.ContactRosterItem(
                unittest.mock.sentinel.account,
                unittest.mock.sentinel.owner,
                TEST_JID1,
            ),
        ]

        self.assertDictEqual(
            roster.contacts_to_json(
                contacts,
            ),
            {
                "ver": None,
                "items": {
                    "romeo@montague.lit": {
                        "subscription": "none",
                        "ask": False,
                    }
                }
            }
        )

    def test_with_groups_label_and_subscribed(self):
        contacts = [
            roster.ContactRosterItem(
                unittest.mock.sentinel.account,
                unittest.mock.sentinel.owner,
                TEST_JID1,
                label="Romeo Montague",
                subscription="both",
                tags=["Montague", "Shakespeare"],
            ),
        ]

        self.assertDictEqual(
            roster.contacts_to_json(
                contacts,
            ),
            {
                "ver": None,
                "items": {
                    "romeo@montague.lit": {
                        "name": "Romeo Montague",
                        "subscription": "both",
                        "groups": ["Montague", "Shakespeare"],
                        "ask": False,
                    }
                }
            }
        )

    def test_with_ask_and_approve(self):
        contacts = [
            roster.ContactRosterItem(
                unittest.mock.sentinel.account,
                unittest.mock.sentinel.owner,
                TEST_JID1,
                ask=True,
                approved=True,
            ),
        ]

        self.assertDictEqual(
            roster.contacts_to_json(
                contacts,
            ),
            {
                "ver": None,
                "items": {
                    "romeo@montague.lit": {
                        "subscription": "none",
                        "ask": True,
                        "approved": True,
                    }
                }
            }
        )

    def test_with_ver(self):
        contacts = [
            roster.ContactRosterItem(
                unittest.mock.sentinel.account,
                unittest.mock.sentinel.owner,
                TEST_JID1,
            ),
        ]

        self.assertDictEqual(
            roster.contacts_to_json(
                contacts,
                ver="foo",
            ),
            {
                "ver": "foo",
                "items": {
                    "romeo@montague.lit": {
                        "subscription": "none",
                        "ask": False,
                    }
                }
            }
        )

    def test_is_understood_by_roster(self):
        client = make_connected_client()
        aioxmpp_roster = aioxmpp.RosterClient(client, dependencies={
            aioxmpp.dispatcher.SimplePresenceDispatcher:
                aioxmpp.dispatcher.SimplePresenceDispatcher(client)
        })
        aioxmpp_roster.import_from_json(roster.contacts_to_json(
            [
                roster.ContactRosterItem(
                    unittest.mock.sentinel.account,
                    unittest.mock.sentinel.owner,
                    TEST_JID1,
                    ask=True,
                    approved=True,
                ),
                roster.ContactRosterItem(
                    unittest.mock.sentinel.account,
                    unittest.mock.sentinel.owner,
                    TEST_JID3,
                    label="Alice",
                    subscription="both",
                    tags=["Cryptographers"],
                ),
            ],
            ver="fnord",
        ))

        self.assertIn(TEST_JID1, aioxmpp_roster.items)
        item = aioxmpp_roster.items[TEST_JID1]
        self.assertEqual(
            item.ask,
            True,
        )
        self.assertEqual(
            item.approved,
            True,
        )
        self.assertIsNone(item.name)
        self.assertEqual(item.subscription, "none")
        self.assertCountEqual(item.groups, [])

        self.assertIn(TEST_JID3, aioxmpp_roster.items)
        item = aioxmpp_roster.items[TEST_JID3]
        self.assertEqual(item.ask, False)
        self.assertEqual(item.approved, False)
        self.assertEqual(item.subscription, "both")
        self.assertCountEqual(item.groups, ["Cryptographers"])
        self.assertEqual(item.name, "Alice")

        self.assertEqual(aioxmpp_roster.version, "fnord")


class TestContactRosterService(unittest.TestCase):
    def setUp(self):
        self.account = unittest.mock.Mock(["jid"])
        self.roster = unittest.mock.Mock(
            spec=aioxmpp.RosterClient,
        )
        self.roster.set_entry = CoroutineMock()
        self.roster.remove_entry = CoroutineMock()
        self.writeman = unittest.mock.Mock(spec=jclib.storage.WriteManager)
        self.rs = roster.ContactRosterService(self.account, self.writeman)
        self.listener = make_listener(self.rs)

    def _prep_client(self):
        client = make_connected_client()
        client.mock_services[aioxmpp.RosterClient] = self.roster
        return client

    def test_not_writable_by_default(self):
        self.assertFalse(self.rs.is_writable)

    def test_connects_weakly_to_write_manager(self):
        self.writeman.on_writeback.connect.assert_called_once_with(
            self.rs.save,
            self.writeman.on_writeback.WEAK
        )

    def test_prepare_client_summons_roster_and_connects_signals(self):
        client = self._prep_client()
        self.rs.prepare_client(client)

        self.roster.on_entry_added.connect.assert_called_once_with(
            self.rs._on_entry_added,
        )

        self.roster.on_entry_removed.connect.assert_called_once_with(
            self.rs._on_entry_removed,
        )

        self.roster.on_entry_name_changed.connect.assert_called_once_with(
            self.rs._on_entry_changed,
        )

        self.roster.on_entry_subscription_state_changed.connect\
            .assert_called_once_with(
                self.rs._on_entry_changed,
            )

        self.roster.on_entry_added_to_group.connect\
            .assert_called_once_with(
                self.rs._on_entry_changed,
            )

        self.roster.on_entry_removed_from_group.connect\
            .assert_called_once_with(
                self.rs._on_entry_changed,
            )

        self.roster.on_group_added.connect.assert_called_once_with(
            self.rs._on_tag_added,
        )

        self.roster.on_group_removed.connect.assert_called_once_with(
            self.rs._on_tag_removed,
        )

    def test_prepare_client_makes_service_writable(self):
        client = self._prep_client()
        self.rs.prepare_client(client)

        self.assertTrue(self.rs.is_writable)

    def test_shutdown_client_disconnects_signals(self):
        client = self._prep_client()
        self.rs.prepare_client(client)
        self.rs.shutdown_client(client)

        self.roster.on_entry_added.disconnect.assert_called_once_with(
            self.roster.on_entry_added.connect(),
        )

        self.roster.on_entry_removed.disconnect.assert_called_once_with(
            self.roster.on_entry_removed.connect(),
        )

        self.roster.on_entry_name_changed.disconnect.assert_called_once_with(
            self.roster.on_entry_name_changed.connect(),
        )

        self.roster.on_entry_subscription_state_changed.disconnect\
            .assert_called_once_with(
                self.roster.on_entry_subscription_state_changed.connect(),
            )

        self.roster.on_entry_added_to_group.disconnect\
            .assert_called_once_with(
                self.roster.on_entry_added_to_group.connect(),
            )

        self.roster.on_entry_removed_from_group.disconnect\
            .assert_called_once_with(
                self.roster.on_entry_removed_from_group.connect(),
            )

        self.roster.on_group_added.disconnect.assert_called_once_with(
            self.roster.on_group_added.connect(),
        )

        self.roster.on_group_removed.disconnect.assert_called_once_with(
            self.roster.on_group_removed.connect(),
        )

    def test_shutdown_makes_service_non_writable(self):
        client = self._prep_client()
        self.rs.prepare_client(client)
        self.rs.shutdown_client(client)

        self.assertFalse(self.rs.is_writable)

    def test__on_entry_added_adds_item(self):
        with contextlib.ExitStack() as stack:
            wrap = stack.enter_context(
                unittest.mock.patch.object(roster.ContactRosterItem, "wrap")
            )

            self.rs._on_entry_added(unittest.mock.sentinel.upstream_item)

        wrap.assert_called_once_with(
            self.account,
            self.rs,
            unittest.mock.sentinel.upstream_item,
        )

        self.assertEqual(len(self.rs), 1)
        self.assertEqual(self.rs[0], wrap())

        self.writeman.request_writeback.assert_called_once_with()

    def test__on_entry_removed_removes_item(self):
        upstream_item1_ver1 = unittest.mock.Mock()
        upstream_item1_ver1.jid = TEST_JID1
        upstream_item1_ver1.groups = []
        upstream_item1_ver2 = unittest.mock.Mock()
        upstream_item1_ver2.jid = TEST_JID1

        upstream_item2 = unittest.mock.Mock()
        upstream_item2.jid = TEST_JID2
        upstream_item2.groups = []

        self.rs._on_entry_added(upstream_item1_ver1)
        self.rs._on_entry_added(upstream_item2)

        self.writeman.request_writeback.reset_mock()
        self.rs._on_entry_removed(upstream_item1_ver2)
        self.writeman.request_writeback.assert_called_once_with()

        self.assertEqual(len(self.rs), 1)
        self.assertEqual(self.rs[0].address, TEST_JID2)

    def test__on_entry_changed_updates_item(self):
        upstream_item1_ver1 = unittest.mock.Mock()
        upstream_item1_ver1.jid = TEST_JID1
        upstream_item1_ver1.groups = []

        upstream_item1_ver2 = unittest.mock.Mock()
        upstream_item1_ver2.jid = TEST_JID1

        upstream_item2 = unittest.mock.Mock()
        upstream_item2.jid = TEST_JID2
        upstream_item2.groups = []

        self.rs._on_entry_added(upstream_item2)
        self.rs._on_entry_added(upstream_item1_ver1)

        self.writeman.request_writeback.reset_mock()
        with unittest.mock.patch.object(self.rs[1], "update") as update:
            self.rs._on_entry_changed(upstream_item1_ver2)

        update.assert_called_once_with(upstream_item1_ver2)

        self.assertEqual(len(self.rs), 2)

        self.writeman.request_writeback.assert_called_once_with()
        self.listener.data_changed.assert_called_once_with(
            None,
            1, 1,
            None, None,
            None,
        )

    def test__on_entry_changed_ignores_additional_argument(self):
        upstream_item1_ver1 = unittest.mock.Mock()
        upstream_item1_ver1.jid = TEST_JID1
        upstream_item1_ver1.groups = []

        upstream_item1_ver2 = unittest.mock.Mock()
        upstream_item1_ver2.jid = TEST_JID1

        upstream_item2 = unittest.mock.Mock()
        upstream_item2.jid = TEST_JID2
        upstream_item2.groups = []

        self.rs._on_entry_added(upstream_item2)
        self.rs._on_entry_added(upstream_item1_ver1)

        self.writeman.request_writeback.reset_mock()
        with unittest.mock.patch.object(self.rs[1], "update") as update:
            self.rs._on_entry_changed(upstream_item1_ver2, "fnord")

        update.assert_called_once_with(upstream_item1_ver2)

        self.assertEqual(len(self.rs), 2)

        self.writeman.request_writeback.assert_called_once_with()
        self.listener.data_changed.assert_called_once_with(
            None,
            1, 1,
            None, None,
            None,
        )

    def test__on_tag_added_emits_on_tag_added(self):
        self.rs._on_tag_added(unittest.mock.sentinel.tag)
        self.listener.on_tag_added.assert_called_once_with(
            unittest.mock.sentinel.tag,
        )

    def test__on_tag_removed_emits_on_tag_removed(self):
        self.rs._on_tag_removed(unittest.mock.sentinel.tag)
        self.listener.on_tag_removed.assert_called_once_with(
            unittest.mock.sentinel.tag,
        )

    def test_load(self):
        def generate_results():
            for i, address in enumerate([TEST_JID1, TEST_JID3, TEST_JID4]):
                yield roster.ContactRosterItem(
                    unittest.mock.sentinel.account,
                    unittest.mock.sentinel.owner,
                    address,
                    label="Contact no. {}".format(i)
                )

        with contextlib.ExitStack() as stack:
            get_all = stack.enter_context(unittest.mock.patch.object(
                jclib.storage.xml,
                "get_all",
            ))
            get_all.return_value = [
                getattr(unittest.mock.sentinel, "item{}".format(i))
                for i in range(3)
            ]

            from_xso = stack.enter_context(unittest.mock.patch.object(
                roster.ContactRosterItem,
                "from_xso",
            ))
            from_xso.side_effect = generate_results()

            self.rs.load()

        get_all.assert_called_once_with(
            jclib.storage.StorageType.CACHE,
            jclib.storage.AccountLevel(self.account.jid),
            jclib.xso.RosterContact,
        )

        self.assertCountEqual(
            from_xso.mock_calls,
            [
                unittest.mock.call(self.account, self.rs,
                                   unittest.mock.sentinel.item0),
                unittest.mock.call(self.account, self.rs,
                                   unittest.mock.sentinel.item1),
                unittest.mock.call(self.account, self.rs,
                                   unittest.mock.sentinel.item2),
            ]
        )

        self.assertEqual(len(self.rs), 3)

        self.assertCountEqual(
            [
                item.label for item in self.rs
            ],
            [
                "Contact no. {}".format(i)
                for i in range(3)
            ]
        )

    def test_load_emits_on_tag_added_events(self):
        items = [
            roster.ContactRosterItem(
                unittest.mock.sentinel.account,
                unittest.mock.sentinel.owner,
                TEST_JID1,
                tags=["foo", "bar"],
            ),
            roster.ContactRosterItem(
                unittest.mock.sentinel.account,
                unittest.mock.sentinel.owner,
                TEST_JID1,
                tags=["baz"],
            ),
            roster.ContactRosterItem(
                unittest.mock.sentinel.account,
                unittest.mock.sentinel.owner,
                TEST_JID1,
                tags=["fnord", "foo"],
            )
        ]

        def generate_results():
            yield from items

        with contextlib.ExitStack() as stack:
            get_all = stack.enter_context(unittest.mock.patch.object(
                jclib.storage.xml,
                "get_all",
            ))
            get_all.return_value = [
                getattr(unittest.mock.sentinel, "item{}".format(i))
                for i in range(3)
            ]

            from_xso = stack.enter_context(unittest.mock.patch.object(
                roster.ContactRosterItem,
                "from_xso",
            ))
            from_xso.side_effect = generate_results()

            self.rs.load()

        self.assertCountEqual(
            self.listener.on_tag_added.mock_calls,
            [
                unittest.mock.call("foo"),
                unittest.mock.call("bar"),
                unittest.mock.call("baz"),
                unittest.mock.call("fnord"),
            ]
        )

    def test_load_raises_if_client_has_been_prepared(self):
        client = self._prep_client()
        self.rs.prepare_client(client)

        with self.assertRaisesRegex(
                RuntimeError,
                "load cannot be called after a client has been prepared"):
            self.rs.load()

    def test_load_raises_if_there_are_contacts(self):
        def generate_results():
            for i, address in enumerate([TEST_JID1, TEST_JID3, TEST_JID4]):
                yield roster.ContactRosterItem(
                    unittest.mock.sentinel.account,
                    unittest.mock.sentinel.owner,
                    address,
                    label="Contact no. {}".format(i)
                )

        with contextlib.ExitStack() as stack:
            get_all = stack.enter_context(unittest.mock.patch.object(
                jclib.storage.xml,
                "get_all",
            ))
            get_all.return_value = [
                getattr(unittest.mock.sentinel, "item{}".format(i))
                for i in range(3)
            ]

            from_xso = stack.enter_context(unittest.mock.patch.object(
                roster.ContactRosterItem,
                "from_xso",
            ))
            from_xso.side_effect = generate_results()

            self.rs.load()

            with self.assertRaisesRegex(
                    RuntimeError,
                    "load cannot be called when there are already contacts "
                    "loaded"):
                self.rs.load()

    def test_prepare_client_imports_loaded_data_into_roster(self):
        items = []

        def generate_results():
            for i, address in enumerate([TEST_JID1, TEST_JID3, TEST_JID4]):
                item = roster.ContactRosterItem(
                    unittest.mock.sentinel.account,
                    unittest.mock.sentinel.owner,
                    address,
                    label="Contact no. {}".format(i)
                )
                items.append(item)
                yield item

        with contextlib.ExitStack() as stack:
            get_all = stack.enter_context(unittest.mock.patch.object(
                jclib.storage.xml,
                "get_all",
            ))
            get_all.return_value = [
                getattr(unittest.mock.sentinel, "item{}".format(i))
                for i in range(3)
            ]

            from_xso = stack.enter_context(unittest.mock.patch.object(
                roster.ContactRosterItem,
                "from_xso",
            ))
            from_xso.side_effect = generate_results()

            self.rs.load()

            contacts_to_json = stack.enter_context(unittest.mock.patch(
                "jclib.roster.contacts_to_json"
            ))

            client = self._prep_client()
            self.rs.prepare_client(client)

        contacts_to_json.assert_called_once_with(
            self.rs
        )

        self.roster.import_from_json.assert_called_once_with(
            contacts_to_json()
        )

    def test_loaded_data_gets_updated(self):
        items = []

        def generate_results():
            for i, address in enumerate([TEST_JID1, TEST_JID3, TEST_JID4]):
                item = roster.ContactRosterItem(
                    unittest.mock.sentinel.account,
                    unittest.mock.sentinel.owner,
                    address,
                    label="Contact no. {}".format(i)
                )
                items.append(item)
                yield item

        with contextlib.ExitStack() as stack:
            get_all = stack.enter_context(unittest.mock.patch.object(
                jclib.storage.xml,
                "get_all",
            ))
            get_all.return_value = [
                getattr(unittest.mock.sentinel, "item{}".format(i))
                for i in range(3)
            ]

            from_xso = stack.enter_context(unittest.mock.patch.object(
                roster.ContactRosterItem,
                "from_xso",
            ))
            from_xso.side_effect = generate_results()

            self.rs.load()

        with contextlib.ExitStack() as stack:
            item = unittest.mock.Mock(spec=aioxmpp.roster.Item)
            item.jid = TEST_JID3

            update = stack.enter_context(unittest.mock.patch.object(
                items[1],
                "update",
            ))

            self.rs._on_entry_changed(item)

        update.assert_called_once_with(item)

    def test_save(self):
        item_base = unittest.mock.Mock()

        def generate_wrapped():
            for i in itertools.count():
                yield getattr(unittest.mock.sentinel, "xso{}".format(i))

        def generate_items():
            generator = generate_wrapped()
            for i, address in enumerate([TEST_JID1, TEST_JID3, TEST_JID4]):
                m = getattr(item_base, "item{}".format(i))
                m.address = address
                m.to_xso.side_effect = generator
                yield m

        # populate roster service

        with contextlib.ExitStack() as stack:
            wrap = stack.enter_context(unittest.mock.patch.object(
                roster.ContactRosterItem,
                "wrap",
            ))
            wrap.side_effect = generate_items()

            self.rs._on_entry_added(unittest.mock.sentinel.upstream_item1)
            self.rs._on_entry_added(unittest.mock.sentinel.upstream_item2)
            self.rs._on_entry_added(unittest.mock.sentinel.upstream_item3)

        self.assertEqual(len(self.rs), 3)

        with contextlib.ExitStack() as stack:
            put = stack.enter_context(unittest.mock.patch.object(
                jclib.storage.xml,
                "put",
            ))

            self.rs.save()

        put.assert_called_once_with(
            jclib.storage.StorageType.CACHE,
            jclib.storage.AccountLevel(self.account.jid),
            [
                unittest.mock.sentinel.xso0,
                unittest.mock.sentinel.xso1,
                unittest.mock.sentinel.xso2,
            ]
        )

    def test_subsequent_save_calls_do_not_call_put(self):
        item_base = unittest.mock.Mock()

        def generate_wrapped():
            for i in itertools.count():
                yield getattr(unittest.mock.sentinel, "xso{}".format(i))

        def generate_items():
            generator = generate_wrapped()
            for i, address in enumerate([TEST_JID1, TEST_JID3, TEST_JID4]):
                m = getattr(item_base, "item{}".format(i))
                m.address = address
                m.to_xso.side_effect = generator
                yield m

        # populate roster service

        with contextlib.ExitStack() as stack:
            wrap = stack.enter_context(unittest.mock.patch.object(
                roster.ContactRosterItem,
                "wrap",
            ))
            wrap.side_effect = generate_items()

            self.rs._on_entry_added(unittest.mock.sentinel.upstream_item1)
            self.rs._on_entry_added(unittest.mock.sentinel.upstream_item2)
            self.rs._on_entry_added(unittest.mock.sentinel.upstream_item3)

        self.assertEqual(len(self.rs), 3)

        with contextlib.ExitStack() as stack:
            put = stack.enter_context(unittest.mock.patch.object(
                jclib.storage.xml,
                "put",
            ))

            self.rs.save()

            put.reset_mock()

            self.rs.save()

            put.assert_not_called()

    def test_save_calls_after_modification_call_put_again(self):
        item_base = unittest.mock.Mock()

        def generate_wrapped():
            for i in itertools.count():
                yield getattr(unittest.mock.sentinel, "xso{}".format(i))

        def generate_items():
            generator = generate_wrapped()
            for i, address in enumerate([TEST_JID1, TEST_JID3, TEST_JID4]):
                m = getattr(item_base, "item{}".format(i))
                m.address = address
                m.to_xso.side_effect = generator
                yield m

        # populate roster service

        with contextlib.ExitStack() as stack:
            wrap = stack.enter_context(unittest.mock.patch.object(
                roster.ContactRosterItem,
                "wrap",
            ))
            wrap.side_effect = generate_items()

            put = stack.enter_context(unittest.mock.patch.object(
                jclib.storage.xml,
                "put",
            ))

            self.rs._on_entry_added(unittest.mock.sentinel.upstream_item1)

            self.rs.save()

            put.reset_mock()

            self.rs._on_entry_added(unittest.mock.sentinel.upstream_item1)

            self.rs.save()

            put.assert_called_once_with(
                jclib.storage.StorageType.CACHE,
                jclib.storage.AccountLevel(self.account.jid),
                [
                    unittest.mock.sentinel.xso1,
                    unittest.mock.sentinel.xso2,
                ]
            )

    def test_set_label_uses_roster_service(self):
        client = self._prep_client()
        self.rs.prepare_client(client)

        item = unittest.mock.Mock(spec=roster.ContactRosterItem)

        run_coroutine(self.rs.set_label(
            item,
            unittest.mock.sentinel.new_label,
        ))

        self.roster.set_entry.assert_called_once_with(
            item.address,
            name=unittest.mock.sentinel.new_label,
        )

    def test_update_tags_uses_roster_service(self):
        client = self._prep_client()
        self.rs.prepare_client(client)

        item = unittest.mock.Mock(spec=roster.ContactRosterItem)

        run_coroutine(self.rs.update_tags(
            item,
            unittest.mock.sentinel.tags_to_add,
            unittest.mock.sentinel.tags_to_remove,
        ))

        self.roster.set_entry.assert_called_once_with(
            item.address,
            add_to_groups=unittest.mock.sentinel.tags_to_add,
            remove_from_groups=unittest.mock.sentinel.tags_to_remove,
        )

    def test_remove_uses_roster_service(self):
        client = self._prep_client()
        self.rs.prepare_client(client)

        item = unittest.mock.Mock(spec=roster.ContactRosterItem)

        run_coroutine(self.rs.remove(
            item,
        ))

        self.roster.remove_entry.assert_called_once_with(
            item.address,
        )


class TestConferenceBookmarkService(unittest.TestCase):
    def setUp(self):
        self.account = unittest.mock.Mock(["jid"])
        self.bookmarks = unittest.mock.Mock(
            spec=aioxmpp.BookmarkClient,
        )
        self.writeman = unittest.mock.Mock(spec=jclib.storage.WriteManager)
        self.rs = roster.ConferenceBookmarkService(self.account, self.writeman)
        self.listener = make_listener(self.rs)

    def _prep_client(self):
        client = make_connected_client()
        client.mock_services[aioxmpp.BookmarkClient] = self.bookmarks
        return client

    def test_not_writable_by_default(self):
        self.assertFalse(self.rs.is_writable)

    def test_connects_weakly_to_write_manager(self):
        self.writeman.on_writeback.connect.assert_called_once_with(
            self.rs.save,
            self.writeman.on_writeback.WEAK
        )

    def test_prepare_client_summons_roster_and_connects_signals(self):
        client = self._prep_client()
        self.rs.prepare_client(client)

        self.bookmarks.on_bookmark_added.connect.assert_called_once_with(
            self.rs._on_bookmark_added,
        )

        self.bookmarks.on_bookmark_removed.connect.assert_called_once_with(
            self.rs._on_bookmark_removed,
        )

        self.bookmarks.on_bookmark_changed.connect.assert_called_once_with(
            self.rs._on_bookmark_changed,
        )

    def test_prepare_client_makes_service_writable(self):
        client = self._prep_client()
        self.rs.prepare_client(client)

        self.assertTrue(self.rs.is_writable)

    def test_shutdown_client_disconnects_signals(self):
        client = self._prep_client()
        self.rs.prepare_client(client)
        self.rs.shutdown_client(client)

        self.bookmarks.on_bookmark_added.disconnect.assert_called_once_with(
            self.bookmarks.on_bookmark_added.connect(),
        )

        self.bookmarks.on_bookmark_removed.disconnect.assert_called_once_with(
            self.bookmarks.on_bookmark_removed.connect(),
        )

        self.bookmarks.on_bookmark_changed.disconnect.assert_called_once_with(
            self.bookmarks.on_bookmark_changed.connect(),
        )

    def test_shutdown_makes_service_non_writable(self):
        client = self._prep_client()
        self.rs.prepare_client(client)
        self.rs.shutdown_client(client)

        self.assertFalse(self.rs.is_writable)

    def test__on_bookmark_added_adds_item(self):
        with contextlib.ExitStack() as stack:
            wrap = stack.enter_context(
                unittest.mock.patch.object(roster.MUCRosterItem, "wrap")
            )

            self.rs._on_bookmark_added(unittest.mock.sentinel.upstream_item)

        wrap.assert_called_once_with(
            self.account,
            self.rs,
            unittest.mock.sentinel.upstream_item,
        )

        self.assertEqual(len(self.rs), 1)
        self.assertEqual(self.rs[0], wrap())

        self.writeman.request_writeback.assert_called_once_with()

    def test__on_bookmark_removed_removes_item(self):
        upstream_item1_ver1 = unittest.mock.Mock()
        upstream_item1_ver1.jid = TEST_JID1
        upstream_item1_ver2 = unittest.mock.Mock()
        upstream_item1_ver2.jid = TEST_JID1

        upstream_item2 = unittest.mock.Mock()
        upstream_item2.jid = TEST_JID2
        upstream_item2.groups = []

        self.rs._on_bookmark_added(upstream_item1_ver1)
        self.rs._on_bookmark_added(upstream_item2)

        self.writeman.request_writeback.reset_mock()
        self.rs._on_bookmark_removed(upstream_item1_ver2)
        self.writeman.request_writeback.assert_called_once_with()

        self.assertEqual(len(self.rs), 1)
        self.assertEqual(self.rs[0].address, TEST_JID2)

    def test_set_label_uses_bookmark_service(self):
        client = self._prep_client()
        self.bookmarks.update_bookmark = CoroutineMock()
        self.bookmarks.update_bookmark.return_value = \
            unittest.mock.sentinel.result
        self.rs.prepare_client(client)

        item = unittest.mock.Mock(spec=roster.MUCRosterItem)

        with contextlib.ExitStack() as stack:
            copy = stack.enter_context(unittest.mock.patch(
                "copy.copy",
            ))

            result = run_coroutine(
                self.rs.set_label(item, "new label")
            )

        item.to_bookmark.assert_called_once_with()
        copy.assert_called_once_with(item.to_bookmark())
        self.assertEqual(copy().name, "new label")

        self.bookmarks.update_bookmark.assert_called_once_with(
            item.to_bookmark(),
            copy(),
        )

        self.assertEqual(result, unittest.mock.sentinel.result)

    def test_remove_uses_bookmark_service(self):
        client = self._prep_client()
        self.bookmarks.discard_bookmark = CoroutineMock()
        self.rs.prepare_client(client)

        item = unittest.mock.Mock(spec=roster.MUCRosterItem)

        run_coroutine(
            self.rs.remove(item)
        )

        item.to_bookmark.assert_called_once_with()
        self.bookmarks.discard_bookmark.assert_called_once_with(
            item.to_bookmark()
        )

    def test__on_bookmark_changed_updates_item_and_emits_data_changed(self):
        with contextlib.ExitStack() as stack:
            wrap = stack.enter_context(
                unittest.mock.patch.object(roster.MUCRosterItem, "wrap")
            )

            self.rs._on_bookmark_added(unittest.mock.sentinel.upstream_item)

        self.writeman.request_writeback.reset_mock()

        wrap.assert_called_once_with(
            self.account,
            self.rs,
            unittest.mock.sentinel.upstream_item,
        )

        old_item = unittest.mock.Mock()
        old_item.jid = wrap().address

        new_item = unittest.mock.Mock()
        new_item.jid = wrap().address

        self.rs._on_bookmark_changed(old_item, new_item)

        wrap().update.assert_called_once_with(new_item)

        self.listener.data_changed.assert_called_once_with(
            None,
            0, 0,
            None, None,
            None,
        )

        self.writeman.request_writeback.assert_called_once_with()


class TestRosterManager(unittest.TestCase):
    def setUp(self):
        self.accounts = unittest.mock.Mock(spec=jclib.identity.Accounts)
        self.client = unittest.mock.Mock(spec=jclib.client.Client)
        self.writeman = unittest.mock.Mock(spec=jclib.storage.WriteManager)
        self.gr = roster.RosterManager(self.accounts, self.client,
                                       self.writeman)

    def test_connects_to_client_events(self):
        self.client.on_client_prepare.connect.assert_called_once_with(
            self.gr._prepare_client,
        )

        self.client.on_client_stopped.connect.assert_called_once_with(
            self.gr._shutdown_client,
        )

    def test__prepare_client_creates_contact_service_and_links_it(self):
        client = unittest.mock.Mock(spec=aioxmpp.Client)
        account = unittest.mock.Mock(spec=jclib.identity.Account)

        with contextlib.ExitStack() as stack:
            ContactRosterService = stack.enter_context(
                unittest.mock.patch("jclib.roster.ContactRosterService")
            )

            _items = stack.enter_context(
                unittest.mock.patch.object(self.gr, "_backend")
            )

            self.gr._prepare_client(account, client)

        self.assertSequenceEqual(
            ContactRosterService.mock_calls,
            [
                unittest.mock.call(account, self.writeman),
                unittest.mock.call().on_tag_added.connect(
                    self.gr._on_tag_added,
                ),
                unittest.mock.call().on_tag_removed.connect(
                    self.gr._on_tag_removed,
                ),
                unittest.mock.call().load(),
                unittest.mock.call().prepare_client(client),
            ]
        )

        self.assertIn(
            unittest.mock.call.append_source(ContactRosterService()),
            _items.mock_calls,
        )

    def test__prepare_client_creates_bookmark_service_and_links_it(self):
        client = unittest.mock.Mock(spec=aioxmpp.Client)
        account = unittest.mock.Mock(spec=jclib.identity.Account)

        with contextlib.ExitStack() as stack:
            ConferenceBookmarkService = stack.enter_context(
                unittest.mock.patch("jclib.roster.ConferenceBookmarkService")
            )

            _items = stack.enter_context(
                unittest.mock.patch.object(self.gr, "_backend")
            )

            self.gr._prepare_client(account, client)

        self.assertSequenceEqual(
            ConferenceBookmarkService.mock_calls,
            [
                unittest.mock.call(account, self.writeman),
                unittest.mock.call().on_tag_added.connect(
                    self.gr._on_tag_added,
                ),
                unittest.mock.call().on_tag_removed.connect(
                    self.gr._on_tag_removed,
                ),
                unittest.mock.call().load(),
                unittest.mock.call().prepare_client(client),
            ]
        )

        self.assertIn(
            unittest.mock.call.append_source(ConferenceBookmarkService()),
            _items.mock_calls,
        )

    def test__shutdown_client_cleans_up_previously_created_services(self):
        client = unittest.mock.Mock(spec=aioxmpp.Client)
        account = unittest.mock.Mock(spec=jclib.identity.Account)

        with contextlib.ExitStack() as stack:
            ContactRosterService = stack.enter_context(
                unittest.mock.patch("jclib.roster.ContactRosterService")
            )

            ConferenceBookmarkService = stack.enter_context(
                unittest.mock.patch("jclib.roster.ConferenceBookmarkService")
            )

            _items = stack.enter_context(
                unittest.mock.patch.object(self.gr, "_backend")
            )

            self.gr._prepare_client(account, client)

            self.gr._shutdown_client(account, client)

        ContactRosterService().shutdown_client.assert_called_once_with(client)
        ConferenceBookmarkService().shutdown_client.assert_called_once_with(
            client
        )

        self.assertIn(
            unittest.mock.call.remove_source(ContactRosterService()),
            _items.mock_calls,
        )

        self.assertIn(
            unittest.mock.call.remove_source(ConferenceBookmarkService()),
            _items.mock_calls,
        )

    def test_index_is_optimised(self):
        item = unittest.mock.Mock(["owner"])
        item.owner.index.return_value = unittest.mock.MagicMock(["__add__"])

        with contextlib.ExitStack() as stack:
            source_offset = stack.enter_context(unittest.mock.patch.object(
                self.gr._backend,
                "source_offset",
            ))
            source_offset.return_value = unittest.mock.MagicMock(
                ["__add__"]
            )

            index = self.gr.index(item)

        source_offset.assert_called_once_with(item.owner)
        item.owner.index.assert_called_once_with(item)

        source_offset().__add__.assert_called_once_with(item.owner.index())

        self.assertEqual(index, source_offset().__add__())

    def test_empty_tags(self):
        self.assertCountEqual(self.gr.tags, [])
        self.assertIsInstance(
            self.gr.tags,
            jclib.instrumentable_list.ModelListView
        )

    def test__on_tag_added_makes_tag_appear_in_tags(self):
        self.gr._on_tag_added("foo")
        self.assertCountEqual(self.gr.tags, {"foo"})

    def test__on_tag_added_does_not_duplicate_tags(self):
        self.gr._on_tag_added("foo")
        self.assertCountEqual(self.gr.tags, {"foo"})
        self.gr._on_tag_added("bar")
        self.assertCountEqual(self.gr.tags, {"bar", "foo"})
        self.gr._on_tag_added("foo")
        self.assertCountEqual(self.gr.tags, {"bar", "foo"})

    def test__on_tag_removed_makes_tag_disappear_in_tags(self):
        self.gr._on_tag_added("foo")
        self.gr._on_tag_added("bar")
        self.gr._on_tag_removed("foo")
        self.assertCountEqual(self.gr.tags, {"bar"})

    def test__on_tag_added_and_remove_use_some_counter_mechanism(self):
        self.gr._on_tag_added("foo")
        self.gr._on_tag_added("foo")
        self.gr._on_tag_added("bar")
        self.gr._on_tag_removed("foo")
        self.assertCountEqual(self.gr.tags, {"foo", "bar"})
        self.gr._on_tag_removed("foo")
        self.assertCountEqual(self.gr.tags, {"bar"})
