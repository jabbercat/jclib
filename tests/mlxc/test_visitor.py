import abc
import unittest
import unittest.mock

import mlxc.visitor as visitor


class Testfor_class(unittest.TestCase):
    def test_for_class_decorator(self):
        class Foo:
            pass

        @visitor.for_class(Foo)
        def foo():
            pass

        self.assertIs(foo.roster_visited_class,
                      Foo)



class TestVisitorMeta(unittest.TestCase):
    def test_is_abc_meta(self):
        self.assertTrue(issubclass(
            visitor.VisitorMeta,
            abc.ABCMeta,
        ))

    def test__issubclass_cmp(self):
        class Target:
            pass

        class OtherTarget(Target):
            pass

        class YetAnotherTarget(OtherTarget):
            pass

        self.assertLess(
            visitor.VisitorMeta._issubclass_cmp(
                OtherTarget,
                Target),
            0
        )

        self.assertGreater(
            visitor.VisitorMeta._issubclass_cmp(
                Target,
                OtherTarget),
            0
        )

    def test_collect_decorated_methods(self):
        class Target:
            pass

        class OtherTarget(Target):
            pass

        class YetAnotherTarget(OtherTarget):
            pass

        class Foo(metaclass=visitor.VisitorMeta):
            @visitor.for_class(Target)
            def visit_foo(self):
                pass

            @visitor.for_class(OtherTarget)
            def visit_bar(self):
                pass

            @visitor.for_class(YetAnotherTarget)
            def visit_baz(self):
                pass

        Foo.visit_foo
        Foo.visit_bar

        self.assertSequenceEqual(
            Foo.VISITOR_HANDLERS,
            [
                (YetAnotherTarget, unittest.mock.ANY),
                (OtherTarget, unittest.mock.ANY),
                (Target, unittest.mock.ANY),
            ]
        )

    def test_inherit_decorated_methods(self):
        class Target:
            pass

        class OtherTarget(Target):
            pass

        class YetAnotherTarget(OtherTarget):
            pass

        class Foo(metaclass=visitor.VisitorMeta):
            @visitor.for_class(Target)
            def visit_foo(self):
                pass

        class Bar(Foo):
            @visitor.for_class(OtherTarget)
            def visit_foo(self):
                pass

        self.assertSequenceEqual(
            Bar.VISITOR_HANDLERS,
            [
                (OtherTarget, unittest.mock.ANY),
                (Target, unittest.mock.ANY),
            ]
        )

    def test_visitor(self):
        class Target:
            pass

        class OtherTarget(Target):
            pass

        class YetAnotherTarget(OtherTarget):
            pass

        mock = unittest.mock.Mock()

        class Foo(metaclass=visitor.VisitorMeta):
            @visitor.for_class(Target)
            def visit_foo(self):
                mock.visit_Target()

            @visitor.for_class(YetAnotherTarget)
            def visit_bar(self):
                mock.visit_YetAnotherTarget()

        class Bar(Foo):
            @visitor.for_class(OtherTarget)
            def visit_foo(self):
                mock.visit_OtherTarget()

        b = Bar()
        Bar.visitor(OtherTarget())(b)
        Bar.visitor(YetAnotherTarget())(b)
        Bar.visitor(Target())(b)

        f = Foo()
        Foo.visitor(OtherTarget())(b)
        Foo.visitor(YetAnotherTarget())(b)
        Foo.visitor(Target())(b)

        self.assertSequenceEqual(
            mock.mock_calls,
            [
                unittest.mock.call.visit_OtherTarget(),
                unittest.mock.call.visit_YetAnotherTarget(),
                unittest.mock.call.visit_Target(),
                unittest.mock.call.visit_Target(),
                unittest.mock.call.visit_YetAnotherTarget(),
                unittest.mock.call.visit_Target(),
            ]
        )

    def test_visitor_raises_KeyError_on_unhandled_type(self):
        class Foo(metaclass=visitor.VisitorMeta):
            pass

        with self.assertRaises(KeyError):
            Foo.visitor(object())

    def test_equal_visitors_first_declared_wins(self):
        class Target:
            pass

        class OtherTarget:
            pass

        class YetAnotherTarget(Target, OtherTarget):
            pass

        mock = unittest.mock.Mock()
        class Foo(metaclass=visitor.VisitorMeta):
            @visitor.for_class(Target)
            def visit_target(self):
                mock.target()

            @visitor.for_class(OtherTarget)
            def visit_other_target(self):
                mock.other_target()

        Foo.visitor(YetAnotherTarget())(Foo())

        self.assertSequenceEqual(
            mock.mock_calls,
            [
                unittest.mock.call.target(),
            ]
        )


class TestVisitor(unittest.TestCase):
    def test_uses_VisitorMeta(self):
        self.assertIsInstance(
            visitor.Visitor,
            visitor.VisitorMeta
        )

    def setUp(self):
        self.visitor = visitor.Visitor()

    def test_visit(self):
        instance = object()

        with unittest.mock.patch.object(
                visitor.Visitor,
                "visitor") as visitor_:
            self.visitor.visit(instance)

        self.assertSequenceEqual(
            visitor_.mock_calls,
            [
                unittest.mock.call(instance),
                unittest.mock.call()(self.visitor, instance)
            ]
        )

    def test_visit_raises_TypeError_on_unhandled_type(self):
        instance = object()

        with unittest.mock.patch.object(
                visitor.Visitor,
                "visitor") as visitor_:
            visitor_.side_effect = KeyError()

            with self.assertRaisesRegexp(TypeError,
                                         "unhandled type in visitor"):
                self.visitor.visit(instance)

        self.assertSequenceEqual(
            visitor_.mock_calls,
            [
                unittest.mock.call(instance),
            ]
        )

    def tearDown(self):
        del self.visitor
