import asyncio
import contextlib
import unittest
import unittest.mock

import keyring

import aioxmpp.structs as structs
import aioxmpp.xso as xso

import mlxc.client as client

from aioxmpp.testutils import run_coroutine

from mlxc.utils import mlxc_namespaces


TEST_JID = structs.JID.fromstr("foo@bar.example/baz")


@asyncio.coroutine
def noop(value=None, raises=None):
    if raises is not None:
        raise raises
    return value


class TestPasswordStoreIsUnsafe(unittest.TestCase):
    def test_is_exception(self):
        self.assertTrue(issubclass(
            client.PasswordStoreIsUnsafe,
            RuntimeError
        ))


class TestConnectionOverride(unittest.TestCase):
    def test_is_xso(self):
        self.assertTrue(issubclass(
            client.ConnectionOverride,
            xso.XSO
        ))

    def test_tag(self):
        self.assertEqual(
            client.ConnectionOverride.TAG,
            (mlxc_namespaces.account, "override-host"),
        )

    def test_host_attr(self):
        self.assertIsInstance(
            client.ConnectionOverride.host,
            xso.Text
        )

    def test_port_attr(self):
        self.assertIsInstance(
            client.ConnectionOverride.port,
            xso.Attr
        )
        self.assertEqual(
            client.ConnectionOverride.port.tag,
            (None, "port"),
        )
        self.assertIsInstance(
            client.ConnectionOverride.port.type_,
            xso.Integer
        )


class TestAccountSettings(unittest.TestCase):
    def test_is_xso(self):
        self.assertTrue(issubclass(
            client.AccountSettings,
            xso.XSO
        ))

    def test_tag(self):
        self.assertEqual(
            client.AccountSettings.TAG,
            (mlxc_namespaces.account, "account"),
        )

    def test_jid_attr(self):
        self.assertIsInstance(
            client.AccountSettings.jid,
            xso.Attr
        )
        self.assertEqual(
            client.AccountSettings.jid.tag,
            (None, "jid"),
        )
        self.assertIsInstance(
            client.AccountSettings.jid.type_,
            xso.JID
        )
        self.assertTrue(
            client.AccountSettings.jid.required
        )

    def test_enabled_attr(self):
        self.assertIsInstance(
            client.AccountSettings.enabled,
            xso.Attr
        )
        self.assertEqual(
            (None, "enabled"),
            client.AccountSettings.enabled.tag
        )
        self.assertIsInstance(
            client.AccountSettings.enabled.type_,
            xso.Bool
        )
        self.assertFalse(
            client.AccountSettings.enabled.required
        )
        self.assertIs(
            False,
            client.AccountSettings.enabled.default
        )

    def test_connection_override(self):
        self.assertIsInstance(
            client.AccountSettings.override_peer,
            xso.Child
        )
        self.assertSetEqual(
            set(client.AccountSettings.override_peer._classes),
            {
                client.ConnectionOverride,
            },
        )

    def test_allow_unencrypted_attr(self):
        self.assertIsInstance(
            client.AccountSettings.allow_unencrypted,
            xso.Attr
        )
        self.assertEqual(
            client.AccountSettings.allow_unencrypted.tag,
            (None, "allow-unencrypted"),
        )
        self.assertIsInstance(
            client.AccountSettings.allow_unencrypted.type_,
            xso.Bool
        )
        self.assertIs(
            client.AccountSettings.allow_unencrypted.default,
            False,
        )
        self.assertFalse(
            client.AccountSettings.allow_unencrypted.required
        )


class TestAccountManager(unittest.TestCase):
    def setUp(self):
        self.loop = asyncio.get_event_loop()
        self.keyring = unittest.mock.Mock()
        self.keyring.priority = 1
        self.manager = client.AccountManager(
            loop=self.loop,
            use_keyring=self.keyring
        )

    def test_keyring_info(self):
        self.assertEqual(
            client.AccountManager.KEYRING_SERVICE_NAME,
            "net.zombofant.mlxc",
        )

        self.assertEqual(
            client.AccountManager.KEYRING_JID_FORMAT,
            "jid:{bare!s}",
        )

    def test_default_init_keyring(self):
        manager = client.AccountManager(use_keyring=None)
        self.assertEqual(
            manager.keyring,
            keyring.get_keyring()
        )

    def test_default_init_loop(self):
        manager = client.AccountManager(loop=None)
        self.assertEqual(
            manager.loop,
            asyncio.get_event_loop()
        )

    def test_get_stored_password(self):
        obj = object()

        with contextlib.ExitStack() as stack:
            run_in_executor = stack.enter_context(
                unittest.mock.patch.object(self.loop, "run_in_executor")
            )

            run_in_executor.return_value = noop(obj)

            result = run_coroutine(self.manager.get_stored_password(
                TEST_JID))

        self.assertSequenceEqual(
            run_in_executor.mock_calls,
            [
                unittest.mock.call(
                    None,
                    keyring.get_password,
                    client.AccountManager.KEYRING_SERVICE_NAME,
                    "jid:{!s}".format(TEST_JID.bare)
                )
            ],
        )

        self.assertIs(obj, result)

    def test_get_stored_password_raises_if_keyring_is_not_secure(self):
        self.keyring.priority = 0.5

        with contextlib.ExitStack() as stack:
            run_in_executor = stack.enter_context(
                unittest.mock.patch.object(self.loop, "run_in_executor")
            )
            run_in_executor.return_value = noop()

            with self.assertRaises(client.PasswordStoreIsUnsafe):
                run_coroutine(self.manager.get_stored_password(
                    TEST_JID))

    def test_set_stored_password(self):
        with contextlib.ExitStack() as stack:
            run_in_executor = stack.enter_context(
                unittest.mock.patch.object(self.loop, "run_in_executor")
            )
            run_in_executor.return_value = noop()

            result = run_coroutine(self.manager.set_stored_password(
                TEST_JID,
                "foobar"
            ))

        self.assertSequenceEqual(
            run_in_executor.mock_calls,
            [
                unittest.mock.call(
                    None,
                    keyring.set_password,
                    client.AccountManager.KEYRING_SERVICE_NAME,
                    "jid:{!s}".format(TEST_JID.bare),
                    "foobar"
                )
            ]
        )

    def test_set_stored_password_raises_if_keyring_is_not_secure(self):
        self.keyring.priority = 0.5

        with contextlib.ExitStack() as stack:
            run_in_executor = stack.enter_context(
                unittest.mock.patch.object(self.loop, "run_in_executor")
            )
            run_in_executor.return_value = noop()

            with self.assertRaises(client.PasswordStoreIsUnsafe):
                run_coroutine(self.manager.set_stored_password(
                    TEST_JID,
                    "foobar"))

    def test_set_stored_password_to_None_deletes_password(self):
        with contextlib.ExitStack() as stack:
            run_in_executor = stack.enter_context(
                unittest.mock.patch.object(self.loop, "run_in_executor")
            )
            run_in_executor.return_value = noop()

            result = run_coroutine(self.manager.set_stored_password(
                TEST_JID,
                None
            ))

        self.assertSequenceEqual(
            run_in_executor.mock_calls,
            [
                unittest.mock.call(
                    None,
                    keyring.delete_password,
                    client.AccountManager.KEYRING_SERVICE_NAME,
                    "jid:{!s}".format(TEST_JID.bare),
                )
            ]
        )

    def test_deleting_password_ignores_exceptions(self):
        with contextlib.ExitStack() as stack:
            run_in_executor = stack.enter_context(
                unittest.mock.patch.object(self.loop, "run_in_executor")
            )
            run_in_executor.return_value = noop(
                raises=keyring.errors.PasswordDeleteError()
            )

            result = run_coroutine(self.manager.set_stored_password(
                TEST_JID,
                None
            ))

        self.assertSequenceEqual(
            run_in_executor.mock_calls,
            [
                unittest.mock.call(
                    None,
                    keyring.delete_password,
                    client.AccountManager.KEYRING_SERVICE_NAME,
                    "jid:{!s}".format(TEST_JID.bare),
                )
            ]
        )

    def tearDown(self):
        del self.manager
        del self.loop
