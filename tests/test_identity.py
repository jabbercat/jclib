import contextlib
import itertools
import unittest
import unittest.mock

import aioxmpp

import mlxc.identity as identity
import mlxc.instrumentable_list
import mlxc.xso

from aioxmpp.testutils import (
    make_listener,
)


TEST_JID = aioxmpp.JID.fromstr("foo@bar.example")


class TestAccount(unittest.TestCase):
    def setUp(self):
        self.i = unittest.mock.Mock()
        self.a = identity.Account(TEST_JID, unittest.mock.sentinel.colour)

    def tearDown(self):
        del self.i
        del self.a

    def test_init(self):
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

        a = identity.Account.from_xso(x)
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


class TestAccounts(unittest.TestCase):
    def setUp(self):
        self.c = identity.Accounts()
        self.listener = make_listener(self.c)

    def tearDown(self):
        del self.c

    def test_is_model_list_view(self):
        self.assertIsInstance(
            self.c,
            mlxc.instrumentable_list.ModelListView
        )

    def test_new_account(self):
        with contextlib.ExitStack() as stack:
            Account = stack.enter_context(
                unittest.mock.patch(
                    "mlxc.identity.Account"
                )
            )

            acc = self.c.new_account(TEST_JID,
                                     unittest.mock.sentinel.colour)

        Account.assert_called_once_with(
            TEST_JID,
            unittest.mock.sentinel.colour,
        )

        self.assertEqual(acc, Account())

        self.assertIn(acc, self.c)

        self.listener.on_account_added.assert_called_once_with(acc)
        self.listener.on_account_enabled.assert_called_once_with(acc)

    def test_new_account_enforces_distinct_jids(self):
        with contextlib.ExitStack() as stack:
            Account = stack.enter_context(
                unittest.mock.patch(
                    "mlxc.identity.Account"
                )
            )

            self.c.new_account(TEST_JID,
                               unittest.mock.sentinel.c)

            with self.assertRaisesRegex(
                    ValueError,
                    "duplicate account JID"):
                self.c.new_account(TEST_JID,
                                   unittest.mock.sentinel.c)

    def test_new_account_extracts_resource_from_jid(self):
        with contextlib.ExitStack() as stack:
            Account = stack.enter_context(
                unittest.mock.patch(
                    "mlxc.identity.Account"
                )
            )

            acc = self.c.new_account(
                TEST_JID.replace(resource="fnord"),
                unittest.mock.sentinel.c
            )

            with self.assertRaises(ValueError):
                self.c.new_account(
                    TEST_JID.replace(resource="foo"),
                    unittest.mock.sentinel.c
                )

        self.assertEqual(
            acc.resource,
            "fnord",
        )

    def test_lookup_jid(self):
        account = self.c.new_account(TEST_JID,
                                     unittest.mock.sentinel.c)

        self.assertEqual(
            self.c.lookup_jid(TEST_JID),
            account
        )

        self.assertEqual(
            self.c.lookup_jid(TEST_JID.replace(resource="fnord")),
            account
        )

    def test_lookup_jid_raises_key_error_for_unknown_jid(self):
        with self.assertRaises(KeyError):
            self.c.lookup_jid(TEST_JID)

    def test_remove_account(self):
        account = self.c.new_account(TEST_JID,
                                     unittest.mock.sentinel.c)

        self.listener.mock_calls.clear()

        self.c.remove_account(account)

        self.assertSequenceEqual(
            self.c,
            []
        )

        self.listener.on_account_disabled.assert_called_once_with(account)
        self.listener.on_account_removed.assert_called_once_with(account)

    def test_remove_account_clears_lookup_jid_result(self):
        account = self.c.new_account(TEST_JID,
                                     unittest.mock.sentinel.c)

        self.c.remove_account(account)

        with self.assertRaises(KeyError):
            self.c.lookup_jid(account.jid)

    def test_remove_account_allows_creation_of_account_with_same_jid(self):
        account = self.c.new_account(TEST_JID,
                                     unittest.mock.sentinel.c)

        self.c.remove_account(account)

        self.c.new_account(TEST_JID,
                           unittest.mock.sentinel.c)

    def test_disable_account(self):
        acc11 = self.c.new_account(TEST_JID.replace(localpart="acc1"),
                                   unittest.mock.sentinel.c)
        self.c.new_account(TEST_JID.replace(localpart="acc2"),
                           unittest.mock.sentinel.c)

        self.listener.reset_mock()

        self.c.set_account_enabled(acc11, True)
        self.listener.on_account_enabled.assert_not_called()
        self.listener.data_changed.assert_not_called()
        self.assertTrue(acc11.enabled)

        self.c.set_account_enabled(acc11, False)
        self.listener.on_account_disabled.assert_called_once_with(acc11)
        self.listener.data_changed.assert_called_once_with(
            None,
            0, 0,
            None, None,
            None,
        )
        self.listener.data_changed.reset_mock()
        self.assertFalse(acc11.enabled)

        self.c.set_account_enabled(acc11, False)
        self.listener.on_account_disabled.assert_called_once_with(acc11)
        self.listener.data_changed.assert_not_called()
        self.assertFalse(acc11.enabled)

        self.c.set_account_enabled(acc11, True)
        self.listener.on_account_enabled.assert_called_once_with(acc11)
        self.listener.data_changed.assert_called_once_with(
            None,
            0, 0,
            None, None,
            None,
        )
        self.assertTrue(acc11.enabled)

    def test_save_and_load_works(self):
        tmp = identity.Accounts()

        acc11 = tmp.new_account(TEST_JID.replace(localpart="acc1"),
                                (100, 200, 300))
        tmp.new_account(TEST_JID.replace(localpart="acc2"),
                        (10, 20, 30))

        tmp.set_account_enabled(acc11, False)

        data = tmp._do_save_xso()
        self.c._do_load_xso(data)

        self.assertEqual(len(self.c), 2)

        acc11_new = self.c[0]
        acc12_new = self.c[1]

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
            self.listener.mock_calls,
            [
                unittest.mock.call.begin_insert_rows(None, 0, 0),
                unittest.mock.call.end_insert_rows(),
                unittest.mock.call.on_account_added(acc11_new),
                unittest.mock.call.begin_insert_rows(None, 1, 1),
                unittest.mock.call.end_insert_rows(),
                unittest.mock.call.on_account_added(acc12_new),
                unittest.mock.call.on_account_enabled(acc12_new),
            ]
        )

        self.assertEqual(
            self.c.lookup_jid(acc11_new.jid),
            acc11_new,
        )
        self.assertEqual(
            self.c.lookup_jid(acc12_new.jid),
            acc12_new,
        )
