import unittest

import aioxmpp.service as service
import aioxmpp.testutils as testutils

import jclib.plugin as plugin


class TestBase(unittest.TestCase):
    def test_is_service_class(self):
        self.assertIsInstance(
            plugin.Base,
            service.Meta
        )

    def test_init(self):
        c = object()
        p = plugin.Base(c)
        self.assertIs(p.client, c)

    def setUp(self):
        c = object()
        self.p = plugin.Base(c)

    def test_close_coroutine_sets_client_to_None(self):
        testutils.run_coroutine(self.p.close())
        self.assertIsNone(self.p.client)

    def test_close_calls__close(self):
        with unittest.mock.patch.object(
                self.p,
                "_close",
                new=testutils.CoroutineMock()) as _close:
            testutils.run_coroutine(self.p.close())

        self.assertSequenceEqual(
            _close.mock_calls,
            [
                unittest.mock.call()
            ]
        )

    def test_client_is_not_writable(self):
        c = object()
        p = plugin.Base(c)
        with self.assertRaises(AttributeError):
            p.client = object()
