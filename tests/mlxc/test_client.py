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
import aioxmpp.stanza as stanza
import aioxmpp.structs as structs
import aioxmpp.xso as xso

import mlxc.client as client
import mlxc.utils
import mlxc.instrumentable_list as instrumentable_list

from aioxmpp.testutils import (
    run_coroutine,
    CoroutineMock,
    ConnectedClientMock
)

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
        self.assertIsNone(client.ConnectionOverride.host.default)

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
        self.assertEqual(
            client.ConnectionOverride.port.default,
            5222
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
        self.assertIs(
            client.AccountSettings._jid.default,
            xso.NO_DEFAULT
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
        self.assertIs(
            client.AccountSettings._enabled.default,
            False
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
        self.assertIs(
            client.AccountSettings.resource.default,
            None
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
        self.assertFalse(
            client.AccountSettings.override_peer.required
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

        settings = client.AccountSettings(
            TEST_JID,
            enabled=True)
        self.assertEqual(
            TEST_JID.bare(),
            settings.jid
        )
        self.assertEqual(
            TEST_JID.resource,
            settings.resource
        )
        self.assertTrue(settings.enabled)
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


class TestSinglePresenceState(unittest.TestCase):
    def test_is_xso(self):
        self.assertTrue(issubclass(
            client.SinglePresenceState,
            xso.XSO
        ))

    def test_tag(self):
        self.assertEqual(
            client.SinglePresenceState.TAG,
            (mlxc_namespaces.presence, "single-presence")
        )

    def test__available(self):
        self.assertIsInstance(
            client.SinglePresenceState._available,
            xso.Attr
        )
        self.assertEqual(
            client.SinglePresenceState._available.tag,
            (None, "available")
        )
        self.assertIsInstance(
            client.SinglePresenceState._available.type_,
            xso.Bool
        )
        self.assertIs(
            client.SinglePresenceState._available.default,
            True
        )

    def test__show_prop(self):
        self.assertIsInstance(
            client.SinglePresenceState._show,
            xso.Attr
        )
        self.assertEqual(
            client.SinglePresenceState._show.tag,
            (None, "show")
        )
        self.assertIs(
            client.SinglePresenceState._show.type_,
            stanza.Presence.show.type_
        )
        self.assertIsNone(
            client.SinglePresenceState._show.default
        )

    def test_status(self):
        self.assertIsInstance(
            client.SinglePresenceState.status,
            xso.ChildList
        )
        self.assertSetEqual(
            client.SinglePresenceState.status._classes,
            {stanza.Status}
        )

    def test_jid(self):
        self.assertIsInstance(
            client.SinglePresenceState.jid,
            xso.Attr
        )
        self.assertEqual(
            client.SinglePresenceState.jid.tag,
            (None, "jid")
        )
        self.assertIsInstance(
            client.SinglePresenceState.jid.type_,
            xso.JID
        )
        self.assertIs(
            client.SinglePresenceState.jid.default,
            xso.NO_DEFAULT
        )

    def test_init_default(self):
        aps = client.SinglePresenceState(TEST_JID)
        self.assertEqual(aps.jid, TEST_JID)
        self.assertFalse(aps.status)
        self.assertEqual(aps.state, structs.PresenceState(True))

    def test_init_args(self):
        aps = client.SinglePresenceState(
            TEST_JID,
            structs.PresenceState(available=True),
            "foobar")
        self.assertEqual(aps.jid, TEST_JID)
        self.assertEqual(
            aps.state,
            structs.PresenceState(available=True)
        )
        self.assertEqual(
            aps.status,
            [stanza.Status("foobar")]
        )

        aps = client.SinglePresenceState(
            TEST_JID,
            structs.PresenceState(available=True),
            [stanza.Status("foobar"),
             stanza.Status(
                 "baz",
                 lang=structs.LanguageTag.fromstr("de-DE"))]
        )
        self.assertEqual(
            aps.state,
            structs.PresenceState(available=True)
        )
        self.assertEqual(
            aps.status,
            [stanza.Status("foobar"),
             stanza.Status(
                 "baz",
                 lang=structs.LanguageTag.fromstr("de-DE"))
            ]
        )

    def test_state_attr(self):
        aps = client.SinglePresenceState(TEST_JID)
        aps.state = structs.PresenceState(available=True, show="dnd")
        self.assertEqual(
            aps.state,
            structs.PresenceState(available=True, show="dnd")
        )

        self.assertEqual(
            aps._available,
            True
        )
        self.assertEqual(
            aps._show,
            "dnd"
        )

    def test_equality(self):
        aps1 = client.SinglePresenceState(TEST_JID, status="foobar")
        aps2 = client.SinglePresenceState(TEST_JID)

        self.assertFalse(aps1 == aps2)
        self.assertTrue(aps1 != aps2)

        aps1.status.clear()

        self.assertTrue(aps1 == aps2)
        self.assertFalse(aps1 != aps2)

        aps1.state = structs.PresenceState()

        self.assertFalse(aps1 == aps2)
        self.assertTrue(aps1 != aps2)

        aps2.state = structs.PresenceState()

        self.assertTrue(aps1 == aps2)
        self.assertFalse(aps1 != aps2)

        aps1.jid = structs.JID.fromstr("foo@bar.example")

        self.assertTrue(aps1 == aps2)
        self.assertFalse(aps1 != aps2)

    def test_equality_deals_with_foreign_types(self):
        aps = client.SinglePresenceState(TEST_JID)
        self.assertNotEqual(aps, None)
        self.assertNotEqual(aps, "foo")
        self.assertNotEqual(aps, 123)

    def setUp(self):
        self.aps = client.SinglePresenceState(TEST_JID)

    def test_get_status_for_locale(self):
        range_ = object()
        with contextlib.ExitStack() as stack:
            filter_ = stack.enter_context(
                unittest.mock.patch.object(self.aps.status, "filter")
            )

            result = self.aps.get_status_for_locale(range_)

        self.assertSequenceEqual(
            filter_.mock_calls,
            [
                unittest.mock.call(lang=range_),
                unittest.mock.call().__next__()
            ]
        )

        self.assertEqual(result, next(filter_()))

    def test_get_status_for_locale_raise_KeyError_if_none_found(self):
        range_ = object()
        with contextlib.ExitStack() as stack:
            filter_ = stack.enter_context(
                unittest.mock.patch.object(self.aps.status, "filter")
            )

            filter_().__next__.side_effect = StopIteration()
            filter_.mock_calls.clear()

            with self.assertRaises(KeyError):
                self.aps.get_status_for_locale(range_)

        self.assertSequenceEqual(
            filter_.mock_calls,
            [
                unittest.mock.call(lang=range_),
                unittest.mock.call().__next__()
            ]
        )

    def test_get_status_for_locale_try_None(self):
        def filter_mock(original, *args, lang=None, **kwargs):
            result = original(*args, lang=lang, **kwargs)
            if lang is not None:
                result.__next__.side_effect = StopIteration()
            else:
                result.__next__.side_effect = None
            return result

        range_ = object()
        base = unittest.mock.MagicMock()
        with contextlib.ExitStack() as stack:
            stack.enter_context(unittest.mock.patch.object(
                self.aps.status, "filter",
                new=functools.partial(filter_mock, base.filter)
            ))

            result = self.aps.get_status_for_locale(range_, try_none=True)

        self.assertSequenceEqual(
            base.mock_calls,
            [
                unittest.mock.call.filter(lang=range_),
                unittest.mock.call.filter().__next__(),
                unittest.mock.call.filter(attrs={"lang": None}, lang=None),
                unittest.mock.call.filter().__next__()
            ]
        )

    def test_get_status_for_locale_try_None_raises_KeyError_on_failure(self):
        range_ = object()
        with contextlib.ExitStack() as stack:
            filter_ = stack.enter_context(
                unittest.mock.patch.object(self.aps.status, "filter")
            )

            filter_().__next__.side_effect = StopIteration()
            filter_.mock_calls.clear()

            with self.assertRaises(KeyError):
                self.aps.get_status_for_locale(range_, try_none=True)

        self.assertSequenceEqual(
            filter_.mock_calls,
            [
                unittest.mock.call(lang=range_),
                unittest.mock.call().__next__(),
                unittest.mock.call(attrs={"lang": None}),
                unittest.mock.call().__next__()
            ]
        )


class TestComplexPresenceState(unittest.TestCase):
    def test_is_xso(self):
        self.assertTrue(issubclass(
            client.ComplexPresenceState,
            xso.XSO
        ))

    def test__available(self):
        self.assertIsInstance(
            client.ComplexPresenceState._available,
            xso.Attr
        )
        self.assertEqual(
            client.ComplexPresenceState._available.tag,
            (None, "available")
        )
        self.assertIsInstance(
            client.ComplexPresenceState._available.type_,
            xso.Bool
        )
        self.assertIs(
            client.ComplexPresenceState._available.default,
            True
        )

    def test__show_prop(self):
        self.assertIsInstance(
            client.ComplexPresenceState._show,
            xso.Attr
        )
        self.assertEqual(
            client.ComplexPresenceState._show.tag,
            (None, "show")
        )
        self.assertIs(
            client.ComplexPresenceState._show.type_,
            stanza.Presence.show.type_
        )
        self.assertIsNone(client.ComplexPresenceState._show.default)

    def test_status(self):
        self.assertIsInstance(
            client.ComplexPresenceState.status,
            xso.ChildList
        )
        self.assertSetEqual(
            client.ComplexPresenceState.status._classes,
            {stanza.Status}
        )

    def test_tag(self):
        self.assertEqual(
            client.ComplexPresenceState.TAG,
            (mlxc_namespaces.presence, "complex-presence")
        )

    def test_name(self):
        self.assertIsInstance(
            client.ComplexPresenceState.name,
            xso.Attr
        )
        self.assertEqual(
            client.ComplexPresenceState.name.tag,
            (None, "name")
        )
        self.assertIs(
            client.ComplexPresenceState.name.default,
            xso.NO_DEFAULT
        )

    def test_overrides(self):
        self.assertIsInstance(
            client.ComplexPresenceState.overrides,
            xso.ChildList
        )
        self.assertSetEqual(
            client.ComplexPresenceState.overrides._classes,
            {client.SinglePresenceState}
        )

    def test_init_default(self):
        cps = client.ComplexPresenceState()
        self.assertEqual(
            cps.state,
            structs.PresenceState(available=True)
        )
        self.assertIs(
            cps._available,
            True
        )
        self.assertIsNone(cps._show)
        self.assertEqual(len(cps.status), 0)
        self.assertEqual(len(cps.overrides), 0)

    def test_init_args_status_list(self):
        status_list = [
            stanza.Status("foo"),
            stanza.Status("de", lang=structs.LanguageTag.fromstr("de-DE"))
        ]

        cps = client.ComplexPresenceState(
            state=structs.PresenceState(available=True,
                                        show="chat"),
            status=status_list
        )

        self.assertEqual(
            cps.state,
            structs.PresenceState(available=True, show="chat")
        )
        self.assertSequenceEqual(
            cps.status,
            status_list
        )
        self.assertEqual(
            cps._available,
            True
        )
        self.assertEqual(
            cps._show,
            "chat"
        )
        self.assertEqual(len(cps.overrides), 0)

    def setUp(self):
        self.cps = client.ComplexPresenceState()

    def test_state_property(self):
        self.cps.state = structs.PresenceState(available=True,
                                               show="dnd")
        self.assertTrue(self.cps._available)
        self.assertEqual(self.cps._show, "dnd")
        self.cps.state = structs.PresenceState(available=False)
        self.assertFalse(self.cps._available)
        self.assertIsNone(self.cps._show)

    def test_get_presence_for_jid_defaulting(self):
        self.cps.state = structs.PresenceState(available=True,
                                               show="dnd")
        self.cps.status[:] = [
            stanza.Status("foo")
        ]
        result = self.cps.get_presence_for_jid(TEST_JID)

        self.assertEqual(self.cps.state, result.state)
        self.assertEqual(self.cps.status, result.status)

    def test_get_presence_for_jid_with_override(self):
        foo_override = client.SinglePresenceState(
            TEST_JID.replace(localpart="foo"),
            structs.PresenceState(available=False)
        )
        bar_override = client.SinglePresenceState(
            TEST_JID.replace(localpart="bar"),
            structs.PresenceState(available=True,
                                  show="dnd")
        )

        self.cps.overrides.append(foo_override)
        self.cps.overrides.append(bar_override)

        self.assertIs(
            self.cps.get_presence_for_jid(TEST_JID.replace(localpart="foo")),
            foo_override
        )

    def test_get_status_for_locale(self):
        range_ = object()
        with contextlib.ExitStack() as stack:
            filter_ = stack.enter_context(
                unittest.mock.patch.object(self.cps.status, "filter")
            )

            result = self.cps.get_status_for_locale(range_)

        self.assertSequenceEqual(
            filter_.mock_calls,
            [
                unittest.mock.call(lang=range_),
                unittest.mock.call().__next__()
            ]
        )

        self.assertEqual(result, next(filter_()))

    def test_get_status_for_locale_raise_KeyError_if_none_found(self):
        range_ = object()
        with contextlib.ExitStack() as stack:
            filter_ = stack.enter_context(
                unittest.mock.patch.object(self.cps.status, "filter")
            )

            filter_().__next__.side_effect = StopIteration()
            filter_.mock_calls.clear()

            with self.assertRaises(KeyError):
                self.cps.get_status_for_locale(range_)

        self.assertSequenceEqual(
            filter_.mock_calls,
            [
                unittest.mock.call(lang=range_),
                unittest.mock.call().__next__()
            ]
        )

    def test_get_status_for_locale_try_None(self):
        def filter_mock(original, *args, lang=None, **kwargs):
            result = original(*args, lang=lang, **kwargs)
            if lang is not None:
                result.__next__.side_effect = StopIteration()
            else:
                result.__next__.side_effect = None
            return result

        range_ = object()
        base = unittest.mock.MagicMock()
        with contextlib.ExitStack() as stack:
            stack.enter_context(unittest.mock.patch.object(
                self.cps.status, "filter",
                new=functools.partial(filter_mock, base.filter)
            ))

            result = self.cps.get_status_for_locale(range_, try_none=True)

        self.assertSequenceEqual(
            base.mock_calls,
            [
                unittest.mock.call.filter(lang=range_),
                unittest.mock.call.filter().__next__(),
                unittest.mock.call.filter(attrs={"lang": None}, lang=None),
                unittest.mock.call.filter().__next__()
            ]
        )

    def test_get_status_for_locale_try_None_raises_KeyError_on_failure(self):
        range_ = object()
        with contextlib.ExitStack() as stack:
            filter_ = stack.enter_context(
                unittest.mock.patch.object(self.cps.status, "filter")
            )

            filter_().__next__.side_effect = StopIteration()
            filter_.mock_calls.clear()

            with self.assertRaises(KeyError):
                self.cps.get_status_for_locale(range_, try_none=True)

        self.assertSequenceEqual(
            filter_.mock_calls,
            [
                unittest.mock.call(lang=range_),
                unittest.mock.call().__next__(),
                unittest.mock.call(attrs={"lang": None}),
                unittest.mock.call().__next__()
            ]
        )


class TestFundamentalPresenceState(unittest.TestCase):
    def test_init_with_presence_state(self):
        state = structs.PresenceState(available=True, show="dnd")
        fps = client.FundamentalPresenceState(state)
        self.assertEqual(fps.state, state)

    def setUp(self):
        self.fps = client.FundamentalPresenceState()

    def test_get_status_for_locale_raises_KeyError(self):
        with self.assertRaises(KeyError):
            self.fps.get_status_for_locale(
                structs.LanguageRange.fromstr("de-de")
            )
        with self.assertRaises(KeyError):
            self.fps.get_status_for_locale(
                structs.LanguageRange.fromstr("de-de"),
                try_none=True
            )

    def test_get_presence_for_jid_returns_self(self):
        self.assertIs(self.fps.get_presence_for_jid(TEST_JID), self.fps)
        self.assertIs(
            self.fps.get_presence_for_jid(TEST_JID.replace(localpart="foo")),
            self.fps
        )

    def test_status_is_empty_iterable(self):
        self.assertEqual(self.fps.status, ())



class Test_ComplexPresenceList(unittest.TestCase):
    def test_is_xso(self):
        self.assertTrue(issubclass(
            client._ComplexPresenceList,
            xso.XSO
        ))


    def test_declare_namespace(self):
        self.assertDictEqual(
            client._ComplexPresenceList.DECLARE_NS,
            {
                None: mlxc_namespaces.presence
            }
        )

    def test_tag(self):
        self.assertEqual(
            client._ComplexPresenceList.TAG,
            (mlxc_namespaces.presence, "presences"),
        )

    def test_items_attr(self):
        self.assertIsInstance(
            client._ComplexPresenceList.items,
            xso.ChildList
        )
        self.assertSetEqual(
            client._ComplexPresenceList.items._classes,
            {
                client.ComplexPresenceState
            }
        )

    def test_init_with_list(self):
        items = [
            client.ComplexPresenceState(),
            client.ComplexPresenceState(),
        ]
        cpl = client._ComplexPresenceList(items)
        self.assertSequenceEqual(cpl.items, items)


class Test_AccountList(unittest.TestCase):
    def test_is_xso(self):
        self.assertTrue(issubclass(
            client._AccountList,
            xso.XSO
        ))

    def test_declare_namespace(self):
        self.assertDictEqual(
            client._AccountList.DECLARE_NS,
            {
                None: mlxc_namespaces.account
            }
        )

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

    def test_jidlist_is_model_list(self):
        self.assertIsInstance(
            self.manager._jidlist,
            instrumentable_list.ModelList
        )

    def test_keyring_info(self):
        self.assertEqual(
            client.AccountManager.KEYRING_SERVICE_NAME,
            "net.zombofant.mlxc",
        )

        self.assertEqual(
            client.AccountManager.KEYRING_JID_FORMAT,
            "xmpp:{bare!s}",
        )

    def test_keyring_with_priority_1_is_safe(self):
        self.assertTrue(self.manager.keyring_is_safe)

    def test_default_init_keyring(self):
        manager = client.AccountManager(use_keyring=None)
        self.assertEqual(
            manager.keyring,
            keyring.get_keyring()
        )

    def test_keyring_with_priority_less_than_one_is_unsafe(self):
        keyring = unittest.mock.Mock()
        keyring.priority = 0.9
        manager = client.AccountManager(use_keyring=keyring)
        self.assertFalse(
            manager.keyring_is_safe,
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
                    "xmpp:{!s}".format(TEST_JID.bare)
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
                    "xmpp:{!s}".format(TEST_JID.bare),
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
                    "xmpp:{!s}".format(TEST_JID.bare),
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
                    "xmpp:{!s}".format(TEST_JID.bare),
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

    def test_jid_account(self):
        jids = [
            TEST_JID.replace(localpart="foo"),
            TEST_JID.replace(localpart="bar"),
            TEST_JID.replace(localpart="baz"),
        ]

        accs = [
            self.manager.new_account(jid)
            for jid in jids
        ]

        for acc in accs:
            self.assertIs(
                self.manager.jid_account(acc.jid),
                acc
            )

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
                unittest.mock.call(acc)
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
                unittest.mock.call(acc, reason=None)
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
                unittest.mock.call(acc, reason=reason)
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
                unittest.mock.call(accs[1], reason=None),
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
                unittest.mock.call(accs[0], reason=None),
                unittest.mock.call(accs[2], reason=None),
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

    @unittest.mock.patch("mlxc.utils.write_xso")
    @unittest.mock.patch("mlxc.client._AccountList")
    def test_save(self, _AccountList, write_xso):
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

        self.manager.save(dest)

        self.assertSequenceEqual(
            _AccountList.mock_calls,
            [
                unittest.mock.call(),
                unittest.mock.call().items.extend(self.manager)
            ]
        )

        self.assertSequenceEqual(
            write_xso.mock_calls,
            [
                unittest.mock.call(dest, _AccountList()),
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

    def test__load_accounts_splits_jid(self):
        accounts = client._AccountList()

        acc1 = client.AccountSettings(TEST_JID)
        acc1._jid = TEST_JID.replace(resource="foo")
        del acc1.resource

        acc2 = client.AccountSettings(TEST_JID)
        acc2._jid = TEST_JID.replace(resource="bar")
        del acc2.resource

        accounts.items.extend([
            acc1, acc2
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

        self.assertEqual(len(self.manager), 1)

        self.assertEqual(
            self.manager[self.manager.jid_index(TEST_JID)].resource,
            "foo"
        )

    def test_emit_enabled_events_for_enabled_accounts(self):
        enabled_account = client.AccountSettings(
            TEST_JID.replace(localpart="foo"),
            enabled=True
        )

        accounts = client._AccountList()
        accounts.items.extend([
            client.AccountSettings(TEST_JID.replace(localpart="foo"),
                                   enabled=True),
            client.AccountSettings(TEST_JID.replace(localpart="bar")),
            client.AccountSettings(TEST_JID.replace(localpart="baz")),
            client.AccountSettings(TEST_JID.replace(localpart="fnord"),
                                   enabled=True),
        ])

        mock = unittest.mock.Mock()
        mock.return_value = False
        self.manager.on_account_enabled.connect(mock)

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

        self.assertSequenceEqual(
            mock.mock_calls,
            [
                unittest.mock.call(self.manager.jid_account(
                    TEST_JID.replace(localpart="foo").bare())
                ),
                unittest.mock.call(self.manager.jid_account(
                    TEST_JID.replace(localpart="fnord").bare())
                ),
            ]
        )

        self.assertEqual(len(self.manager), 4)

    @unittest.mock.patch("xml.sax.make_parser")
    @unittest.mock.patch("mlxc.utils.read_xso")
    def test_load(self, read_xso, make_parser):
        src = io.BytesIO()

        self.manager.load(src)

        self.assertSequenceEqual(
            read_xso.mock_calls,
            [
                unittest.mock.call(src, {
                    client._AccountList: self.manager._load_accounts
                }),
            ]
        )

    def test_password_provider_uses_stored_password_if_possible(self):
        password = object()

        self.manager.new_account(TEST_JID)

        with unittest.mock.patch.object(
                self.manager,
                "get_stored_password",
                new=CoroutineMock()) as get_stored_password:
            get_stored_password.return_value = password
            result = run_coroutine(
                self.manager.password_provider(TEST_JID, 0),
            )

        self.assertSequenceEqual(
            get_stored_password.mock_calls,
            [
                unittest.mock.call(TEST_JID.bare())
            ]
        )

        self.assertIs(
            result,
            password
        )

    def test_password_provider_raises_key_error_if_store_is_unsafe(self):
        self.manager.new_account(TEST_JID)

        with unittest.mock.patch.object(
                self.manager,
                "get_stored_password",
                new=CoroutineMock()) as get_stored_password:
            get_stored_password.side_effect = client.PasswordStoreIsUnsafe

            with self.assertRaises(KeyError):
                run_coroutine(
                    self.manager.password_provider(TEST_JID, 0),
                )

        self.assertSequenceEqual(
            get_stored_password.mock_calls,
            [
                unittest.mock.call(TEST_JID.bare())
            ]
        )

    def test_password_provider_raises_key_error_if_password_not_stored(self):
        self.manager.new_account(TEST_JID)

        with unittest.mock.patch.object(
                self.manager,
                "get_stored_password",
                new=CoroutineMock()) as get_stored_password:
            get_stored_password.return_value = None

            with self.assertRaises(KeyError):
                run_coroutine(
                    self.manager.password_provider(TEST_JID, 0),
                )

        self.assertSequenceEqual(
            get_stored_password.mock_calls,
            [
                unittest.mock.call(TEST_JID.bare())
            ]
        )

    def tearDown(self):
        del self.manager
        del self.loop


class TestClient(unittest.TestCase):
    def setUp(self):
        self.patches = [
            unittest.mock.patch(
                "aioxmpp.security_layer.tls_with_password_based_authentication"
            ),
            unittest.mock.patch("aioxmpp.node.PresenceManagedClient"),
        ]

        (self.tls_with_password_based_authentication,
         self.PresenceManagedClient) = [
             patch.start()
             for patch in self.patches
         ]

        self.PresenceManagedClient.return_value = ConnectedClientMock()
        self.config_manager = unittest.mock.Mock([
            "open_single",
            "open_multiple",
            "on_writeback",
        ])

        self.c = client.Client(self.config_manager)

        self.config_manager.mock_calls.clear()

    def test_init(self):
        with contextlib.ExitStack() as stack:
            AccountManager = stack.enter_context(
                unittest.mock.patch.object(
                    client.Client,
                    "AccountManager"
                )
            )

            c = client.Client(self.config_manager)

        self.assertSequenceEqual(
            AccountManager.mock_calls,
            [
                unittest.mock.call(),
                unittest.mock.call().on_account_enabled.connect(
                    c._on_account_enabled
                ),
                unittest.mock.call().on_account_disabled.connect(
                    c._on_account_disabled
                )
            ]
        )

        self.assertSequenceEqual(
            self.config_manager.mock_calls,
            [
                unittest.mock.call.on_writeback.connect(c.save_state),
            ]
        )

        self.assertEqual(
            c.accounts,
            AccountManager()
        )

        self.assertEqual(
            c.current_presence.state,
            structs.PresenceState()
        )
        self.assertIsInstance(c.current_presence,
                              client.FundamentalPresenceState)

    def test_enable_account_creates_state(self):
        self.c.apply_presence_state(client.FundamentalPresenceState(
            structs.PresenceState(True, "dnd")
        ))

        acc = self.c.accounts.new_account(TEST_JID)

        with unittest.mock.patch("functools.partial") as partial:
            self.c.accounts.set_account_enabled(TEST_JID, True)

        self.assertSequenceEqual(
            partial.mock_calls,
            [
                unittest.mock.call(self.c._make_certificate_verifier,
                                   acc)
            ]
        )

        self.assertSequenceEqual(
            self.tls_with_password_based_authentication.mock_calls,
            [
                unittest.mock.call(
                    self.c.accounts.password_provider,
                    certificate_verifier_factory=partial()
                )
            ]
        )

        self.assertSequenceEqual(
            self.PresenceManagedClient.mock_calls,
            [
                unittest.mock.call(
                    TEST_JID,
                    self.tls_with_password_based_authentication()
                ),
                unittest.mock.call().set_presence(
                    structs.PresenceState(True, "dnd"),
                    ()
                )
            ]
        )

        state = self.c.account_state(acc)
        self.assertEqual(
            state,
            self.PresenceManagedClient(),
        )

    def test_account_state_raises_KeyError_for_disabled_account(self):
        acc = self.c.accounts.new_account(TEST_JID)

        with self.assertRaises(KeyError):
            self.c.account_state(acc)

    def test_account_state_raises_KeyError_for_re_disabled_account(self):
        acc = self.c.accounts.new_account(TEST_JID)
        self.c.accounts.set_account_enabled(TEST_JID, True)
        self.c.accounts.set_account_enabled(TEST_JID, False)

        with self.assertRaises(KeyError):
            self.c.account_state(acc)

    def test_current_presence_cannot_be_set_directly(self):
        with self.assertRaises(AttributeError):
            self.c.current_presence = structs.PresenceState(False)

    def test_stop_all(self):
        jids = [
            TEST_JID.replace(localpart="foo"),
            TEST_JID.replace(localpart="bar"),
            TEST_JID.replace(localpart="baz"),
        ]

        accs = [
            self.c.accounts.new_account(jid)
            for jid in jids
        ]

        clients = []

        self.c.apply_presence_state(client.FundamentalPresenceState(
            structs.PresenceState(True))
        )

        for acc in accs:
            self.c.accounts.set_account_enabled(acc.jid, True)
            clients.append(self.PresenceManagedClient.return_value)
            self.PresenceManagedClient.return_value = ConnectedClientMock()

        self.c.stop_all()

        for client_ in clients:
            self.assertSequenceEqual(
                client_.mock_calls,
                [
                    unittest.mock.call.set_presence(
                        structs.PresenceState(True),
                        ()
                    ),
                    unittest.mock.call.stop()
                ]
            )

    def test_stop_and_wait_for_all(self):
        jids = [
            TEST_JID.replace(localpart="foo"),
            TEST_JID.replace(localpart="bar"),
            TEST_JID.replace(localpart="baz"),
        ]

        accs = [
            self.c.accounts.new_account(jid)
            for jid in jids
        ]

        self.c.apply_presence_state(client.FundamentalPresenceState(
            structs.PresenceState(True))
        )

        for acc in accs:
            self.c.accounts.set_account_enabled(acc.jid, True)
            self.PresenceManagedClient.return_value = ConnectedClientMock()

        states = [
            self.c.account_state(acc)
            for acc in accs
        ]

        for state in states:
            state.running = True

        self.PresenceManagedClient.reset_mock()

        task = asyncio.async(self.c.stop_and_wait_for_all())

        self.assertFalse(task.done())

        run_coroutine(asyncio.sleep(0))

        for state in states:
            self.assertSequenceEqual(
                [
                    unittest.mock.call.set_presence(
                        structs.PresenceState(True),
                        ()),
                    unittest.mock.call.stop(),
                ],
                state.mock_calls
            )

        self.assertFalse(task.done())

        states[0].on_stopped()

        run_coroutine(asyncio.sleep(0))

        self.assertFalse(task.done())

        states[1].on_failure(ConnectionError())

        run_coroutine(asyncio.sleep(0))

        self.assertFalse(task.done())

        states[2].on_failure(ValueError())

        run_coroutine(asyncio.sleep(0))

        self.assertTrue(task.done())
        self.assertIsNone(task.result())

    def test_stop_and_wait_for_all_ignores_not_running_clients(self):
        jids = [
            TEST_JID.replace(localpart="foo"),
            TEST_JID.replace(localpart="bar"),
            TEST_JID.replace(localpart="baz"),
        ]

        accs = [
            self.c.accounts.new_account(jid)
            for jid in jids
        ]

        self.c.apply_presence_state(client.FundamentalPresenceState(
            structs.PresenceState(True))
        )

        for acc in accs:
            self.c.accounts.set_account_enabled(acc.jid, True)
            self.PresenceManagedClient.return_value = ConnectedClientMock()

        states = [
            self.c.account_state(acc)
            for acc in accs
        ]
        states[1].presence = structs.PresenceState(False)

        for i, state in enumerate(states):
            state.running = (i != 1)

        self.PresenceManagedClient.reset_mock()

        task = asyncio.async(self.c.stop_and_wait_for_all())

        self.assertFalse(task.done())

        run_coroutine(asyncio.sleep(0))

        for i, state in enumerate(states):
            if i == 1:
                self.assertSequenceEqual(
                    [
                        unittest.mock.call.set_presence(
                            structs.PresenceState(True),
                            ()),
                    ],
                    state.mock_calls)
            else:
                self.assertSequenceEqual(
                    [
                        unittest.mock.call.set_presence(
                            structs.PresenceState(True),
                            ()),
                        unittest.mock.call.stop(),
                    ],
                    state.mock_calls
                )

        self.assertFalse(task.done())

        states[0].on_stopped()

        run_coroutine(asyncio.sleep(0))

        self.assertFalse(task.done())

        states[2].on_failure(ValueError())

        run_coroutine(asyncio.sleep(0))

        self.assertTrue(task.done())
        self.assertIsNone(task.result())

    def test__load_accounts(self):
        base = unittest.mock.MagicMock()

        with contextlib.ExitStack() as stack:
            self.config_manager.open_single = base.open_single
            open_single = base.open_single
            load = stack.enter_context(unittest.mock.patch.object(
                self.c.accounts,
                "load",
                new=base.load
            ))

            self.c._load_accounts()

        calls = list(base.mock_calls)

        self.assertSequenceEqual(
            calls,
            [
                unittest.mock.call.open_single(
                    mlxc.utils.mlxc_uid,
                    "accounts.xml"),
                unittest.mock.call.open_single().__enter__(),
                unittest.mock.call.load(open_single()),
                unittest.mock.call.open_single().__exit__(None, None, None),
            ]
        )

    def test__load_accounts_clears_accounts_on_open_errors(self):
        base = unittest.mock.MagicMock()

        with contextlib.ExitStack() as stack:
            self.config_manager.open_single = base.open_single
            open_single = base.open_single

            load = stack.enter_context(unittest.mock.patch.object(
                self.c.accounts,
                "load",
                new=base.load
            ))

            clear = stack.enter_context(unittest.mock.patch.object(
                self.c.accounts,
                "clear",
                new=base.clear
            ))

            open_single.side_effect = OSError()

            self.c._load_accounts()

        calls = list(base.mock_calls)
        self.assertSequenceEqual(
            calls,
            [
                unittest.mock.call.open_single(
                    mlxc.utils.mlxc_uid,
                    "accounts.xml"),
                unittest.mock.call.clear()
            ]
        )

    def test__load_pin_store(self):
        base = unittest.mock.MagicMock()

        with contextlib.ExitStack() as stack:
            self.config_manager.open_single = base.open_single
            open_single = base.open_single

            load = stack.enter_context(unittest.mock.patch(
                "json.load",
                new=base.json.load
            ))

            import_from_json = stack.enter_context(
                unittest.mock.patch.object(
                    self.c.pin_store,
                    "import_from_json",
                    new=base.import_from_json
                )
            )

            self.c._load_pin_store()

        calls = list(base.mock_calls)

        self.assertSequenceEqual(
            calls,
            [
                unittest.mock.call.open_single(
                    mlxc.utils.mlxc_uid,
                    "pinstore.json",
                    mode="r",
                    encoding="utf-8"),
                unittest.mock.call.open_single().__enter__(),
                unittest.mock.call.json.load(open_single().__enter__()),
                unittest.mock.call.open_single().__exit__(None, None, None),
                unittest.mock.call.import_from_json(
                    load(),
                    override=True),
            ]
        )

    def test__load_pin_store_loads_empty_dict_on_OSError(self):
        base = unittest.mock.MagicMock()

        with contextlib.ExitStack() as stack:
            self.config_manager.open_single = base.open_single
            open_single = base.open_single

            load = stack.enter_context(unittest.mock.patch(
                "json.load",
                new=base.json.load
            ))

            import_from_json = stack.enter_context(
                unittest.mock.patch.object(
                    self.c.pin_store,
                    "import_from_json",
                    new=base.import_from_json
                )
            )

            open_single.side_effect = OSError()

            self.c._load_pin_store()

        calls = list(base.mock_calls)

        self.assertSequenceEqual(
            calls,
            [
                unittest.mock.call.open_single(
                    mlxc.utils.mlxc_uid,
                    "pinstore.json",
                    mode="r",
                    encoding="utf-8"),
                unittest.mock.call.import_from_json(
                    {},
                    override=True),
            ]
        )

    def test__load_pin_store_loads_empty_dict_on_other_Exception_reraise(self):
        base = unittest.mock.MagicMock()

        with contextlib.ExitStack() as stack:
            self.config_manager.open_single = base.open_single
            open_single = base.open_single

            load = stack.enter_context(unittest.mock.patch(
                "json.load",
                new=base.json.load
            ))

            import_from_json = stack.enter_context(
                unittest.mock.patch.object(
                    self.c.pin_store,
                    "import_from_json",
                    new=base.import_from_json
                )
            )

            exc = Exception()
            load.side_effect = exc

            with self.assertRaises(Exception) as ctx:
                self.c._load_pin_store()

        self.assertIs(
            ctx.exception,
            exc
        )

        calls = list(base.mock_calls)

        self.assertSequenceEqual(
            calls,
            [
                unittest.mock.call.open_single(
                    mlxc.utils.mlxc_uid,
                    "pinstore.json",
                    mode="r",
                    encoding="utf-8"),
                unittest.mock.call.open_single().__enter__(),
                unittest.mock.call.json.load(
                    open_single().__enter__(),
                ),
                unittest.mock.call.open_single().__exit__(
                    unittest.mock.ANY,
                    unittest.mock.ANY,
                    unittest.mock.ANY),
                unittest.mock.call.import_from_json(
                    {},
                    override=True),
            ]
        )

    def test_presence_states(self):
        self.assertIsInstance(
            self.c.presence_states,
            instrumentable_list.ModelList
        )

    def test__import_presence_states(self):
        base = unittest.mock.MagicMock()

        with contextlib.ExitStack() as stack:
            self.config_manager.open_single = base.open_single
            open_single = base.open_single

            presence_states = stack.enter_context(unittest.mock.patch.object(
                self.c,
                "presence_states",
                new=base.presence_states
            ))

            self.c._import_presence_states(base.list_xso)

        calls = list(base.mock_calls)

        self.assertSequenceEqual(
            calls,
            [
                unittest.mock.call.presence_states.__setitem__(
                    slice(None), base.list_xso.items
                )
            ]
        )

    def test__load_presence_states(self):
        base = unittest.mock.MagicMock()

        with contextlib.ExitStack() as stack:
            self.config_manager.open_single = base.open_single
            open_single = base.open_single

            import_ = stack.enter_context(unittest.mock.patch.object(
                self.c,
                "_import_presence_states",
                new=base._import_presence_states
            ))

            read_xso = stack.enter_context(unittest.mock.patch(
                "mlxc.utils.read_xso",
                new=base.read_xso
            ))

            self.c._load_presence_states()

        calls = list(base.mock_calls)

        self.assertSequenceEqual(
            calls,
            [
                unittest.mock.call.open_single(
                    mlxc.utils.mlxc_uid,
                    "presence.xml"),
                unittest.mock.call.open_single().__enter__(),
                unittest.mock.call.read_xso(open_single(), {
                    client._ComplexPresenceList: import_
                }),
                unittest.mock.call.open_single().__exit__(None, None, None),
            ]
        )

    def test__load_presence_states_clears_on_open_error(self):
        base = unittest.mock.MagicMock()

        with contextlib.ExitStack() as stack:
            self.config_manager.open_single = base.open_single
            open_single = base.open_single

            import_ = stack.enter_context(unittest.mock.patch.object(
                self.c,
                "_import_presence_states",
                new=base._import_presence_states
            ))

            presence_states = stack.enter_context(unittest.mock.patch.object(
                self.c,
                "presence_states",
                new=base.presence_states
            ))

            read_xso = stack.enter_context(unittest.mock.patch(
                "mlxc.utils.read_xso",
                new=base.read_xso
            ))

            open_single.side_effect = OSError()

            self.c._load_presence_states()

        calls = list(base.mock_calls)

        self.assertSequenceEqual(
            calls,
            [
                unittest.mock.call.open_single(
                    mlxc.utils.mlxc_uid,
                    "presence.xml"),
                unittest.mock.call.presence_states.clear()
            ]
        )

    def test_load_state_ignores_exceptions(self):
        funcs = [
            "_load_accounts",
            "_load_pin_store",
            "_load_presence_states",
        ]

        for func_to_fail_name in funcs:
            with contextlib.ExitStack() as stack:
                funcs_to_pass = []
                for func_to_pass_name in funcs:
                    if func_to_pass_name == func_to_fail_name:
                        continue
                    funcs_to_pass.append((
                        func_to_pass_name,
                        stack.enter_context(unittest.mock.patch.object(
                            self.c,
                            func_to_pass_name
                        ))
                    ))

                func_to_fail = stack.enter_context(
                    unittest.mock.patch.object(
                        self.c,
                        func_to_fail_name
                    )
                )

                func_to_fail.side_effect = Exception()

                self.c.load_state()

                for name, func in funcs_to_pass:
                    self.assertSequenceEqual(
                        func.mock_calls,
                        [
                            unittest.mock.call(),
                        ],
                        "function {} when {} fails".format(
                            name,
                            func_to_fail_name)
                    )

                self.assertSequenceEqual(
                    func_to_fail.mock_calls,
                    [
                        unittest.mock.call()
                    ],
                    "function {} when it is supposed to fail".format(
                        func_to_fail_name
                    )
                )

    def test_save_state(self):
        base = unittest.mock.MagicMock()

        with contextlib.ExitStack() as stack:
            self.config_manager.open_single = base.open_single
            open_single = base.open_single

            save = stack.enter_context(unittest.mock.patch.object(
                self.c.accounts,
                "save",
                new=base.save
            ))

            write_xso = stack.enter_context(unittest.mock.patch(
                "mlxc.utils.write_xso",
                new=base.write_xso
            ))

            _ComplexPresenceList = stack.enter_context(unittest.mock.patch(
                "mlxc.client._ComplexPresenceList",
                new=base._ComplexPresenceList
            ))

            json_dump = stack.enter_context(unittest.mock.patch(
                "json.dump",
                new=base.json.dump
            ))

            export_to_json = stack.enter_context(unittest.mock.patch.object(
                self.c.pin_store,
                "export_to_json",
                new=base.export_to_json
            ))

            self.c.save_state()

        calls = list(base.mock_calls)

        self.assertSequenceEqual(
            calls,
            [
                unittest.mock.call.open_single(
                    mlxc.utils.mlxc_uid,
                    "accounts.xml",
                    mode="wb"),
                unittest.mock.call.open_single().__enter__(),
                unittest.mock.call.save(
                    open_single().__enter__()
                ),
                unittest.mock.call.open_single().__exit__(None, None, None),
                unittest.mock.call.export_to_json(),
                unittest.mock.call.open_single(
                    mlxc.utils.mlxc_uid,
                    "pinstore.json",
                    mode="w",
                    encoding="utf-8"),
                unittest.mock.call.open_single().__enter__(),
                unittest.mock.call.json.dump(
                    export_to_json(),
                    open_single().__enter__()
                ),
                unittest.mock.call.open_single().__exit__(None, None, None),
                unittest.mock.call._ComplexPresenceList(self.c.presence_states),
                unittest.mock.call.open_single(
                    mlxc.utils.mlxc_uid,
                    "presence.xml",
                    mode="wb"),
                unittest.mock.call.open_single().__enter__(),
                unittest.mock.call.write_xso(
                    open_single().__enter__(),
                    _ComplexPresenceList(),
                ),
                unittest.mock.call.open_single().__exit__(None, None, None),
            ]
        )

    def test_pin_store(self):
        self.assertIsInstance(
            self.c.pin_store,
            aioxmpp.security_layer.PublicKeyPinStore
        )

    def test__decide_on_certificate_returns_None(self):
        account = object()

        self.assertIs(
            run_coroutine(self.c._decide_on_certificate(account, None)),
            False
        )

        verifier = self.c._make_certificate_verifier(account)
        self.assertIs(
            run_coroutine(self.c._decide_on_certificate(account, verifier)),
            False
        )

    def test__make_certificate_verifier_creates_pinning_pkix_verifier(self):
        base = unittest.mock.Mock()
        account = object()

        with contextlib.ExitStack() as stack:
            PinningPKIXCertificateVerifier = stack.enter_context(
                unittest.mock.patch(
                    "aioxmpp.security_layer.PinningPKIXCertificateVerifier",
                    new=base.PinningPKIXCertificateVerifier
                )
            )
            partial = stack.enter_context(unittest.mock.patch(
                "functools.partial",
                new=base.partial
            ))

            verifier = self.c._make_certificate_verifier(account)

        calls = list(base.mock_calls)
        self.assertSequenceEqual(
            calls,
            [
                unittest.mock.call.partial(self.c._decide_on_certificate,
                                           account),
                unittest.mock.call.PinningPKIXCertificateVerifier(
                    self.c.pin_store.query,
                    partial()),
            ]
        )

    def test_apply_presence_state(self):
        jids = [
            TEST_JID.replace(localpart="foo"),
            TEST_JID.replace(localpart="bar"),
            TEST_JID.replace(localpart="baz"),
        ]

        accs = [
            self.c.accounts.new_account(jid)
            for jid in jids
        ]

        for acc in accs:
            self.c.accounts.set_account_enabled(acc.jid, True)
            self.PresenceManagedClient.return_value = ConnectedClientMock()

        states = [
            self.c.account_state(acc)
            for acc in accs
        ]

        pres = client.ComplexPresenceState(
            state=structs.PresenceState(available=True, show="chat"),
            status=[
                stanza.Status(
                    text="I feel chatty!",
                    lang=structs.LanguageTag.fromstr("en")
                ),
                stanza.Status(
                    text="Ich will chatten!",
                    lang=structs.LanguageTag.fromstr("de")
                ),
            ]
        )
        pres.overrides.append(client.SinglePresenceState(
            jids[1],
            structs.PresenceState(available=False)
        ))
        pres.overrides.append(client.SinglePresenceState(
            jids[2],
            structs.PresenceState(available=True, show="dnd")
        ))

        self.c.apply_presence_state(pres)

        for acc, state in zip(accs, states):
            single_presence = pres.get_presence_for_jid(acc.jid)
            state.set_presence.assert_called_with(
                single_presence.state,
                single_presence.status
            )

    def tearDown(self):
        del self.c

        for patch in self.patches:
            patch.stop()

# foo
