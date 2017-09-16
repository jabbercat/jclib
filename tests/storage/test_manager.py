import asyncio
import contextlib
import unittest

from datetime import timedelta

from aioxmpp.testutils import (
    make_listener,
    run_coroutine,
)

import jclib.storage.manager


class TestWriteManager(unittest.TestCase):
    def setUp(self):
        self.m = jclib.storage.manager.WriteManager(
            writeback_interval=timedelta(seconds=0.1)
        )
        self.listener = make_listener(self.m)

    def tearDown(self):
        self.m.close()

    def test_writeback_interval(self):
        self.assertEqual(self.m.writeback_interval, timedelta(seconds=0.1))

    def test_emits_on_writeback_regularly(self):
        self.listener.on_writeback.assert_not_called()
        run_coroutine(asyncio.sleep(0.15))
        self.listener.on_writeback.assert_called_once_with()

        self.listener.on_writeback.reset_mock()
        run_coroutine(asyncio.sleep(0.1))
        self.listener.on_writeback.assert_called_once_with()

    def test_change_of_writeback_interval_causes_emit(self):
        self.listener.on_writeback.assert_not_called()
        self.m.writeback_interval = timedelta(seconds=0.2)
        self.listener.on_writeback.assert_not_called()

        run_coroutine(asyncio.sleep(0))
        self.listener.on_writeback.assert_called_once_with()

        self.listener.on_writeback.reset_mock()
        run_coroutine(asyncio.sleep(0.3))
        self.listener.on_writeback.assert_called_once_with()

    def test_close_stops_loop(self):
        self.listener.on_writeback.assert_not_called()
        run_coroutine(asyncio.sleep(0.15))
        self.listener.on_writeback.assert_called_once_with()

        self.listener.on_writeback.reset_mock()
        run_coroutine(asyncio.sleep(0.1))
        self.listener.on_writeback.assert_called_once_with()

        self.m.close()

        self.listener.on_writeback.reset_mock()
        run_coroutine(asyncio.sleep(0.1))
        self.listener.on_writeback.assert_not_called()

    def test_request_writeback(self):
        self.listener.on_writeback.assert_not_called()
        self.m.request_writeback()
        self.listener.on_writeback.assert_not_called()

        run_coroutine(asyncio.sleep(0))
        self.listener.on_writeback.assert_called_once_with()

        self.listener.on_writeback.reset_mock()
        run_coroutine(asyncio.sleep(0.15))
        self.listener.on_writeback.assert_called_once_with()

    def test_calls_xml_frontend_flush_after_writeback(self):
        not_called = False

        with contextlib.ExitStack() as stack:
            flush_all = stack.enter_context(unittest.mock.patch.object(
                jclib.storage.xml,
                "flush_all",
            ))

            def check_not_called():
                nonlocal not_called, flush_all
                try:
                    flush_all.assert_not_called()
                    not_called = True
                except Exception:
                    pass

            flush_all.assert_not_called()
            self.m.on_writeback.connect(
                check_not_called,
            )
            run_coroutine(asyncio.sleep(0.15))
            self.assertTrue(not_called, "flush is called before on_writeback")
            flush_all.assert_called_once_with()
