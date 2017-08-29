import contextlib
import itertools
import unittest
import unittest.mock

import mlxc.client
import mlxc.identity
import mlxc.roster as roster
import mlxc.storage
import mlxc.xso

import aioxmpp

from aioxmpp.testutils import (
    make_connected_client,
    make_listener,
)


TEST_JID1 = aioxmpp.JID.fromstr("romeo@montague.lit")
TEST_JID2 = aioxmpp.JID.fromstr("juliet@capulet.lit")
TEST_JID3 = aioxmpp.JID.fromstr("alice@hub.sotecware.net")
TEST_JID4 = aioxmpp.JID.fromstr("bob@hub.sotecware.net")
TEST_JID5 = aioxmpp.JID.fromstr("carol@hub.sotecware.net")


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
            self.upstream_item,
        )

        self.assertEqual(result.account, unittest.mock.sentinel.account)
        self.assertEqual(result.address, self.upstream_item.jid)
        self.assertEqual(result.label, self.upstream_item.name)
        self.assertCountEqual(result.tags, self.upstream_item.groups)
        self.assertEqual(result.subscription, self.upstream_item.subscription)
        self.assertEqual(result.approved, self.upstream_item.approved)
        self.assertEqual(result.ask, self.upstream_item.ask)

    def test_from_xso(self):
        obj = mlxc.xso.RosterContact()
        obj.address = TEST_JID2
        obj.label = "Juliet Capulet"
        obj.tags.update(["foo", "bar"])
        obj.approved = True
        obj.ask = True
        obj.subscription = "foo"

        item = roster.ContactRosterItem.from_xso(
            unittest.mock.sentinel.account,
            obj,
        )

        self.assertIsInstance(item, roster.ContactRosterItem)

        self.assertEqual(item.account, unittest.mock.sentinel.account)
        self.assertEqual(item.address, TEST_JID2)
        self.assertEqual(item.label, "Juliet Capulet")
        self.assertCountEqual(item.tags, ["foo", "bar"])
        self.assertEqual(item.ask, True)
        self.assertEqual(item.approved, True)
        self.assertEqual(item.subscription, "foo")

    def test_to_xso(self):
        item = roster.ContactRosterItem(
            unittest.mock.sentinel.account,
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
            TEST_JID1,
            tags=["foo", "bar"],
            subscription="both",
            ask=True,
            approved=True,
        )

        obj = item.to_xso()

        self.assertIsInstance(obj, mlxc.xso.RosterContact)
        self.assertEqual(obj.address, TEST_JID1)
        self.assertIsNone(obj.label)
        self.assertSetEqual(obj.tags, {"foo", "bar"})
        self.assertEqual(obj.subscription, "both")
        self.assertTrue(obj.ask)
        self.assertTrue(obj.approved)

    def test_update_updates_contents(self):
        item = roster.ContactRosterItem(
            unittest.mock.sentinel.account,
            TEST_JID1,
        )
        item.update(self.upstream_item)

        self.assertEqual(item.account, unittest.mock.sentinel.account)

        self.assertEqual(item.label, self.upstream_item.name)
        self.assertCountEqual(item.tags, self.upstream_item.groups)
        self.assertEqual(item.subscription, self.upstream_item.subscription)
        self.assertEqual(item.approved, self.upstream_item.approved)
        self.assertEqual(item.ask, self.upstream_item.ask)


class Testcontacts_to_json(unittest.TestCase):
    def test_minimal(self):
        contacts = [
            roster.ContactRosterItem(
                unittest.mock.sentinel.account,
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
                    TEST_JID1,
                    ask=True,
                    approved=True,
                ),
                roster.ContactRosterItem(
                    unittest.mock.sentinel.account,
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
        self.writeman = unittest.mock.Mock(spec=mlxc.storage.WriteManager)
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

    def test_load(self):
        def generate_results():
            for i, address in enumerate([TEST_JID1, TEST_JID3, TEST_JID4]):
                yield roster.ContactRosterItem(
                    unittest.mock.sentinel.account,
                    address,
                    label="Contact no. {}".format(i)
                )

        with contextlib.ExitStack() as stack:
            get_all = stack.enter_context(unittest.mock.patch.object(
                mlxc.storage.xml,
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
            mlxc.storage.StorageType.CACHE,
            mlxc.storage.AccountLevel(self.account.jid),
            mlxc.xso.RosterContact,
        )

        self.assertCountEqual(
            from_xso.mock_calls,
            [
                unittest.mock.call(self.account, unittest.mock.sentinel.item0),
                unittest.mock.call(self.account, unittest.mock.sentinel.item1),
                unittest.mock.call(self.account, unittest.mock.sentinel.item2),
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
                    address,
                    label="Contact no. {}".format(i)
                )

        with contextlib.ExitStack() as stack:
            get_all = stack.enter_context(unittest.mock.patch.object(
                mlxc.storage.xml,
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
                mlxc.storage.xml,
                "put",
            ))

            self.rs.save()

        put.assert_called_once_with(
            mlxc.storage.StorageType.CACHE,
            mlxc.storage.AccountLevel(self.account.jid),
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
                mlxc.storage.xml,
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
                mlxc.storage.xml,
                "put",
            ))

            self.rs._on_entry_added(unittest.mock.sentinel.upstream_item1)

            self.rs.save()

            put.reset_mock()

            self.rs._on_entry_added(unittest.mock.sentinel.upstream_item1)

            self.rs.save()

            put.assert_called_once_with(
                mlxc.storage.StorageType.CACHE,
                mlxc.storage.AccountLevel(self.account.jid),
                [
                    unittest.mock.sentinel.xso1,
                    unittest.mock.sentinel.xso2,
                ]
            )


class TestRosterManager(unittest.TestCase):
    def setUp(self):
        self.accounts = unittest.mock.Mock(spec=mlxc.identity.Accounts)
        self.client = unittest.mock.Mock(spec=mlxc.client.Client)
        self.writeman = unittest.mock.Mock(spec=mlxc.storage.WriteManager)
        self.gr = roster.RosterManager(self.accounts, self.client,
                                       self.writeman)

    def test_connects_to_client_events(self):
        self.client.on_client_prepare.connect.assert_called_once_with(
            self.gr._prepare_client,
        )

        self.client.on_client_stopped.connect.assert_called_once_with(
            self.gr._shutdown_client,
        )

    def test__prepare_client_creates_roster_and_links_it(self):
        client = unittest.mock.Mock(spec=aioxmpp.Client)
        account = unittest.mock.Mock(spec=mlxc.identity.Account)

        with contextlib.ExitStack() as stack:
            ContactRosterService = stack.enter_context(
                unittest.mock.patch("mlxc.roster.ContactRosterService")
            )

            _items = stack.enter_context(
                unittest.mock.patch.object(self.gr, "_items")
            )

            self.gr._prepare_client(account, client)

        self.assertSequenceEqual(
            ContactRosterService.mock_calls,
            [
                unittest.mock.call(account, self.writeman),
                unittest.mock.call().load(),
                unittest.mock.call().prepare_client(client),
            ]
        )

        _items.append_source.assert_called_once_with(ContactRosterService())

    def test__shutdown_client_cleans_up_previously_created_service(self):
        client = unittest.mock.Mock(spec=aioxmpp.Client)
        account = unittest.mock.Mock(spec=mlxc.identity.Account)

        with contextlib.ExitStack() as stack:
            ContactRosterService = stack.enter_context(
                unittest.mock.patch("mlxc.roster.ContactRosterService")
            )

            _items = stack.enter_context(
                unittest.mock.patch.object(self.gr, "_items")
            )

            self.gr._prepare_client(account, client)

            self.gr._shutdown_client(account, client)

        ContactRosterService().shutdown_client.assert_called_once_with(client)
        _items.remove_source.assert_called_once_with(ContactRosterService())
