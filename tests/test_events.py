import unittest

import mlxc.events as events

class TestEventHandler(unittest.TestCase):
    def _test_plain_event_result(self, obj, event_type, value):
        ev = events.Event(event_type)
        self.assertEqual(obj.dispatch_event(ev), value)

    def test_dispatch_event_simple(self):
        class Handler(events.EventHandler):
            @events.handler
            def foobar(self, ev):
                return "foobar"

        obj = Handler()
        ev = events.Event("foobar")
        self.assertTrue(events.accepts_event(obj, "foobar"))
        self.assertEqual(obj.dispatch_event(ev), "foobar")

    def test_dispatch_event_specific(self):
        class Handler(events.EventHandler):
            @events.handler_for("baz")
            def foobar(self, ev):
                return "baz"

        obj = Handler()
        ev = events.Event("baz")
        self.assertTrue(events.accepts_event(obj, "baz"))
        self.assertEqual(obj.dispatch_event(ev), "baz")

    def test_dispatch_event_specific_multiple(self):
        class Handler(events.EventHandler):
            @events.handler_for("bar", "baz")
            def foobar(self, ev):
                return "bar or baz"

        obj = Handler()
        self.assertTrue(events.accepts_event(obj, "baz"))
        self.assertTrue(events.accepts_event(obj, "bar"))
        ev = events.Event("baz")
        self.assertEqual(obj.dispatch_event(ev), "bar or baz")
        ev = events.Event("bar")
        self.assertEqual(obj.dispatch_event(ev), "bar or baz")

    def test_dispatch_catchall(self):
        class Handler(events.EventHandler):
            @events.catchall
            def foobar(self, ev):
                return "caught"

            @events.handler_for("foo")
            def fnord(self, ev):
                return "foo"

        obj = Handler()
        self.assertTrue(events.accepts_event(obj, "foo"))
        self.assertTrue(events.accepts_event(obj, 10))
        ev = events.Event("foo")
        self.assertEqual(obj.dispatch_event(ev), "foo")
        ev = events.Event(10)
        self.assertEqual(obj.dispatch_event(ev), "caught")

    def test_require_handler(self):
        class Handler(events.EventHandler):
            pass

        ev = events.Event("foo")
        obj = Handler()
        self.assertFalse(events.accepts_event(obj, "foo"))
        with self.assertRaisesRegexp(
                TypeError,
                ".*? does not support event 'foo'"):
            obj.dispatch_event(ev)

    def test_inheritance(self):
        class BaseA(events.EventHandler):
            @events.handler
            def a(self, ev):
                return "BaseA"

            @events.handler
            def common(self, ev):
                return "BaseA"

        class BaseB(events.EventHandler):
            @events.handler
            def b(self, ev):
                return "BaseB"

            @events.handler
            def c(self, ev):
                return "BaseC"

            @events.handler
            def common(self, ev):
                return "BaseB"

        class BaseC(events.EventHandler):
            @events.handler
            def c(self, ev):
                return "BaseC"

        class Merged(BaseA, BaseB, BaseC):
            pass

        m = Merged()
        self.assertTrue(events.accepts_event(m, "a"))
        self.assertTrue(events.accepts_event(m, "b"))
        self.assertTrue(events.accepts_event(m, "c"))
        self.assertTrue(events.accepts_event(m, "common"))

        self._test_plain_event_result(m, "a", "BaseA")
        self._test_plain_event_result(m, "b", "BaseB")
        self._test_plain_event_result(m, "c", "BaseC")
        self._test_plain_event_result(m, "common", "BaseA")
