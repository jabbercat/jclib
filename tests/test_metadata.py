import asyncio
import collections.abc
import contextlib
import unittest
import unittest.mock

import aioxmpp
import aioxmpp.callbacks
import aioxmpp.service

from aioxmpp.testutils import (
    CoroutineMock,
    run_coroutine,
    make_listener,
)

import jclib.client

import jclib.metadata as metadata


def make_provider_mock(published_keys=[]):
    p = unittest.mock.Mock(spec=metadata.AbstractMetadataProvider)
    p.fetch = CoroutineMock()
    p.published_keys = set(published_keys)
    return p


class TestServiceMetadataProvider(unittest.TestCase):
    def setUp(self):
        self.svc_cls = unittest.mock.Mock(
            spec=metadata.AbstractMetadataProviderService
        )
        self.svc_cls.PUBLISHED_KEYS = ["k1", "k2"]
        self.svc_instance = unittest.mock.Mock(
            spec=metadata.AbstractMetadataProviderService
        )
        self.svc_instance.fetch = CoroutineMock()
        self.svc_cls.return_value = self.svc_instance
        self.client = unittest.mock.Mock(spec=jclib.client.Client)
        self.smp = metadata.ServiceMetadataProvider(
            self.svc_cls,
            self.client,
        )
        self.listener = make_listener(self.smp)

    def tearDown(self):
        del self.svc_cls, self.client, self.smp

    def test_constructor_connects_to_signals(self):
        self.client.on_client_prepare.connect.assert_called_once_with(
            self.smp._on_client_prepare,
        )
        self.client.on_client_stopped.connect.assert_called_once_with(
            self.smp._on_client_stopped,
        )

    def test__on_client_prepare_summons_service_and_connects_signals(self):
        client = unittest.mock.Mock(spec=aioxmpp.Client)
        client.summon.return_value = self.svc_instance
        account = unittest.mock.sentinel.account

        self.smp._on_client_prepare(
            account,
            client,
        )

        client.summon.assert_called_once_with(self.svc_cls)

        self.svc_instance.on_changed.connect.assert_called_once_with(
            unittest.mock.ANY,
        )

        _, (cb, ), _ = self.svc_instance.on_changed.connect.mock_calls[-1]

        self.listener.on_changed.assert_not_called()

        cb(
            unittest.mock.sentinel.key,
            unittest.mock.sentinel.arg1,
            unittest.mock.sentinel.arg2,
        )

        self.listener.on_changed.assert_called_once_with(
            unittest.mock.sentinel.key,
            unittest.mock.sentinel.account,
            unittest.mock.sentinel.arg1,
            unittest.mock.sentinel.arg2,
        )

    def test__on_client_stopped_disconnects_signals(self):
        client = unittest.mock.Mock(spec=aioxmpp.Client)
        client.summon.return_value = self.svc_instance
        account = unittest.mock.sentinel.account

        self.smp._on_client_prepare(
            account,
            client,
        )

        self.svc_instance.on_changed.disconnect.assert_not_called()

        self.smp._on_client_stopped(
            account,
            client,
        )

        self.svc_instance.on_changed.disconnect.assert_called_once_with(
            self.svc_instance.on_changed.connect(),
        )

    def test_publishes_published_keys_as_tuple(self):
        self.assertSequenceEqual(
            self.smp.published_keys,
            ("k1", "k2")
        )

        self.assertIsInstance(
            self.smp.published_keys,
            collections.abc.Sequence,
        )

        self.assertFalse(
            isinstance(self.smp.published_keys, collections.abc.MutableSequence)
        )

    def test__get_service_raises_key_error_for_unknown_account(self):
        with self.assertRaises(KeyError):
            self.smp._get_service(unittest.mock.sentinel.account)

    def test__get_service_returns_correct_service(self):
        client = unittest.mock.Mock(spec=aioxmpp.Client)
        client.summon.return_value = self.svc_instance
        account = unittest.mock.sentinel.account

        self.smp._on_client_prepare(
            account,
            client,
        )

        self.assertIs(
            self.smp._get_service(unittest.mock.sentinel.account),
            self.svc_instance
        )

    def test__get_service_raises_key_error_for_disconnected_account(self):
        client = unittest.mock.Mock(spec=aioxmpp.Client)
        client.summon.return_value = self.svc_instance
        account = unittest.mock.sentinel.account

        self.smp._on_client_prepare(
            account,
            client,
        )

        self.smp._on_client_stopped(account, client)

        with self.assertRaises(KeyError):
            self.smp._get_service(unittest.mock.sentinel.account)

    def test_fetch_propagates_key_error_from__get_service(self):
        with contextlib.ExitStack() as stack:
            _get_service = stack.enter_context(unittest.mock.patch.object(
                self.smp,
                "_get_service",
            ))
            _get_service.side_effect = KeyError

            stack.enter_context(self.assertRaises(KeyError))

            run_coroutine(self.smp.fetch(
                unittest.mock.sentinel.key,
                unittest.mock.sentinel.account,
                unittest.mock.sentinel.peer,
            ))

        _get_service.assert_called_once_with(unittest.mock.sentinel.account)

    def test_fetch_uses__get_service_to_obtain_service(self):
        with contextlib.ExitStack() as stack:
            _get_service = stack.enter_context(unittest.mock.patch.object(
                self.smp,
                "_get_service",
            ))
            _get_service.return_value = self.svc_instance
            self.svc_instance.fetch.return_value = \
                unittest.mock.sentinel.r

            result = run_coroutine(
                self.smp.fetch(
                    unittest.mock.sentinel.key,
                    unittest.mock.sentinel.account,
                    unittest.mock.sentinel.peer,
                )
            )

        _get_service.assert_called_once_with(
            unittest.mock.sentinel.account,
        )

        self.svc_instance.fetch.assert_called_once_with(
            unittest.mock.sentinel.key,
            unittest.mock.sentinel.peer,
        )

        self.assertEqual(result, unittest.mock.sentinel.r)

    def test_get_propagates_key_error_from__get_service(self):
        with contextlib.ExitStack() as stack:
            _get_service = stack.enter_context(unittest.mock.patch.object(
                self.smp,
                "_get_service",
            ))
            _get_service.side_effect = KeyError

            stack.enter_context(self.assertRaises(KeyError))

            self.smp.get(
                unittest.mock.sentinel.key,
                unittest.mock.sentinel.account,
                unittest.mock.sentinel.peer,
            )

        _get_service.assert_called_once_with(unittest.mock.sentinel.account)

    def test_get_forwards_to_service_for_account(self):
        with contextlib.ExitStack() as stack:
            _get_service = stack.enter_context(unittest.mock.patch.object(
                self.smp,
                "_get_service",
            ))
            _get_service.return_value = self.svc_instance
            self.svc_instance.get.return_value = unittest.mock.sentinel.r

            result = self.smp.get(
                unittest.mock.sentinel.key,
                unittest.mock.sentinel.account,
                unittest.mock.sentinel.peer,
            )

        _get_service.assert_called_once_with(unittest.mock.sentinel.account)

        self.svc_instance.get.assert_called_once_with(
            unittest.mock.sentinel.key,
            unittest.mock.sentinel.peer,
        )

        self.assertEqual(result, unittest.mock.sentinel.r)


class TestLRUMetadataProvider(unittest.TestCase):
    def setUp(self):
        self.svc_cls = unittest.mock.Mock(
            spec=metadata.AbstractMetadataProviderService
        )
        self.svc_cls.PUBLISHED_KEYS = [unittest.mock.sentinel.key]
        self.svc_instance = unittest.mock.Mock(
            spec=metadata.AbstractMetadataProviderService
        )
        self.svc_instance.fetch = CoroutineMock()
        self.svc_cls.return_value = self.svc_instance
        self.client = unittest.mock.Mock(spec=jclib.client.Client)
        self.lrump = metadata.LRUMetadataProvider(
            self.svc_cls,
            self.client,
        )
        self.listener = make_listener(self.lrump)

    def test_connects_to_own_on_changed(self):
        with unittest.mock.patch.object(
                metadata.LRUMetadataProvider,
                "_on_changed") as handler:
            lrump = metadata.LRUMetadataProvider(self.svc_cls, self.client)

        lrump.on_changed(unittest.mock.sentinel.arg)

        handler.assert_called_once_with(unittest.mock.sentinel.arg)

    def test_fetch_uses__get_service(self):
        with contextlib.ExitStack() as stack:
            _get_service = stack.enter_context(unittest.mock.patch.object(
                self.lrump,
                "_get_service",
            ))
            _get_service.return_value = self.svc_instance

            self.svc_instance.fetch.return_value = unittest.mock.sentinel.r

            result = run_coroutine(self.lrump.fetch(
                unittest.mock.sentinel.key,
                unittest.mock.sentinel.account,
                unittest.mock.sentinel.peer,
            ))

        _get_service.assert_called_once_with(unittest.mock.sentinel.account)

        self.svc_instance.fetch.assert_called_once_with(
            unittest.mock.sentinel.key,
            unittest.mock.sentinel.peer,
        )

        self.assertEqual(result, unittest.mock.sentinel.r)

    def test_get_returns_value_from_service(self):
        with contextlib.ExitStack() as stack:
            _get_service = stack.enter_context(unittest.mock.patch.object(
                self.lrump,
                "_get_service",
            ))
            _get_service.return_value = self.svc_instance

            self.svc_instance.get.return_value = unittest.mock.sentinel.r

            result = self.lrump.get(
                unittest.mock.sentinel.key,
                unittest.mock.sentinel.account,
                unittest.mock.sentinel.peer,
            )

        _get_service.assert_called_once_with(unittest.mock.sentinel.account)

        self.svc_instance.get.assert_called_once_with(
            unittest.mock.sentinel.key,
            unittest.mock.sentinel.peer,
        )

        self.assertEqual(
            result,
            unittest.mock.sentinel.r,
        )

    def test_get_masks_tempfail(self):
        with contextlib.ExitStack() as stack:
            _get_service = stack.enter_context(unittest.mock.patch.object(
                self.lrump,
                "_get_service",
            ))
            _get_service.return_value = self.svc_instance

            self.svc_instance.get.side_effect = metadata.Tempfail

            result = self.lrump.get(
                unittest.mock.sentinel.key,
                unittest.mock.sentinel.account,
                unittest.mock.sentinel.peer,
            )

        _get_service.assert_called_once_with(unittest.mock.sentinel.account)

        self.svc_instance.get.assert_called_once_with(
            unittest.mock.sentinel.key,
            unittest.mock.sentinel.peer,
        )

        self.assertIsNone(result)

    def test_get_uses_cache_set_by_fetch_on_tempfail(self):
        with contextlib.ExitStack() as stack:
            _get_service = stack.enter_context(unittest.mock.patch.object(
                self.lrump,
                "_get_service",
            ))
            _get_service.return_value = self.svc_instance

            self.svc_instance.fetch.return_value = unittest.mock.sentinel.r
            self.svc_instance.get.side_effect = metadata.Tempfail

            run_coroutine(self.lrump.fetch(
                unittest.mock.sentinel.key,
                unittest.mock.sentinel.account,
                unittest.mock.sentinel.peer,
            ))

            result = self.lrump.get(
                unittest.mock.sentinel.key,
                unittest.mock.sentinel.account,
                unittest.mock.sentinel.peer,
            )

        self.svc_instance.fetch.assert_called_once_with(
            unittest.mock.sentinel.key,
            unittest.mock.sentinel.peer,
        )

        self.svc_instance.get.assert_called_once_with(
            unittest.mock.sentinel.key,
            unittest.mock.sentinel.peer,
        )

        self.assertEqual(
            result,
            unittest.mock.sentinel.r
        )

    def test__on_changed_sets_new_cache_entry(self):
        with contextlib.ExitStack() as stack:
            _get_service = stack.enter_context(unittest.mock.patch.object(
                self.lrump,
                "_get_service",
            ))
            _get_service.return_value = self.svc_instance

            self.svc_instance.fetch.return_value = unittest.mock.sentinel.r
            self.svc_instance.get.side_effect = metadata.Tempfail

            run_coroutine(self.lrump.fetch(
                unittest.mock.sentinel.key,
                unittest.mock.sentinel.account,
                unittest.mock.sentinel.peer,
            ))

            self.lrump._on_changed(
                unittest.mock.sentinel.key,
                unittest.mock.sentinel.account,
                unittest.mock.sentinel.peer,
                unittest.mock.sentinel.v,
            )

            result = self.lrump.get(
                unittest.mock.sentinel.key,
                unittest.mock.sentinel.account,
                unittest.mock.sentinel.peer,
            )

        self.assertEqual(
            result,
            unittest.mock.sentinel.v,
        )

    def test__on_changed_sets_new_cache_entry_to_none(self):
        with contextlib.ExitStack() as stack:
            _get_service = stack.enter_context(unittest.mock.patch.object(
                self.lrump,
                "_get_service",
            ))
            _get_service.return_value = self.svc_instance

            self.svc_instance.fetch.return_value = unittest.mock.sentinel.r
            self.svc_instance.get.side_effect = metadata.Tempfail

            run_coroutine(self.lrump.fetch(
                unittest.mock.sentinel.key,
                unittest.mock.sentinel.account,
                unittest.mock.sentinel.peer,
            ))

            self.lrump._on_changed(
                unittest.mock.sentinel.key,
                unittest.mock.sentinel.account,
                unittest.mock.sentinel.peer,
                None,
            )

            result = self.lrump.get(
                unittest.mock.sentinel.key,
                unittest.mock.sentinel.account,
                unittest.mock.sentinel.peer,
            )

        self.assertIsNone(result)

    def test_fetch_emits_on_changed_on_new_value(self):
        with contextlib.ExitStack() as stack:
            _get_service = stack.enter_context(unittest.mock.patch.object(
                self.lrump,
                "_get_service",
            ))
            _get_service.return_value = self.svc_instance

            self.svc_instance.fetch.return_value = unittest.mock.sentinel.r

            run_coroutine(self.lrump.fetch(
                unittest.mock.sentinel.key,
                unittest.mock.sentinel.account,
                unittest.mock.sentinel.peer,
            ))

            self.listener.on_changed.assert_called_once_with(
                unittest.mock.sentinel.key,
                unittest.mock.sentinel.account,
                unittest.mock.sentinel.peer,
                unittest.mock.sentinel.r,
            )
            self.listener.on_changed.reset_mock()

    def test_fetch_does_not_emit_on_changed_on_equal_value(self):
        with contextlib.ExitStack() as stack:
            _get_service = stack.enter_context(unittest.mock.patch.object(
                self.lrump,
                "_get_service",
            ))
            _get_service.return_value = self.svc_instance

            self.svc_instance.fetch.return_value = unittest.mock.sentinel.r

            run_coroutine(self.lrump.fetch(
                unittest.mock.sentinel.key,
                unittest.mock.sentinel.account,
                unittest.mock.sentinel.peer,
            ))

            self.listener.on_changed.reset_mock()

            run_coroutine(self.lrump.fetch(
                unittest.mock.sentinel.key,
                unittest.mock.sentinel.account,
                unittest.mock.sentinel.peer,
            ))

            self.listener.on_changed.assert_not_called()

    def test_fetch_emits_on_changed_on_unequal_value(self):
        with contextlib.ExitStack() as stack:
            _get_service = stack.enter_context(unittest.mock.patch.object(
                self.lrump,
                "_get_service",
            ))
            _get_service.return_value = self.svc_instance

            self.svc_instance.fetch.return_value = unittest.mock.sentinel.r1

            run_coroutine(self.lrump.fetch(
                unittest.mock.sentinel.key,
                unittest.mock.sentinel.account,
                unittest.mock.sentinel.peer,
            ))

            self.listener.on_changed.reset_mock()

            self.svc_instance.fetch.return_value = unittest.mock.sentinel.r2

            run_coroutine(self.lrump.fetch(
                unittest.mock.sentinel.key,
                unittest.mock.sentinel.account,
                unittest.mock.sentinel.peer,
            ))

            self.listener.on_changed.assert_called_once_with(
                unittest.mock.sentinel.key,
                unittest.mock.sentinel.account,
                unittest.mock.sentinel.peer,
                unittest.mock.sentinel.r2,
            )


class TestMetadataFrontend(unittest.TestCase):
    def setUp(self):
        self.mf = metadata.MetadataFrontend()
        self.p1 = make_provider_mock(["k1"])
        self.p2 = make_provider_mock(["k1", "k2"])
        self.p3 = make_provider_mock(["k2"])

    def tearDown(self):
        del self.mf

    def test_register_provider_rejects_duplicate_keys(self):
        self.mf.register_provider(self.p1)
        with self.assertRaisesRegex(
                ValueError,
                r"key conflict between"):
            self.mf.register_provider(self.p2)

        self.mf.register_provider(self.p3)

    def test_get_raises_for_unknown_key(self):
        self.mf.register_provider(self.p3)

        with self.assertRaisesRegex(
                LookupError,
                r"no provider for key: 'k1'"):
            self.mf.get(
                "k1",
                unittest.mock.sentinel.account,
                unittest.mock.sentinel.peer
            )

    def test_get_forwards_to_provider_for_known_key(self):
        self.mf.register_provider(self.p1)

        result = self.mf.get(
            "k1",
            unittest.mock.sentinel.account,
            unittest.mock.sentinel.peer,
        )

        self.p1.get.assert_called_once_with(
            "k1",
            unittest.mock.sentinel.account,
            unittest.mock.sentinel.peer,
        )

        self.assertEqual(result, self.p1.get())

    def test_get_forwards_to_correct_provider(self):
        self.mf.register_provider(self.p1)
        self.mf.register_provider(self.p3)

        result = self.mf.get(
            "k2",
            unittest.mock.sentinel.account,
            unittest.mock.sentinel.peer,
        )

        self.p3.get.assert_called_once_with(
            "k2",
            unittest.mock.sentinel.account,
            unittest.mock.sentinel.peer,
        )
        self.p1.get.assert_not_called()

        self.assertEqual(result, self.p3.get())

    def test_fetch_raises_for_unknown_key(self):
        self.mf.register_provider(self.p3)

        with self.assertRaisesRegex(
                LookupError,
                r"no provider for key: 'k1'"):
            run_coroutine(self.mf.fetch(
                "k1",
                unittest.mock.sentinel.account,
                unittest.mock.sentinel.peer,
            ))

    def test_fetch_forwards_to_provider_for_known_key(self):
        self.mf.register_provider(self.p1)
        self.p1.fetch.return_value = unittest.mock.sentinel.result

        result = run_coroutine(self.mf.fetch(
            "k1",
            unittest.mock.sentinel.account,
            unittest.mock.sentinel.peer,
        ))

        self.p1.fetch.assert_called_once_with(
            "k1",
            unittest.mock.sentinel.account,
            unittest.mock.sentinel.peer,
        )

        self.assertEqual(result, unittest.mock.sentinel.result)

    def test_fetch_forwards_to_correct_provider(self):
        self.mf.register_provider(self.p1)
        self.mf.register_provider(self.p3)
        self.p3.fetch.return_value = unittest.mock.sentinel.result

        result = run_coroutine(self.mf.fetch(
            "k2",
            unittest.mock.sentinel.account,
            unittest.mock.sentinel.peer,
        ))

        self.p3.fetch.assert_called_once_with(
            "k2",
            unittest.mock.sentinel.account,
            unittest.mock.sentinel.peer,
        )
        self.p1.fetch.assert_not_called()

        self.assertEqual(result, unittest.mock.sentinel.result)

    def test_no_changed_signals_for_unregistered_keys(self):
        with self.assertRaisesRegex(
                LookupError,
                r"no provider for key: 'k1'"):
            self.mf.changed_signal("k1")

    def test_changed_signal_for_registered_keys(self):
        self.mf.register_provider(self.p2)

        self.assertIsNot(self.mf.changed_signal("k1"),
                         self.mf.changed_signal("k2"))
        self.assertIs(self.mf.changed_signal("k1"),
                      self.mf.changed_signal("k1"))
        self.assertIs(self.mf.changed_signal("k2"),
                      self.mf.changed_signal("k2"))

        self.assertIsInstance(self.mf.changed_signal("k1"),
                              aioxmpp.callbacks.AdHocSignal)

        self.assertIsInstance(self.mf.changed_signal("k2"),
                              aioxmpp.callbacks.AdHocSignal)
