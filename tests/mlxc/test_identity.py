import contextlib
import itertools
import unittest
import unittest.mock

import aioxmpp

import mlxc.identity as identity
import mlxc.instrumentable_list
import mlxc.xso


TEST_JID = aioxmpp.JID.fromstr("foo@bar.example")


class TestAccount(unittest.TestCase):
    def setUp(self):
        self.tree = mlxc.instrumentable_list.ModelTree()
        self.node = mlxc.instrumentable_list.ModelTreeNode(self.tree)
        self.i = unittest.mock.Mock()
        self.a = identity.Account(self.node, TEST_JID,
                                  unittest.mock.sentinel.colour)

    def tearDown(self):
        del self.i
        del self.a
        del self.node
        del self.tree

    def test_init(self):
        self.assertIs(self.a._node, self.node)
        self.assertEqual(self.a.jid, TEST_JID)
        self.assertTrue(self.a.enabled)
        self.assertFalse(self.a.allow_unencrypted)
        self.assertSequenceEqual(self.a.stashed_xml, [])
        self.assertEqual(self.a.colour, unittest.mock.sentinel.colour)

    def test_jid_is_not_writable(self):
        with self.assertRaises(AttributeError):
            self.a.jid = TEST_JID

    def test_from_xso(self):
        x = mlxc.xso.AccountSettings(TEST_JID)
        x.disabled = True
        x.allow_unencrypted = True
        x.colour = "127 127 127"
        x._ = [unittest.mock.sentinel.foo, unittest.mock.sentinel.bar]

        a = identity.Account.from_xso(x, self.node)
        self.assertIs(a._node, self.node)
        self.assertEqual(a.jid, x.jid)
        self.assertEqual(a.enabled, not x.disabled)
        self.assertEqual(a.allow_unencrypted, x.allow_unencrypted)
        self.assertEqual(a.colour, (127, 127, 127))
        self.assertIsNot(a.stashed_xml, x._)
        self.assertSequenceEqual(a.stashed_xml, x._)

    def test_to_xso(self):
        self.a.disabled = True
        self.a.allow_unencrypted = True
        self.a.stashed_xml = [unittest.mock.sentinel.foo,
                              unittest.mock.sentinel.bar]
        self.a.colour = (123, 456, 789)

        x = self.a.to_xso()
        self.assertIsInstance(x, mlxc.xso.AccountSettings)
        self.assertEqual(x.jid, self.a.jid)
        self.assertEqual(x.disabled, not self.a.enabled)
        self.assertEqual(x.allow_unencrypted,
                         self.a.allow_unencrypted)
        self.assertEqual(x.colour, "123 456 789")
        self.assertIsNot(x._, self.a.stashed_xml)
        self.assertSequenceEqual(x._, self.a.stashed_xml)


class TestIdentity(unittest.TestCase):
    def setUp(self):
        self.tree = mlxc.instrumentable_list.ModelTree()
        self.node = mlxc.instrumentable_list.ModelTreeNode(self.tree)
        self.i = identity.Identity(self.node, "foobar")

    def tearDown(self):
        del self.i
        del self.node
        del self.tree

    def test_init(self):
        self.assertIs(self.node, self.i.accounts)
        self.assertIs(self.node, self.i._node)
        self.assertEqual(self.i.name, "foobar")
        self.assertSequenceEqual(self.i.custom_presences, [])
        self.assertSequenceEqual(self.i.stashed_xml, [])

    def test_from_xso(self):
        x = mlxc.xso.IdentitySettings()
        x.name = "fnord"
        x.accounts = [
            unittest.mock.sentinel.acc1_s,
            unittest.mock.sentinel.acc2_s,
            unittest.mock.sentinel.acc3_s,
        ]
        x.custom_presences = [
            unittest.mock.sentinel.cp1,
            unittest.mock.sentinel.cp2,
        ]
        x._ = [
            unittest.mock.sentinel.foo,
            unittest.mock.sentinel.bar,
        ]

        acc_base = unittest.mock.Mock()

        def account_generator():
            for i in itertools.count():
                result = getattr(acc_base, "acc{}".format(i))
                result.parent = None
                yield result

        def node_generator():
            for i in itertools.count():
                yield getattr(unittest.mock.sentinel, "node{}".format(i))

        with contextlib.ExitStack() as stack:
            ModelTreeNode = stack.enter_context(
                unittest.mock.patch("mlxc.instrumentable_list.ModelTreeNode")
            )
            ModelTreeNode.side_effect = node_generator()

            Account = stack.enter_context(
                unittest.mock.patch("mlxc.identity.Account")
            )
            Account.from_xso.side_effect = account_generator()

            i = identity.Identity.from_xso(x, self.node)

        self.assertIsInstance(i, identity.Identity)

        self.assertSequenceEqual(
            ModelTreeNode.mock_calls,
            [
                unittest.mock.call(self.tree)
            ]*len(x.accounts)
        )

        self.assertSequenceEqual(
            Account.mock_calls,
            [
                unittest.mock.call.from_xso(
                    acc_s,
                    getattr(unittest.mock.sentinel, "node{}".format(i)),
                )
                for i, acc_s in enumerate(x.accounts)
            ]
        )

        self.assertSequenceEqual(
            i.accounts,
            [
                getattr(acc_base, "acc{}".format(i))
                for i in range(len(x.accounts))
            ]
        )

        self.assertIsNot(
            i.custom_presences,
            x.custom_presences
        )
        self.assertSequenceEqual(
            i.custom_presences,
            x.custom_presences
        )

        self.assertIsNot(
            i.stashed_xml,
            x._
        )
        self.assertSequenceEqual(
            i.stashed_xml,
            x._
        )


class TestIdentities(unittest.TestCase):
    def setUp(self):
        self.c = identity.Identities()
        self.cbs = unittest.mock.Mock()

        def link_cb(name):
            cb = getattr(self.cbs, name)
            cb.return_value = None
            getattr(self.c, "on_{}".format(name)).connect(cb)

        def link_model_ev(name):
            cb = getattr(self.cbs, name)
            cb.return_value = None
            getattr(self.c._tree, name).connect(cb)

        link_cb("account_enabled")
        link_cb("account_disabled")

        link_cb("account_online")
        link_cb("account_offline")
        link_cb("account_unstable")

        link_cb("account_added")
        link_cb("account_removed")

        link_cb("identity_added")
        link_cb("identity_removed")
        link_cb("identity_enabled")
        link_cb("identity_disabled")

        link_model_ev("data_changed")

    def tearDown(self):
        del self.c

    def test_new_identity(self):
        with contextlib.ExitStack() as stack:
            Identity = stack.enter_context(
                unittest.mock.patch(
                    "mlxc.identity.Identity"
                )
            )
            Identity().parent = None

            ModelTreeNode = stack.enter_context(
                unittest.mock.patch(
                    "mlxc.instrumentable_list.ModelTreeNode"
                )
            )
            Identity()._node = ModelTreeNode()

            result = self.c.new_identity(
                unittest.mock.sentinel.name
            )

        ModelTreeNode.assert_called_with(self.c._tree)

        Identity.assert_called_with(
            ModelTreeNode(),
            unittest.mock.sentinel.name,
        )

        self.assertEqual(
            result,
            Identity(),
        )

        self.assertIn(
            result,
            self.c.identities,
        )

        self.cbs.identity_added.assert_called_once_with(result)
        self.cbs.identity_enabled.assert_called_once_with(result)

    def test_identities_is_tree_node(self):
        self.assertIsInstance(
            self.c.identities,
            mlxc.instrumentable_list.ModelTreeNode
        )

    def test_identities_is_node_of_holder(self):
        self.assertIs(
            self.c._node,
            self.c.identities,
        )

    def test_new_account(self):
        identity = self.c.new_identity("foobar")
        with contextlib.ExitStack() as stack:
            Account = stack.enter_context(
                unittest.mock.patch(
                    "mlxc.identity.Account"
                )
            )
            Account().parent = None

            ModelTreeNode = stack.enter_context(
                unittest.mock.patch(
                    "mlxc.instrumentable_list.ModelTreeNode"
                )
            )
            Account()._node = ModelTreeNode()

            acc = self.c.new_account(identity, TEST_JID, (255, 255, 255))

        ModelTreeNode.assert_called_with(
            self.c._tree
        )

        Account.assert_called_with(
            ModelTreeNode(),
            TEST_JID,
            (255, 255, 255),
        )

        self.assertEqual(acc, Account())

        self.assertIn(acc, identity.accounts)

        self.cbs.account_added.assert_called_once_with(acc)
        self.cbs.account_enabled.assert_called_once_with(acc)

    def test_new_account_enforces_distinct_jids_over_identities(self):
        identity1 = self.c.new_identity("foobar")
        identity2 = self.c.new_identity("baz")

        with contextlib.ExitStack() as stack:
            Account = stack.enter_context(
                unittest.mock.patch(
                    "mlxc.identity.Account"
                )
            )
            Account().parent = None

            ModelTreeNode = stack.enter_context(
                unittest.mock.patch(
                    "mlxc.instrumentable_list.ModelTreeNode"
                )
            )
            Account()._node = ModelTreeNode()

            self.c.new_account(identity1, TEST_JID,
                               unittest.mock.sentinel.c)

            with self.assertRaisesRegex(
                    ValueError,
                    "duplicate account JID"):
                self.c.new_account(identity2, TEST_JID,
                                   unittest.mock.sentinel.c)

    def test_new_account_extracts_resource(self):
        identity = self.c.new_identity("foobar")
        with contextlib.ExitStack() as stack:
            Account = stack.enter_context(
                unittest.mock.patch(
                    "mlxc.identity.Account"
                )
            )
            Account().parent = None

            ModelTreeNode = stack.enter_context(
                unittest.mock.patch(
                    "mlxc.instrumentable_list.ModelTreeNode"
                )
            )
            Account()._node = ModelTreeNode()

            acc = self.c.new_account(identity, TEST_JID,
                                     unittest.mock.sentinel.c)

        ModelTreeNode.assert_called_with(
            self.c._tree
        )

        Account.assert_called_with(
            ModelTreeNode(),
            TEST_JID,
            unittest.mock.sentinel.c,
        )

        self.assertEqual(acc, Account())

        self.assertIn(acc, identity.accounts)

    def test_new_account_extracts_resource_from_jid(self):
        identity = self.c.new_identity("foobar")

        with contextlib.ExitStack() as stack:
            Account = stack.enter_context(
                unittest.mock.patch(
                    "mlxc.identity.Account"
                )
            )
            Account().parent = None

            ModelTreeNode = stack.enter_context(
                unittest.mock.patch(
                    "mlxc.instrumentable_list.ModelTreeNode"
                )
            )
            Account()._node = ModelTreeNode()

            acc = self.c.new_account(
                identity,
                TEST_JID.replace(resource="fnord"),
                unittest.mock.sentinel.c
            )

            with self.assertRaises(ValueError):
                self.c.new_account(
                    identity,
                    TEST_JID.replace(resource="foo"),
                    unittest.mock.sentinel.c
                )

        self.assertEqual(
            acc.resource,
            "fnord",
        )

    def test_lookup_jid(self):
        identity = self.c.new_identity("foobar")
        account = self.c.new_account(identity, TEST_JID,
                                     unittest.mock.sentinel.c)

        self.assertEqual(
            self.c.lookup_jid(TEST_JID),
            (identity, account)
        )

        self.assertEqual(
            self.c.lookup_jid(TEST_JID.replace(resource="fnord")),
            (identity, account)
        )

    def test_lookup_jid_raises_key_error_for_unknown_jid(self):
        with self.assertRaises(KeyError):
            self.c.lookup_jid(TEST_JID)

    def test_remove_account(self):
        identity = self.c.new_identity("foobar")
        account = self.c.new_account(identity, TEST_JID,
                                     unittest.mock.sentinel.c)

        self.cbs.mock_calls.clear()

        self.c.remove_account(account)

        self.assertSequenceEqual(
            identity.accounts,
            []
        )

        self.cbs.account_disabled.assert_called_once_with(account)
        self.cbs.account_removed.assert_called_once_with(account)

    def test_remove_account_clears_lookup_jid_result(self):
        identity = self.c.new_identity("foobar")
        account = self.c.new_account(identity, TEST_JID,
                                     unittest.mock.sentinel.c)

        self.c.remove_account(account)

        with self.assertRaises(KeyError):
            self.c.lookup_jid(account.jid)

    def test_remove_account_allows_creation_of_account_with_same_jid(self):
        identity = self.c.new_identity("foobar")
        account = self.c.new_account(identity, TEST_JID,
                                     unittest.mock.sentinel.c)

        self.c.remove_account(account)

        self.c.new_account(identity, TEST_JID,
                           unittest.mock.sentinel.c)

    def test_remove_identity_removes_identity_and_accounts(self):
        identity = self.c.new_identity("foobar")
        account = self.c.new_account(identity, TEST_JID,
                                     unittest.mock.sentinel.c)

        self.cbs.mock_calls.clear()

        self.c.remove_identity(identity)

        self.assertSequenceEqual(
            self.c.identities,
            []
        )

        self.assertSequenceEqual(
            self.cbs.mock_calls,
            [
                unittest.mock.call.account_disabled(account),
                unittest.mock.call.account_removed(account),
                unittest.mock.call.identity_disabled(identity),
                unittest.mock.call.identity_removed(identity),
            ],
        )

    def test_remove_identity_clears_lookup_jid_result(self):
        identity1 = self.c.new_identity("foobar")
        self.c.new_account(identity1, TEST_JID.replace(localpart="acc1"),
                           unittest.mock.sentinel.c)
        self.c.new_account(identity1, TEST_JID.replace(localpart="acc2"),
                           unittest.mock.sentinel.c)

        identity2 = self.c.new_identity("baz")
        acc3 = self.c.new_account(identity2,
                                  TEST_JID.replace(localpart="acc3"),
                                  unittest.mock.sentinel.c)

        self.c.remove_identity(identity1)

        self.assertSequenceEqual(
            self.c.identities,
            [
                identity2
            ]
        )

        self.assertEqual(
            self.c.lookup_jid(TEST_JID.replace(localpart="acc3")),
            (identity2, acc3)
        )

        with self.assertRaises(KeyError):
            self.c.lookup_jid(TEST_JID.replace(localpart="acc1"))

        with self.assertRaises(KeyError):
            self.c.lookup_jid(TEST_JID.replace(localpart="acc2"))

    def test_disable_account(self):
        identity1 = self.c.new_identity("foobar")
        acc11 = self.c.new_account(identity1,
                                   TEST_JID.replace(localpart="acc1"),
                                   unittest.mock.sentinel.c)
        self.c.new_account(identity1,
                           TEST_JID.replace(localpart="acc2"),
                           unittest.mock.sentinel.c)

        self.cbs.reset_mock()

        self.c.set_account_enabled(acc11, True)
        self.cbs.account_enabled.assert_not_called()
        self.assertTrue(acc11.enabled)

        self.c.set_account_enabled(acc11, False)
        self.cbs.account_disabled.assert_called_once_with(acc11)
        self.assertFalse(acc11.enabled)

        self.c.set_account_enabled(acc11, False)
        self.cbs.account_disabled.assert_called_once_with(acc11)
        self.assertFalse(acc11.enabled)

        self.c.set_account_enabled(acc11, True)
        self.cbs.account_enabled.assert_called_once_with(acc11)
        self.assertTrue(acc11.enabled)

    def test_disable_identity_emits_disable_account_events(self):
        identity1 = self.c.new_identity("foobar")
        acc11 = self.c.new_account(identity1,
                                   TEST_JID.replace(localpart="acc1"),
                                   unittest.mock.sentinel.c)
        acc12 = self.c.new_account(identity1,
                                   TEST_JID.replace(localpart="acc2"),
                                   unittest.mock.sentinel.c)

        self.c.set_account_enabled(acc11, False)

        self.cbs.mock_calls.clear()

        self.c.set_identity_enabled(identity1, False)

        self.assertSequenceEqual(
            self.cbs.mock_calls,
            [
                unittest.mock.call.account_disabled(acc12),
                unittest.mock.call.identity_disabled(identity1),
                unittest.mock.call.data_changed(
                    self.c.identities,
                    (identity1._parent_index, None),
                    (identity1._parent_index, None),
                    None,
                ),
                unittest.mock.call.data_changed(
                    identity1._node,
                    (0, None),
                    (len(identity1.accounts)-1, None),
                    None,
                ),
            ]
        )

    def test_reenabling_identity_emits_enable_account_events(self):
        identity1 = self.c.new_identity("foobar")
        acc11 = self.c.new_account(identity1,
                                   TEST_JID.replace(localpart="acc1"),
                                   unittest.mock.sentinel.c)
        acc12 = self.c.new_account(identity1,
                                   TEST_JID.replace(localpart="acc2"),
                                   unittest.mock.sentinel.c)

        self.c.set_account_enabled(acc11, False)
        self.c.set_identity_enabled(identity1, False)

        self.cbs.mock_calls.clear()

        self.c.set_identity_enabled(identity1, True)

        self.assertSequenceEqual(
            self.cbs.mock_calls,
            [
                unittest.mock.call.identity_enabled(identity1),
                unittest.mock.call.account_enabled(acc12),
                unittest.mock.call.data_changed(
                    self.c.identities,
                    (identity1._parent_index, None),
                    (identity1._parent_index, None),
                    None,
                ),
                unittest.mock.call.data_changed(
                    identity1._node,
                    (0, None),
                    (len(identity1.accounts)-1, None),
                    None,
                ),
            ]
        )

    def test_enabling_account_does_not_emit_event_if_identity_is_disabled(self):
        identity1 = self.c.new_identity("foobar")
        acc11 = self.c.new_account(identity1,
                                   TEST_JID.replace(localpart="acc1"),
                                   unittest.mock.sentinel.c)
        self.c.new_account(identity1,
                           TEST_JID.replace(localpart="acc2"),
                           unittest.mock.sentinel.c)

        self.c.set_account_enabled(acc11, False)
        self.c.set_identity_enabled(identity1, False)

        self.cbs.mock_calls.clear()

        self.c.set_account_enabled(acc11, True)

        self.assertSequenceEqual(
            self.cbs.mock_calls,
            [
                unittest.mock.call.data_changed(
                    identity1._node,
                    (acc11._parent_index, None),
                    (acc11._parent_index, None),
                    None,
                ),
            ]
        )

    def test_save_and_load_works(self):
        tmp = identity.Identities()

        identity1 = tmp.new_identity("foobar")
        acc11 = tmp.new_account(identity1,
                                TEST_JID.replace(localpart="acc1"),
                                (100, 200, 300))
        tmp.new_account(identity1,
                        TEST_JID.replace(localpart="acc2"),
                        (100, 200, 300))

        tmp.set_account_enabled(acc11, False)

        data = tmp._do_save_xso()
        self.c._do_load_xso(data)

        self.assertEqual(len(self.c.identities), 1)
        identity1_new = self.c.identities[0]

        self.assertTrue(identity1_new.enabled)
        self.assertEqual(len(identity1_new.accounts), 2)

        acc11_new = identity1_new.accounts[0]
        acc12_new = identity1_new.accounts[1]

        self.assertEqual(
            acc11_new.jid,
            TEST_JID.replace(localpart="acc1"),
        )
        self.assertFalse(acc11_new.enabled)

        self.assertEqual(
            acc12_new.jid,
            TEST_JID.replace(localpart="acc2"),
        )
        self.assertTrue(acc12_new.enabled)

        self.assertSequenceEqual(
            self.cbs.mock_calls,
            [
                unittest.mock.call.identity_added(identity1_new),
                unittest.mock.call.identity_enabled(identity1_new),
                unittest.mock.call.account_added(acc11_new),
                unittest.mock.call.account_added(acc12_new),
                unittest.mock.call.account_enabled(acc12_new),
            ]
        )

        self.assertIs(
            self.c.lookup_account_identity(acc11_new),
            identity1_new,
        )
        self.assertIs(
            self.c.lookup_account_identity(acc12_new),
            identity1_new,
        )

        self.assertEqual(
            self.c.lookup_jid(acc11_new.jid),
            (identity1_new, acc11_new),
        )
        self.assertEqual(
            self.c.lookup_jid(acc12_new.jid),
            (identity1_new, acc12_new),
        )
