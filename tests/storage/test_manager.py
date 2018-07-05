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
        self.delay = 0.1
        self.max_delay = 0.2
        self.m = jclib.storage.manager.WriteManager(
            delay=self.delay,
            max_delay=self.max_delay,
        )
        self.listener = make_listener(self.m)

    def test_uses_delayed_invocation(self):
        with unittest.mock.patch(
                "jclib.utils.DelayedInvocation") as DelayedInvocation:
            wm = jclib.storage.manager.WriteManager(
                delay=unittest.mock.sentinel.delay,
                max_delay=unittest.mock.sentinel.max_delay,
                loop=unittest.mock.sentinel.loop,
            )

        DelayedInvocation.assert_called_once_with(
            wm._writeback_scheduled,
            unittest.mock.sentinel.delay,
            max_delay=unittest.mock.sentinel.max_delay,
            loop=unittest.mock.sentinel.loop,
        )

        self.assertEqual(wm._scheduler, DelayedInvocation())

    def test_request_writeback_causes_writeback(self):
        self.m.request_writeback()
        run_coroutine(asyncio.sleep(self.delay/2))
        self.listener.on_writeback.assert_not_called()
        run_coroutine(asyncio.sleep(self.delay/2 + self.delay/10))
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
            self.m.request_writeback()
            run_coroutine(asyncio.sleep(self.delay*1.1))
            self.listener.on_writeback.assert_called_once_with()
            self.assertTrue(not_called, "flush is called before on_writeback")
            flush_all.assert_called_once_with()
