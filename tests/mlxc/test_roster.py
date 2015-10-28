import unittest
import unittest.mock

import mlxc.instrumentable_list as ilist
import mlxc.roster as roster


class TestNode(unittest.TestCase):
    def test_init_default(self):
        item = roster.Node()
        self.assertIsNone(item.parent)

    def setUp(self):
        self.item = roster.Node()

    def test_parent_is_not_settable(self):
        with self.assertRaises(AttributeError):
            self.item.parent = None

    def test__add_to_parent_sets_parent(self):
        obj = object()
        self.item._add_to_parent(obj)
        self.assertIs(self.item.parent, obj)

    def test__add_to_parent_raises_if_parent_is_set(self):
        obj = object()
        self.item._add_to_parent(obj)
        self.assertIs(self.item.parent, obj)
        with self.assertRaises(RuntimeError):
            self.item._add_to_parent(obj)
        with self.assertRaises(RuntimeError):
            self.item._add_to_parent(object())
        self.assertIs(self.item.parent, obj)

    def test__remove_from_parent_sets_parent_to_None(self):
        obj = object()
        self.item._add_to_parent(obj)
        self.item._remove_from_parent()
        self.assertIsNone(self.item.parent)

    def test__remove_from_parent_raises_if_parent_is_not_set(self):
        with self.assertRaises(RuntimeError):
            self.item._remove_from_parent()

    def tearDown(self):
        del self.item


class TestContainer(unittest.TestCase):
    def test_is_model_list(self):
        self.assertTrue(issubclass(
            roster.Container,
            ilist.ModelList
        ))

    def setUp(self):
        self.cont = roster.Container()
        self.mock = unittest.mock.Mock()

        self.mock.register_item.return_value = False
        self.cont.on_register_item.connect(
            self.mock.register_item
        )

        self.mock.unregister_item.return_value = False
        self.cont.on_unregister_item.connect(
            self.mock.unregister_item
        )

        self.cont.begin_insert_rows = self.mock.begin_insert_rows
        self.cont.end_insert_rows = self.mock.end_insert_rows
        self.cont.begin_remove_rows = self.mock.begin_remove_rows
        self.cont.end_remove_rows = self.mock.end_remove_rows
        self.cont.begin_move_rows = self.mock.begin_move_rows
        self.cont.end_move_rows = self.mock.end_move_rows

    def test__begin_insert_rows_emits_parent(self):
        a, b = object(), object()
        self.cont._begin_insert_rows(a, b)
        self.assertSequenceEqual(
            self.mock.mock_calls,
            [
                unittest.mock.call.begin_insert_rows(
                    self.cont,
                    a, b)
            ]
        )

    def test__begin_move_rows_emits_parent(self):
        a, b, c = object(), object(), object()
        self.cont._begin_move_rows(a, b, c)
        self.assertSequenceEqual(
            self.mock.mock_calls,
            [
                unittest.mock.call.begin_move_rows(
                    self.cont, a, b,
                    self.cont, c)
            ]
        )

    def test__begin_remove_rows_emits_parent(self):
        a, b = object(), object()
        self.cont._begin_remove_rows(a, b)
        self.assertSequenceEqual(
            self.mock.mock_calls,
            [
                unittest.mock.call.begin_remove_rows(
                    self.cont,
                    a, b)
            ]
        )

    def test_inject_does_not_emit_model_events_but_emits_register(self):
        items = [roster.Node(), roster.Node(), roster.Node()]
        more_items = [roster.Node(),
                      roster.Node(),
                      roster.Node()]
        self.cont[:] = items
        self.mock.mock_calls.clear()

        def generate():
            yield from more_items

        self.cont.inject(1, generate())

        self.assertSequenceEqual(
            self.cont,
            items[:1] + more_items + items[1:]
        )
        self.assertSequenceEqual(
            self.mock.mock_calls,
            [
                unittest.mock.call.register_item(more_items[0]),
                unittest.mock.call.register_item(more_items[1]),
                unittest.mock.call.register_item(more_items[2]),
            ]
        )

    def test_eject_does_not_emit_model_events_but_emits_unregister(self):
        items = [roster.Node() for i in range(5)]
        self.cont[:] = items
        self.mock.mock_calls.clear()

        self.assertSequenceEqual(
            self.cont.eject(1, 3),
            items[1:3]
        )

        self.assertSequenceEqual(
            self.cont,
            items[:1] + items[3:]
        )
        self.assertSequenceEqual(
            self.mock.mock_calls,
            [
                unittest.mock.call.unregister_item(items[1]),
                unittest.mock.call.unregister_item(items[2]),
            ]
        )

    def test_register_item_sets_parent(self):
        obj = unittest.mock.Mock()
        self.cont._register_items([obj])
        self.assertSequenceEqual(
            obj.mock_calls,
            [
                unittest.mock.call._add_to_parent(self.cont)
            ]
        )

    def test_parent_is_set_during_initalisation(self):
        obj = unittest.mock.Mock()
        cont = roster.Container([obj])
        self.assertSequenceEqual(
            obj.mock_calls,
            [
                unittest.mock.call._add_to_parent(cont)
            ]
        )

    def test_unregister_item_unsets_parent(self):
        obj = unittest.mock.Mock()
        self.cont._unregister_items([obj])
        self.assertSequenceEqual(
            obj.mock_calls,
            [
                unittest.mock.call._remove_from_parent()
            ]
        )

    def tearDown(self):
        del self.cont


class TestTree(unittest.TestCase):
    def setUp(self):
        self.tree = roster.Tree()

    def test_root_is_container(self):
        self.assertIsInstance(
            self.tree.root,
            roster.Container
        )

    def test_root_is_not_writable(self):
        with self.assertRaises(AttributeError):
            self.tree.root = object()

    def tearDown(self):
        del self.tree


class TestRosterWalker(unittest.TestCase):
    def setUp(self):
        self.w = roster.Walker()

    def test_visit_dispatches_to_class_name(self):
        class Foo:
            pass

        instance = Foo()

        self.w.visit_Foo = unittest.mock.Mock()
        self.w.visit(instance)
        self.assertSequenceEqual(
            self.w.visit_Foo.mock_calls,
            [
                unittest.mock.call(instance)
            ]
        )

    def test_visit_dispatches_to_generic_visit_without_handler(self):
        class Foo:
            pass

        instance = Foo()

        with unittest.mock.patch.object(
                self.w, "generic_visit") as generic_visit:
            self.w.visit(instance)

        self.assertSequenceEqual(
            generic_visit.mock_calls,
            [
                unittest.mock.call(instance)
            ]
        )

    def test_generic_visit_visits_children_of_Container(self):
        class Foo(roster.Container):
            pass

        class Bar(roster.Node):
            pass

        items = [Bar(), Bar(), Bar()]

        f = Foo(items)

        with unittest.mock.patch.object(
                self.w, "visit") as visit:
            self.w.generic_visit(f)

        self.assertSequenceEqual(
            visit.mock_calls,
            [
                unittest.mock.call(item)
                for item in items
            ]
        )

    def tearDown(self):
        del self.w
