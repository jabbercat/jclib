import asyncio
import contextlib
import functools
import io
import unittest
import unittest.mock
import xml.sax.handler

import keyring

import aioxmpp.stringprep

import aioxmpp.callbacks as callbacks
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

    def test__jid_attr(self):
        self.assertIsInstance(
            client.AccountSettings._jid,
            xso.Attr
        )
        self.assertEqual(
            client.AccountSettings._jid.tag,
            (None, "jid"),
        )
        self.assertIsInstance(
            client.AccountSettings._jid.type_,
            xso.JID
        )
        self.assertTrue(
            client.AccountSettings._jid.required
        )

    def test__enabled_attr(self):
        self.assertIsInstance(
            client.AccountSettings._enabled,
            xso.Attr
        )
        self.assertEqual(
            (None, "enabled"),
            client.AccountSettings._enabled.tag
        )
        self.assertIsInstance(
            client.AccountSettings._enabled.type_,
            xso.Bool
        )
        self.assertFalse(
            client.AccountSettings._enabled.required
        )
        self.assertIs(
            False,
            client.AccountSettings._enabled.default
        )

    def test_resource_attr(self):
        self.assertIsInstance(
            client.AccountSettings.resource,
            xso.Attr
        )
        self.assertEqual(
            client.AccountSettings.resource.tag,
            (None, "resource"),
        )
        self.assertIsInstance(
            client.AccountSettings.resource.type_,
            xso.String
        )
        self.assertEqual(
            client.AccountSettings.resource.type_.prepfunc,
            aioxmpp.stringprep.resourceprep
        )
        self.assertFalse(
            client.AccountSettings.resource.required
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

    def test_init_requires_jid(self):
        with self.assertRaisesRegex(TypeError,
                                    "missing.* argument.* 'jid'"):
            client.AccountSettings()

    def test_init(self):
        settings = client.AccountSettings(TEST_JID)
        self.assertEqual(
            TEST_JID.bare(),
            settings.jid
        )
        self.assertEqual(
            TEST_JID.resource,
            settings.resource
        )
        self.assertFalse(settings.enabled)
        self.assertIsNone(settings.override_peer)
        self.assertFalse(settings.allow_unencrypted)

    def test_jid_attr(self):
        settings = client.AccountSettings(TEST_JID)
        self.assertIs(
            settings.jid,
            settings._jid
        )

    def test_enabled_attr(self):
        settings = client.AccountSettings(TEST_JID)
        self.assertIs(
            settings.enabled,
            settings._enabled
        )


class Test_AccountList(unittest.TestCase):
    def test_is_xso(self):
        self.assertTrue(issubclass(
            client._AccountList,
            xso.XSO
        ))

    def test_tag(self):
        self.assertEqual(
            client._AccountList.TAG,
            (mlxc_namespaces.account, "accounts"),
        )

    def test_items_attr(self):
        self.assertIsInstance(
            client._AccountList.items,
            xso.ChildList
        )
        self.assertSetEqual(
            client._AccountList.items._classes,
            {
                client.AccountSettings
            }
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

    def test_signal_attributes(self):
        self.assertIsInstance(
            client.AccountManager.on_account_enabled,
            callbacks.Signal
        )

        self.assertIsInstance(
            client.AccountManager.on_account_disabled,
            callbacks.Signal
        )

        self.assertIsInstance(
            client.AccountManager.on_account_refresh,
            callbacks.Signal
        )

    def test_new_account(self):
        acc = self.manager.new_account(TEST_JID)
        self.assertIsInstance(
            acc,
            client.AccountSettings
        )
        self.assertEqual(
            acc.jid,
            TEST_JID.bare()
        )
        self.assertEqual(
            acc.resource,
            TEST_JID.resource
        )

    def test_new_account_rejects_duplicate_bare_jid(self):
        self.manager.new_account(TEST_JID)
        with self.assertRaisesRegex(ValueError,
                                    "duplicate jid"):
            self.manager.new_account(TEST_JID.replace(
                resource=TEST_JID.resource + "dupe"
            ))

    def test_iterate_over_existing_accounts(self):
        jids = [
            TEST_JID.replace(localpart="foo"),
            TEST_JID.replace(localpart="bar"),
            TEST_JID.replace(localpart="baz"),
        ]

        accs = [
            self.manager.new_account(jid)
            for jid in jids
        ]

        self.assertSequenceEqual(
            list(self.manager),
            accs
        )

    def test_length(self):
        jids = [
            TEST_JID.replace(localpart="foo"),
            TEST_JID.replace(localpart="bar"),
            TEST_JID.replace(localpart="baz"),
        ]

        for i, jid in enumerate(jids):
            self.assertEqual(len(self.manager), i)
            self.manager.new_account(jid)

        self.assertEqual(len(self.manager), len(jids))

    def test_delitem_single(self):
        jids = [
            TEST_JID.replace(localpart="foo"),
            TEST_JID.replace(localpart="bar"),
            TEST_JID.replace(localpart="baz"),
        ]

        accs = [
            self.manager.new_account(jid)
            for jid in jids
        ]

        del self.manager[1]

        self.assertSequenceEqual(
            list(self.manager),
            accs[:1] + accs[2:]
        )

        new_acc = self.manager.new_account(jids[1])

        self.assertSequenceEqual(
            list(self.manager),
            accs[:1] + accs[2:] + [new_acc]
        )

    def test_delitem_slice(self):
        jids = [
            TEST_JID.replace(localpart="foo"),
            TEST_JID.replace(localpart="bar"),
            TEST_JID.replace(localpart="baz"),
        ]

        accs = [
            self.manager.new_account(jid)
            for jid in jids
        ]

        del self.manager[1:]

        self.assertSequenceEqual(
            list(self.manager),
            accs[:1]
        )

        new_acc = self.manager.new_account(jids[1])

        self.assertSequenceEqual(
            list(self.manager),
            accs[:1] + [new_acc]
        )

    def test_getitem_single(self):
        jids = [
            TEST_JID.replace(localpart="foo"),
            TEST_JID.replace(localpart="bar"),
            TEST_JID.replace(localpart="baz"),
        ]

        accs = [
            self.manager.new_account(jid)
            for jid in jids
        ]

        for i in range(3):
            self.assertIs(
                accs[i],
                self.manager[i]
            )

        with self.assertRaises(IndexError):
            self.manager[3]

    def test_getitem_slice(self):
        jids = [
            TEST_JID.replace(localpart="foo"),
            TEST_JID.replace(localpart="bar"),
            TEST_JID.replace(localpart="baz"),
        ]

        accs = [
            self.manager.new_account(jid)
            for jid in jids
        ]

        self.assertSequenceEqual(
            accs[1:],
            self.manager[1:]
        )

        self.assertSequenceEqual(
            accs[1:2],
            self.manager[1:2]
        )

    def test_jid_index(self):
        jids = [
            TEST_JID.replace(localpart="foo"),
            TEST_JID.replace(localpart="bar"),
            TEST_JID.replace(localpart="baz"),
        ]

        accs = [
            self.manager.new_account(jid)
            for jid in jids
        ]

        self.assertEqual(
            self.manager.jid_index(jids[0]),
            0
        )

        self.assertEqual(
            self.manager.jid_index(jids[1]),
            1
        )

        self.assertEqual(
            self.manager.jid_index(jids[2]),
            2
        )

        with self.assertRaises(ValueError):
            self.manager.jid_index(TEST_JID.replace(localpart="fnord"))

    def test_account_index(self):
        jids = [
            TEST_JID.replace(localpart="foo"),
            TEST_JID.replace(localpart="bar"),
            TEST_JID.replace(localpart="baz"),
        ]

        accs = [
            self.manager.new_account(jid)
            for jid in jids
        ]

        self.assertEqual(
            self.manager.account_index(accs[0]),
            0
        )

        self.assertEqual(
            self.manager.account_index(accs[1]),
            1
        )

        self.assertEqual(
            self.manager.account_index(accs[2]),
            2
        )

        obj = "foo"
        with self.assertRaisesRegex(ValueError,
                                    r"'foo' not in list"):
            self.manager.account_index(obj)

    def test_set_account_enabled_set_to_enabled(self):
        acc = self.manager.new_account(TEST_JID)
        self.manager.set_account_enabled(TEST_JID, True)
        self.assertTrue(acc.enabled)

    def test_enabling_account_fires_event_only_if_not_enabled(self):
        mock = unittest.mock.Mock()
        mock.return_value = False

        self.manager.on_account_enabled.connect(mock)

        acc = self.manager.new_account(TEST_JID)
        self.manager.set_account_enabled(TEST_JID, True)
        self.manager.set_account_enabled(TEST_JID, True)

        self.assertSequenceEqual(
            mock.mock_calls,
            [
                unittest.mock.call(TEST_JID.bare())
            ]
        )

    def test_set_account_enabled_set_to_disabled(self):
        acc = self.manager.new_account(TEST_JID)
        self.manager.set_account_enabled(TEST_JID, True)
        self.assertTrue(acc.enabled)
        self.manager.set_account_enabled(TEST_JID, False)
        self.assertFalse(acc.enabled)

    def test_disabling_account_fires_event_only_if_not_disabled(self):
        mock = unittest.mock.Mock()
        mock.return_value = False

        self.manager.on_account_disabled.connect(mock)

        acc = self.manager.new_account(TEST_JID)
        self.manager.set_account_enabled(TEST_JID, False)
        self.manager.set_account_enabled(TEST_JID, True)
        self.manager.set_account_enabled(TEST_JID, False)
        self.manager.set_account_enabled(TEST_JID, False)

        self.assertSequenceEqual(
            mock.mock_calls,
            [
                unittest.mock.call(TEST_JID.bare(), reason=None)
            ]
        )

    def test_disable_account_with_reason(self):
        mock = unittest.mock.Mock()
        mock.return_value = False

        reason = object()

        self.manager.on_account_disabled.connect(mock)

        acc = self.manager.new_account(TEST_JID)
        self.manager.set_account_enabled(TEST_JID, True)
        self.assertTrue(acc.enabled)
        self.manager.set_account_enabled(TEST_JID, False, reason=reason)
        self.assertFalse(acc.enabled)

        self.assertSequenceEqual(
            mock.mock_calls,
            [
                unittest.mock.call(TEST_JID.bare(), reason=reason)
            ]
        )

    def test_refresh_account_fires_event(self):
        mock = unittest.mock.Mock()
        mock.return_value = False

        self.manager.on_account_refresh.connect(mock)

        acc = self.manager.new_account(TEST_JID)
        self.manager.refresh_account(TEST_JID)
        self.manager.refresh_account(TEST_JID)

        self.assertSequenceEqual(
            [
                unittest.mock.call(acc),
                unittest.mock.call(acc),
            ],
            mock.mock_calls
        )

    def test_delitem_single_disables_account_before_removal(self):
        jids = [
            TEST_JID.replace(localpart="foo"),
            TEST_JID.replace(localpart="bar"),
            TEST_JID.replace(localpart="baz"),
        ]

        accs = [
            self.manager.new_account(jid)
            for jid in jids
        ]

        self.manager.set_account_enabled(jids[1], True)

        mock = unittest.mock.Mock()
        mock.return_value = False
        self.manager.on_account_disabled.connect(mock)

        del self.manager[1]
        del self.manager[1]

        self.assertSequenceEqual(
            [
                unittest.mock.call(jids[1].bare(), reason=None),
            ],
            mock.mock_calls
        )

    def test_delitem_slice_disables_accounts_before_removal(self):
        jids = [
            TEST_JID.replace(localpart="foo"),
            TEST_JID.replace(localpart="bar"),
            TEST_JID.replace(localpart="baz"),
        ]

        accs = [
            self.manager.new_account(jid)
            for jid in jids
        ]

        self.manager.set_account_enabled(jids[0], True)
        self.manager.set_account_enabled(jids[2], True)

        mock = unittest.mock.Mock()
        mock.return_value = False
        self.manager.on_account_disabled.connect(mock)

        del self.manager[:]

        self.assertSequenceEqual(
            [
                unittest.mock.call(jids[0].bare(), reason=None),
                unittest.mock.call(jids[2].bare(), reason=None),
            ],
            mock.mock_calls
        )

    def test_clear_uses_delitem(self):
        with unittest.mock.patch.object(
                client.AccountManager,
                "__delitem__") as delitem:
            self.manager.clear()

        self.assertSequenceEqual(
            [
                unittest.mock.call(slice(None, None, None))
            ],
            delitem.mock_calls
        )

    def test_remove_jid(self):
        jids = [
            TEST_JID.replace(localpart="foo"),
            TEST_JID.replace(localpart="bar"),
            TEST_JID.replace(localpart="baz"),
        ]

        accs = [
            self.manager.new_account(jid)
            for jid in jids
        ]

        self.manager.remove_jid(jids[1])

        self.assertSequenceEqual(
            list(self.manager),
            accs[:1] + accs[2:]
        )

    def test_remove_account(self):
        jids = [
            TEST_JID.replace(localpart="foo"),
            TEST_JID.replace(localpart="bar"),
            TEST_JID.replace(localpart="baz"),
        ]

        accs = [
            self.manager.new_account(jid)
            for jid in jids
        ]

        self.manager.remove_account(accs[1])

        self.assertSequenceEqual(
            list(self.manager),
            accs[:1] + accs[2:]
        )

    @unittest.mock.patch("aioxmpp.xml.XMPPXMLGenerator")
    @unittest.mock.patch("mlxc.client._AccountList")
    def test_save(self, _AccountList, XMPPXMLGenerator):
        jids = [
            TEST_JID.replace(localpart="foo"),
            TEST_JID.replace(localpart="bar"),
            TEST_JID.replace(localpart="baz"),
        ]

        accs = [
            self.manager.new_account(jid)
            for jid in jids
        ]

        dest = io.BytesIO()

        def callthrough(writer):
            writer.__write_object()

        _AccountList().unparse_to_sax = callthrough
        _AccountList.mock_calls.clear()

        self.manager.save(dest)

        self.assertSequenceEqual(
            _AccountList.mock_calls,
            [
                unittest.mock.call(),
                unittest.mock.call().items.extend(self.manager)
            ]
        )

        self.assertSequenceEqual(
            XMPPXMLGenerator.mock_calls,
            [
                unittest.mock.call(out=dest,
                                   short_empty_elements=True),
                unittest.mock.call().startDocument(),
                unittest.mock.call().startElementNS(
                    (mlxc_namespaces.account, "accounts"),
                    None,
                    {}
                ),
                unittest.mock.call().__write_object(),
                unittest.mock.call().endElementNS(
                    (mlxc_namespaces.account, "accounts"),
                    None
                ),
                unittest.mock.call().endDocument(),
                unittest.mock.call().flush()
            ]
        )

    def test__load_accounts(self):
        accounts = client._AccountList()

        with unittest.mock.patch.object(
                self.manager,
                "clear") as clear:
            self.manager._load_accounts(accounts)

        self.assertSequenceEqual(
            clear.mock_calls,
            [
                unittest.mock.call()
            ]
        )

        self.assertEqual(len(self.manager), 0)

    def test__load_accounts_skip_over_duplicate_jids(self):
        accounts = client._AccountList()
        accounts.items.extend([
            client.AccountSettings(TEST_JID.replace(resource="foo")),
            client.AccountSettings(TEST_JID.replace(resource="bar")),
            client.AccountSettings(TEST_JID.replace(domain="other.example")),
        ])

        with unittest.mock.patch.object(
                self.manager,
                "clear") as clear:
            self.manager._load_accounts(accounts)

        self.assertSequenceEqual(
            clear.mock_calls,
            [
                unittest.mock.call()
            ]
        )

        self.assertEqual(len(self.manager), 2)

        self.assertEqual(
            self.manager[self.manager.jid_index(TEST_JID)].resource,
            "foo"
        )

    @unittest.mock.patch("xml.sax.parse")
    @unittest.mock.patch("aioxmpp.xso.SAXDriver")
    @unittest.mock.patch("aioxmpp.xso.XSOParser")
    def test_load(self, XSOParser, SAXDriver, parse):
        src = io.BytesIO()

        self.manager.load(src)

        self.assertSequenceEqual(
            XSOParser.mock_calls,
            [
                unittest.mock.call(),
                unittest.mock.call().add_class(
                    client._AccountList,
                    self.manager._load_accounts
                )
            ]
        )

        self.assertSequenceEqual(
            SAXDriver.mock_calls,
            [
                unittest.mock.call(XSOParser()),
            ]
        )

        self.assertSequenceEqual(
            parse.mock_calls,
            [
                unittest.mock.call(src, SAXDriver())
            ]
        )

    def tearDown(self):
        del self.manager
        del self.loop
