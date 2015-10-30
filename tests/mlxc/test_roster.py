import contextlib
import unittest
import unittest.mock

import aioxmpp.roster
import aioxmpp.structs
import aioxmpp.testutils

import mlxc.instrumentable_list as ilist
import mlxc.plugin as plugin
import mlxc.roster as roster
import mlxc.visitor as visitor

from mlxc.testutils import (
    ClientMock
)


TEST_ACCOUNT_JID = aioxmpp.structs.JID.fromstr(
    "foo@a.example"
)
TEST_PEER_JID = aioxmpp.structs.JID.fromstr(
    "bar@b.example"
)
TEST_PEER_JID2 = aioxmpp.structs.JID.fromstr(
    "baz@c.example"
)


class TestNode(unittest.TestCase):
    def test_init_default(self):
        item = roster.Node()
        self.assertIsNone(item.parent)
        self.assertIsNone(item.index_at_parent)
        self.assertIsNone(item.root)

    def setUp(self):
        self.item = roster.Node()

    def test_parent_is_not_settable(self):
        with self.assertRaises(AttributeError):
            self.item.parent = None

    def test_root_is_not_settable(self):
        with self.assertRaises(AttributeError):
            self.item.root = None

    def test_index_at_parent_is_not_settable(self):
        with self.assertRaises(AttributeError):
            self.item.index_at_parent = None

    def test__add_to_parent_sets_parent(self):
        obj = unittest.mock.Mock()
        self.item._add_to_parent(obj)
        self.assertIs(self.item.parent, obj)

    def test__add_to_parent_raises_if_parent_is_set(self):
        obj = unittest.mock.Mock()
        self.item._add_to_parent(obj)
        self.assertIs(self.item.parent, obj)
        with self.assertRaises(RuntimeError):
            self.item._add_to_parent(obj)
        with self.assertRaises(RuntimeError):
            self.item._add_to_parent(object())
        self.assertIs(self.item.parent, obj)

    def test__add_to_parent_calls__root_changed(self):
        obj = unittest.mock.Mock()
        with unittest.mock.patch.object(
                self.item, "_root_changed") as root_changed:
            self.item._add_to_parent(obj)

        root_changed.assert_called_with()
        self.assertIsNone(self.item.root)

    def test__root_changed_updates_root_from_parent(self):
        obj = unittest.mock.Mock()
        # it is tested in another test that _add_to_parent calls _root_changed
        # and does not modify root by itself
        self.item._add_to_parent(obj)
        self.assertEqual(self.item.root, obj.root)

    def test_parent_supported(self):
        self.assertFalse(self.item.parent_supported(object()))

    def test__remove_from_parent_sets_parent_to_None(self):
        obj = unittest.mock.Mock()
        self.item._add_to_parent(obj)
        self.item._remove_from_parent()
        self.assertIsNone(self.item.parent)

    def test__remove_from_parent_sets_calls__root_changed(self):
        obj = unittest.mock.Mock()
        self.item._add_to_parent(obj)
        with unittest.mock.patch.object(
                self.item, "_root_changed") as root_changed:
            self.item._remove_from_parent()
        root_changed.assert_called_with()
        self.assertIsNone(self.item.parent)
        self.assertEqual(self.item.root, obj.root)

    def test__root_changed_set_root_to_None_if_parent_is_None(self):
        obj = unittest.mock.Mock()
        self.item._add_to_parent(obj)
        # it is tested in another test that _remove_from_parent calls
        # _root_changed and does not modify root by itself
        self.item._remove_from_parent()
        self.assertIsNone(self.item.root)

    def test__remove_from_parent_raises_if_parent_is_not_set(self):
        with self.assertRaises(RuntimeError):
            self.item._remove_from_parent()

    def test_attach_view_classmethod(self):
        class View:
            pass

        roster.Node.attach_view(View)
        self.assertIs(roster.Node.View, View)

    def test_view_attribute(self):
        self.assertIsNone(roster.Node.View)

    def test_reject_multiple_views(self):
        class View:
            pass

        roster.Node.attach_view(View)
        with self.assertRaisesRegexp(
                ValueError,
                "only a single view can be attached to a node class"):
            roster.Node.attach_view(View)

    def test_allow_specialized_views_for_subclasses(self):
        class View:
            pass

        class OtherView:
            pass

        class Subnode(roster.Node):
            pass

        roster.Node.attach_view(View)
        self.assertIs(Subnode.View, View)
        self.assertIs(roster.Node.View, View)

        Subnode.attach_view(OtherView)
        self.assertIs(Subnode.View, OtherView)
        self.assertIs(roster.Node.View, View)

    def test_attached_view_gets_instanciated_automatically(self):
        view_cls = unittest.mock.Mock()
        view_instance = view_cls()
        view_cls.mock_calls.clear()
        roster.Node.attach_view(view_cls)

        view = self.item.view
        self.assertSequenceEqual(
            view_cls.mock_calls,
            [
                unittest.mock.call(self.item)
            ]
        )
        self.assertEqual(view, view_instance)

        # test that it is not re-instanciated on each request
        view = self.item.view
        self.assertSequenceEqual(
            view_cls.mock_calls,
            [
                unittest.mock.call(self.item)
            ]
        )
        self.assertEqual(view, view_instance)

    def test_view_attribute_is_not_writable(self):
        with self.assertRaises(AttributeError):
            self.item.view = object()

    def test_view_attribute_raises_attribute_error_if_no_view_attached(self):
        self.assertIsNone(roster.Node.View)
        with self.assertRaises(AttributeError):
            self.item.view

    def test_view_attribute_can_be_deleted(self):
        view_cls = unittest.mock.Mock()
        view_instance = view_cls()
        view_cls.mock_calls.clear()
        roster.Node.attach_view(view_cls)

        view = self.item.view
        self.assertSequenceEqual(
            view_cls.mock_calls,
            [
                unittest.mock.call(self.item)
            ]
        )
        self.assertEqual(view, view_instance)

        del self.item.view

        # test that it *is* re-instanciated after deletion
        view = self.item.view
        self.assertSequenceEqual(
            view_cls.mock_calls,
            [
                unittest.mock.call(self.item),
                unittest.mock.call(self.item),
            ]
        )
        self.assertEqual(view, view_instance)

    def tearDown(self):
        del self.item
        try:
            roster.Node.View = None
        except AttributeError:
            pass


class TestContainer(unittest.TestCase):
    def test_is_model_list(self):
        self.assertTrue(issubclass(
            roster.Container,
            ilist.ModelList
        ))

    def test_is_node(self):
        self.assertTrue(issubclass(
            roster.Container,
            roster.Node
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

    def test_is_true_on_empty(self):
        self.assertTrue(self.cont)

    def test__begin_insert_rows_emits_parent(self):
        a, b = 1, 2
        self.cont._begin_insert_rows(a, b)
        self.assertSequenceEqual(
            self.mock.mock_calls,
            [
                unittest.mock.call.begin_insert_rows(
                    self.cont,
                    a, b)
            ]
        )

    def test_indices_are_set_and_updated_on_insert(self):
        items = [roster.Node(), roster.Node()]
        new_items = [roster.Node()]
        self.cont.extend(items)
        for i, item in enumerate(self.cont):
            self.assertIs(item.parent, self.cont)
            self.assertEqual(item.index_at_parent, i,
                             "index not set on extend")

        self.cont[1:1] = new_items
        for i, item in enumerate(self.cont):
            self.assertIs(item.parent, self.cont)
            self.assertEqual(item.index_at_parent, i,
                             "index not updated with __setitem__")

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

    def test_indices_are_set_and_updated_on_backward_move(self):
        items = [roster.Node(), roster.Node(), roster.Node()]
        self.cont.extend(items)
        for i, item in enumerate(self.cont):
            self.assertEqual(item.index_at_parent, i,
                             "index not set on extend")

        self.cont.move(2, 0)
        for i, item in enumerate(self.cont):
            self.assertEqual(item.index_at_parent, i,
                             "index not updated with move")

    def test_indices_are_set_and_updated_on_forward_move(self):
        items = [roster.Node(), roster.Node(), roster.Node()]
        self.cont.extend(items)
        for i, item in enumerate(self.cont):
            self.assertEqual(item.index_at_parent, i,
                             "index not set on extend")

        self.cont.move(0, 1)
        for i, item in enumerate(self.cont):
            self.assertEqual(item.index_at_parent, i,
                             "index not updated with move")

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

    def test_indices_are_set_and_updated_on_remove(self):
        items = [roster.Node(), roster.Node(), roster.Node()]
        self.cont.extend(items)
        for i, item in enumerate(self.cont):
            self.assertEqual(item.index_at_parent, i,
                             "index not set on extend")

        del self.cont[0:2]
        for i, item in enumerate(self.cont):
            self.assertEqual(item.index_at_parent, i,
                             "index not updated with remove")

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

    def test_indices_are_incorrect_after_eject(self):
        items = [roster.Node() for i in range(5)]
        self.cont[:] = items
        self.mock.mock_calls.clear()

        self.cont.eject(1, 3)

        self.assertNotEqual(self.cont[2].index_at_parent, 2)

    def test_indices_are_incorrect_after_inject(self):
        items = [roster.Node(), roster.Node(), roster.Node()]
        more_items = [roster.Node(),
                      roster.Node(),
                      roster.Node()]
        self.cont[:] = items
        self.mock.mock_calls.clear()

        def generate():
            yield from more_items

        self.cont.inject(1, generate())

        self.assertNotEqual(self.cont[2].index_at_parent, 2)

    def test_reindex_patches_incorrect_indices(self):
        items = [roster.Node(), roster.Node(), roster.Node()]
        more_items = [roster.Node(),
                      roster.Node(),
                      roster.Node()]
        self.cont[:] = items
        self.mock.mock_calls.clear()

        def generate():
            yield from more_items

        self.cont.inject(1, generate())
        self.cont.reindex()

        for i, item in enumerate(self.cont):
            self.assertEqual(item.index_at_parent, i)

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

    def test__root_changed_propagates_to_children(self):
        obj = unittest.mock.Mock()
        items = [roster.Node(), roster.Node(), roster.Node()]
        self.cont.extend(items)
        self.cont._add_to_parent(obj)
        self.assertEqual(items[0].root, obj.root)

    def test__root_changed_attaches_handlers_from_root(self):
        obj = unittest.mock.Mock()
        self.cont._add_to_parent(obj)
        self.assertEqual(
            self.cont.begin_insert_rows,
            obj.root.begin_insert_rows
        )
        self.assertEqual(
            self.cont.begin_move_rows,
            obj.root.begin_move_rows
        )
        self.assertEqual(
            self.cont.begin_remove_rows,
            obj.root.begin_remove_rows
        )
        self.assertEqual(
            self.cont.end_insert_rows,
            obj.root.end_insert_rows
        )
        self.assertEqual(
            self.cont.end_move_rows,
            obj.root.end_move_rows
        )
        self.assertEqual(
            self.cont.end_remove_rows,
            obj.root.end_remove_rows
        )

    def test__root_changed_detaches_handlers_from_root_if_None(self):
        obj = unittest.mock.Mock()
        self.cont._add_to_parent(obj)
        self.cont._remove_from_parent()
        self.assertIsNone(self.cont.begin_insert_rows)
        self.assertIsNone(self.cont.begin_move_rows)
        self.assertIsNone(self.cont.begin_remove_rows)
        self.assertIsNone(self.cont.end_insert_rows)
        self.assertIsNone(self.cont.end_move_rows)
        self.assertIsNone(self.cont.end_remove_rows)

    def tearDown(self):
        del self.cont


class TestVia(unittest.TestCase):
    def test_is_node(self):
        self.assertTrue(issubclass(
            roster.Via,
            roster.Node
        ))

    def setUp(self):
        self.item = aioxmpp.roster.Item(TEST_PEER_JID)
        self.via = roster.Via(
            TEST_ACCOUNT_JID,
            self.item
        )

    def test_init(self):
        self.assertEqual(self.via.account_jid, TEST_ACCOUNT_JID)
        self.assertIs(self.via.roster_item, self.item)

    def test_account_jid_not_writable(self):
        with self.assertRaises(AttributeError):
            self.via.account_jid = TEST_ACCOUNT_JID

    def test_roster_item_not_writable(self):
        with self.assertRaises(AttributeError):
            self.via.roster_item = self.item

    def test_label_not_writable(self):
        with self.assertRaises(AttributeError):
            self.via.label = "foo"

    def test_label_returns_jid_if_name_is_unset(self):
        self.assertEqual(self.via.label, str(self.item.jid))

    def test_label_returns_name_if_set(self):
        self.item.name = "fnord"
        self.assertEqual(self.via.label, self.item.name)

    def test_contact_supported_as_parent(self):
        contact = roster.Contact()
        self.assertTrue(self.via.parent_supported(contact))

    def test_node_not_supported_as_parent(self):
        self.assertFalse(self.via.parent_supported(roster.Node()))

    def tearDown(self):
        del self.via


class TestContact(unittest.TestCase):
    def test_is_container(self):
        self.assertTrue(issubclass(
            roster.Contact,
            roster.Container
        ))

    def test_is_node(self):
        self.assertTrue(issubclass(
            roster.Contact,
            roster.Node
        ))

    def setUp(self):
        self.item1 = aioxmpp.roster.Item(TEST_PEER_JID)
        self.via1 = roster.Via(
            TEST_ACCOUNT_JID,
            self.item1
        )

        self.item2 = aioxmpp.roster.Item(TEST_PEER_JID2)
        self.via2 = roster.Via(
            TEST_ACCOUNT_JID,
            self.item2
        )

        self.contact = roster.Contact()

    def test_init(self):
        self.assertIsNone(self.contact.label)

    def test_group_supported_as_parent(self):
        group = roster.Group("foo")
        self.assertTrue(self.contact.parent_supported(group))

    def test_container_not_supported_as_parent(self):
        container = roster.Container()
        self.assertFalse(self.contact.parent_supported(container))

    def test_label_delegates_to_first_child_if_unset(self):
        self.contact.extend([self.via1, self.via2])
        self.assertEqual(
            self.contact.label,
            self.via1.label
        )

    def test_label_can_be_overridden_before_adding_children(self):
        self.contact.label = "foo"
        self.assertEqual(self.contact.label, "foo")
        self.contact.extend([self.via1, self.via2])
        self.assertEqual(self.contact.label, "foo")

    def test_label_can_be_overridden_after_adding_children(self):
        self.contact.extend([self.via1, self.via2])
        self.contact.label = "foo"
        self.assertEqual(self.contact.label, "foo")

    def tearDown(self):
        del self.contact


class TestGroup(unittest.TestCase):
    def test_is_container(self):
        self.assertTrue(issubclass(
            roster.Group,
            roster.Container
        ))

    def test_is_node(self):
        self.assertTrue(issubclass(
            roster.Group,
            roster.Node
        ))

    def setUp(self):
        self.label = "foo"
        self.group = roster.Group(self.label)

    def test_label(self):
        self.assertEqual(self.label, self.group.label)

    def test_label_is_writable(self):
        self.group.label = "bar"
        self.assertEqual(self.group.label, "bar")

    def test_group_supported_as_parent(self):
        other_group = roster.Group("foo")
        self.assertTrue(self.group.parent_supported(other_group))

    def test_tree_supported_as_parent(self):
        tree_root = roster.TreeRoot()
        self.assertTrue(self.group.parent_supported(tree_root))

    def test_container_not_supported_as_parent(self):
        self.assertFalse(self.group.parent_supported(roster.Container()))

    def tearDown(self):
        del self.group


class TestTreeRoot(unittest.TestCase):
    def test_is_container(self):
        self.assertTrue(issubclass(
            roster.TreeRoot,
            roster.Container
        ))

    def setUp(self):
        self.mock = unittest.mock.Mock()
        self.root = roster.TreeRoot()

        self.root.begin_insert_rows = self.mock.begin_insert_rows
        self.root.end_insert_rows = self.mock.end_insert_rows
        self.root.begin_remove_rows = self.mock.begin_remove_rows
        self.root.end_remove_rows = self.mock.end_remove_rows
        self.root.begin_move_rows = self.mock.begin_move_rows
        self.root.end_move_rows = self.mock.end_move_rows

    def test_is_its_own_root(self):
        self.assertIs(self.root, self.root.root)

    def test__add_to_parent_raises_TypeError(self):
        obj = unittest.mock.Mock()
        with self.assertRaisesRegexp(
                TypeError,
                "cannot add TreeRoot to any parent"):
            self.root._add_to_parent(obj)

    def tearDown(self):
        del self.root


class TestTree(unittest.TestCase):
    def test_init(self):
        tree = roster.Tree()
        self.assertIsNone(tree.begin_insert_rows)
        self.assertIsNone(tree.begin_move_rows)
        self.assertIsNone(tree.begin_remove_rows)
        self.assertIsNone(tree.end_insert_rows)
        self.assertIsNone(tree.end_move_rows)
        self.assertIsNone(tree.end_remove_rows)

    def setUp(self):
        self.tree = roster.Tree()
        self.mock = unittest.mock.Mock()

        self.tree.begin_insert_rows = self.mock.begin_insert_rows
        self.tree.end_insert_rows = self.mock.end_insert_rows
        self.tree.begin_remove_rows = self.mock.begin_remove_rows
        self.tree.end_remove_rows = self.mock.end_remove_rows
        self.tree.begin_move_rows = self.mock.begin_move_rows
        self.tree.end_move_rows = self.mock.end_move_rows

    def test_root_is_tree_root(self):
        self.assertIsInstance(
            self.tree.root,
            roster.TreeRoot
        )

    def test_root_is_not_writable(self):
        with self.assertRaises(AttributeError):
            self.tree.root = object()

    def test_root_events_are_forwarded_to_tree_events(self):
        a1, b1, c1 = object(), object(), object()
        self.tree.root.begin_insert_rows(a1, b1, c1)

        a2, b2, c2, d2, e2 = object(), object(), object(), object(), object()
        self.tree.root.begin_move_rows(a2, b2, c2, d2, e2)

        a3, b3, c3 = object(), object(), object()
        self.tree.root.begin_remove_rows(a3, b3, c3)

        self.tree.root.end_insert_rows()
        self.tree.root.end_move_rows()
        self.tree.root.end_remove_rows()

        self.assertSequenceEqual(
            self.mock.mock_calls,
            [
                unittest.mock.call.begin_insert_rows(a1, b1, c1),
                unittest.mock.call.begin_move_rows(a2, b2, c2, d2, e2),
                unittest.mock.call.begin_remove_rows(a3, b3, c3),
                unittest.mock.call.end_insert_rows(),
                unittest.mock.call.end_move_rows(),
                unittest.mock.call.end_remove_rows(),
            ]
        )

    def tearDown(self):
        del self.tree


class TestTreeVisitor(unittest.TestCase):
    def test_is_visitor(self):
        self.assertTrue(issubclass(
            roster.TreeVisitor,
            visitor.Visitor
        ))

    def test_visits_children_of_containers(self):
        mock = unittest.mock.Mock()

        class Visitor(roster.TreeVisitor):
            @visitor.for_class(roster.Node)
            def test(self, item):
                mock(item)

        items = [roster.Node(), roster.Node()]
        cont = roster.Container(items)

        Visitor().visit(cont)

        self.assertSequenceEqual(
            mock.mock_calls,
            [
                unittest.mock.call(item)
                for item in items
            ]
        )

    def test_default_implementation_for_Node(self):
        roster.TreeVisitor().visit(roster.Node())


class Test_RosterConnector(unittest.TestCase):
    def test_init(self):
        base = unittest.mock.Mock()
        c = roster._RosterConnector(
            base.plugin,
            base.account,
            base.state)

        self.assertSequenceEqual(
            base.mock_calls,
            [
                unittest.mock.call.state.summon(
                    aioxmpp.roster.Service
                ),
                unittest.mock.call.state.summon(
                ).on_entry_added.connect(
                    c._on_entry_added
                ),
                unittest.mock.call.state.summon(
                ).on_entry_name_changed.connect(
                    c._on_entry_name_changed
                ),
                unittest.mock.call.state.summon(
                ).on_entry_added_to_group.connect(
                    c._on_entry_added_to_group
                ),
                unittest.mock.call.state.summon(
                ).on_entry_removed_from_group.connect(
                    c._on_entry_removed_from_group
                ),
                unittest.mock.call.state.summon(
                ).on_entry_removed.connect(
                    c._on_entry_removed
                )
            ]
        )

    def setUp(self):
        self.base = unittest.mock.Mock()
        self.c = roster._RosterConnector(
            self.base.plugin,
            self.base.account,
            self.base.state)
        self.base.mock_calls.clear()

    def test__on_entry_added(self):
        item = object()
        self.c._on_entry_added(item)

        self.assertSequenceEqual(
            self.base.mock_calls,
            [
                unittest.mock.call.plugin._on_entry_added(
                    self.base.account,
                    item
                )
            ]
        )

    def test__on_entry_name_changed(self):
        item = object()
        self.c._on_entry_name_changed(item)

        self.assertSequenceEqual(
            self.base.mock_calls,
            [
                unittest.mock.call.plugin._on_entry_name_changed(
                    self.base.account,
                    item
                )
            ]
        )

    def test__on_entry_added_to_group(self):
        item = object()
        name = object()
        self.c._on_entry_added_to_group(item, name)

        self.assertSequenceEqual(
            self.base.mock_calls,
            [
                unittest.mock.call.plugin._on_entry_added_to_group(
                    self.base.account,
                    item,
                    name,
                )
            ]
        )

    def test__on_entry_removed_from_group(self):
        item = object()
        name = object()
        self.c._on_entry_removed_from_group(item, name)

        self.assertSequenceEqual(
            self.base.mock_calls,
            [
                unittest.mock.call.plugin._on_entry_removed_from_group(
                    self.base.account,
                    item,
                    name,
                )
            ]
        )

    def test__on_entry_removed(self):
        item = object()
        self.c._on_entry_removed(item)

        self.assertSequenceEqual(
            self.base.mock_calls,
            [
                unittest.mock.call.plugin._on_entry_removed(
                    self.base.account,
                    item,
                )
            ]
        )

    def test_close(self):
        base = unittest.mock.Mock()
        c = roster._RosterConnector(
            base.plugin,
            base.account,
            base.state)
        c.close()

        calls = list(base.mock_calls)

        self.assertSequenceEqual(
            calls,
            [
                unittest.mock.call.state.summon(
                    aioxmpp.roster.Service
                ),
                unittest.mock.call.state.summon(
                ).on_entry_added.connect(
                    c._on_entry_added
                ),
                unittest.mock.call.state.summon(
                ).on_entry_name_changed.connect(
                    c._on_entry_name_changed
                ),
                unittest.mock.call.state.summon(
                ).on_entry_added_to_group.connect(
                    c._on_entry_added_to_group
                ),
                unittest.mock.call.state.summon(
                ).on_entry_removed_from_group.connect(
                    c._on_entry_removed_from_group
                ),
                unittest.mock.call.state.summon(
                ).on_entry_removed.connect(
                    c._on_entry_removed
                ),
                unittest.mock.call.state.summon(
                ).on_entry_added.disconnect(
                    base.state.summon().on_entry_added.connect()
                ),
                unittest.mock.call.state.summon(
                ).on_entry_name_changed.disconnect(
                    base.state.summon().on_entry_name_changed.connect()
                ),
                unittest.mock.call.state.summon(
                ).on_entry_added_to_group.disconnect(
                    base.state.summon().on_entry_added_to_group.connect()
                ),
                unittest.mock.call.state.summon(
                ).on_entry_removed_from_group.disconnect(
                    base.state.summon().on_entry_removed_from_group.connect()
                ),
                unittest.mock.call.state.summon(
                ).on_entry_removed.disconnect(
                    base.state.summon().on_entry_removed.connect()
                )
            ]
        )

    def tearDown(self):
        del self.c
        del self.base


class Test_EraseVia(unittest.TestCase):
    def setUp(self):
        self.item = aioxmpp.roster.Item(TEST_PEER_JID)
        self.v = roster._EraseVia(self.item)

    def test_delete_empty_contact_at_parent(self):
        tree = roster.Group(
            "foo",
            initial=[
                roster.Contact(initial=[
                    roster.Via(TEST_ACCOUNT_JID, self.item)
                ]),
            ]
        )
        self.v.visit(tree)
        self.assertEqual(len(tree), 0)

    def test_keep_nonempty_contact_and_delete_via(self):
        other_item = aioxmpp.roster.Item(TEST_PEER_JID)
        tree = roster.Group(
            "foo",
            initial=[
                roster.Contact(initial=[
                    roster.Via(TEST_ACCOUNT_JID, self.item),
                    roster.Via(TEST_ACCOUNT_JID, other_item)
                ]),
            ]
        )
        self.v.visit(tree)
        self.assertEqual(len(tree), 1)
        self.assertEqual(len(tree[0]), 1)
        self.assertIs(
            tree[0][0].roster_item,
            other_item,
        )

    def test_keep_same_peer_on_different_account(self):
        tree = roster.Group(
            "foo",
            initial=[
                roster.Contact(initial=[
                    roster.Via(TEST_ACCOUNT_JID.replace(localpart="X"),
                               aioxmpp.roster.Item(TEST_PEER_JID))
                ]),
            ]
        )
        self.v.visit(tree)
        self.assertEqual(len(tree), 1)

    def tearDown(self):
        del self.v


class TestPlugin(unittest.TestCase):
    def test_is_plugin(self):
        self.assertTrue(issubclass(
            roster.Plugin,
            plugin.Base
        ))

    def setUp(self):
        self.c = ClientMock()
        self.r = roster.Plugin(self.c)

    # def test_connect_to_account_signals(self):
    #     c = ClientMock()
    #     with contextlib.ExitStack() as stack:
    #         on_account_enabled = stack.enter_context(
    #             unittest.mock.patch.object(
    #                 c,
    #                 "on_account_enabling")
    #         )
    #         on_account_disabled = stack.enter_context(
    #             unittest.mock.patch.object(
    #                 c,
    #                 "on_account_disabling")
    #         )

    #         r = roster.Plugin(c)

    #     on_account_enabled.connect.assert_called_with(
    #         r._on_account_enabling
    #     )

    def test__on_account_enabling_summons_roster(self):
        base = unittest.mock.Mock()
        with unittest.mock.patch("mlxc.roster._RosterConnector",
                                 new=base.connector):
            self.r._on_account_enabling(
                base.account,
                base.state)

        calls = list(base.mock_calls)
        self.assertSequenceEqual(
            calls,
            [
                unittest.mock.call.connector(
                    self.r,
                    base.account,
                    base.state)
            ]
        )

    def test__on_account_disabling_disconnects_from_roster(self):
        base = unittest.mock.Mock()
        with unittest.mock.patch("mlxc.roster._RosterConnector",
                                 new=base.connector):
            self.r._on_account_enabling(
                base.account,
                base.state)
            self.r._on_account_disabling(
                base.account,
                base.state,
                reason=None)


        calls = list(base.mock_calls)
        self.assertSequenceEqual(
            calls,
            [
                unittest.mock.call.connector(
                    self.r,
                    base.account,
                    base.state),
                unittest.mock.call.connector().close()
            ]
        )

    def test__on_account_disabling_twice_is_noop(self):
        base = unittest.mock.Mock()
        with unittest.mock.patch("mlxc.roster._RosterConnector",
                                 new=base.connector):
            self.r._on_account_enabling(
                base.account,
                base.state)
            self.r._on_account_disabling(
                base.account,
                base.state,
                reason=None)
            self.r._on_account_disabling(
                base.account,
                base.state,
                reason=None)


        calls = list(base.mock_calls)
        self.assertSequenceEqual(
            calls,
            [
                unittest.mock.call.connector(
                    self.r,
                    base.account,
                    base.state),
                unittest.mock.call.connector().close()
            ]
        )

    def test__on_entry_added_creates_groups_and_contacts_and_vias(self):
        account = unittest.mock.Mock(["jid"])
        account.jid = TEST_ACCOUNT_JID
        item = aioxmpp.roster.Item(
            TEST_PEER_JID,
            name="Foobar",
            groups={"A", "B"}
        )
        self.r._on_entry_added(account, item)

        self.assertEqual(len(self.c.roster.root), 2)
        self.assertIsInstance(
            self.c.roster.root[0],
            roster.Group)
        self.assertIsInstance(
            self.c.roster.root[1],
            roster.Group)

        self.assertSetEqual(
            set(group.label for group in self.c.roster.root),
            {"A",  "B"}
        )

        self.assertSetEqual(
            set(self.r.group_map),
            {"A", "B"},
        )

        for group in self.c.roster.root:
            self.assertEqual(len(group), 1)
            contact = group[0]
            self.assertIsInstance(contact, roster.Contact)
            self.assertEqual(len(contact), 1)
            via = contact[0]
            self.assertIsInstance(via, roster.Via)
            self.assertEqual(via.account_jid, account.jid)
            self.assertIs(via.roster_item, item)

    def test__on_entry_added_reuses_existing_groups(self):
        account = unittest.mock.Mock(["jid"])
        account.jid = TEST_ACCOUNT_JID
        item1 = aioxmpp.roster.Item(
            TEST_PEER_JID,
            name="Foobar",
            groups={"A", "B"}
        )
        self.r._on_entry_added(account, item1)
        item2 = aioxmpp.roster.Item(
            TEST_PEER_JID.replace(localpart="c"),
            name="Baz",
            groups={"A", "C"}
        )
        self.r._on_entry_added(account, item2)

        self.assertEqual(len(self.c.roster.root), 3)
        self.assertIsInstance(
            self.c.roster.root[0],
            roster.Group)
        self.assertIsInstance(
            self.c.roster.root[1],
            roster.Group)
        self.assertIsInstance(
            self.c.roster.root[2],
            roster.Group)

        self.assertSetEqual(
            set(group.label for group in self.c.roster.root),
            {"A",  "B", "C"}
        )

        self.assertSetEqual(
            set(self.r.group_map),
            {"A", "B", "C"},
        )

        group = self.r.group_map["B"]
        self.assertEqual(len(group), 1)
        contact = group[0]
        self.assertIsInstance(contact, roster.Contact)
        self.assertEqual(len(contact), 1)
        via = contact[0]
        self.assertIsInstance(via, roster.Via)
        self.assertIs(via.roster_item, item1)

        group = self.r.group_map["C"]
        self.assertEqual(len(group), 1)
        contact = group[0]
        self.assertIsInstance(contact, roster.Contact)
        self.assertEqual(len(contact), 1)
        via = contact[0]
        self.assertIsInstance(via, roster.Via)
        self.assertEqual(via.roster_item, item2)

        group = self.r.group_map["A"]
        self.assertEqual(len(group), 2)
        for contact in group:
            self.assertIsInstance(contact, roster.Contact)
            self.assertEqual(len(contact), 1)

        self.assertSetEqual(
            set(via.roster_item for contact in group for via in contact),
            {item1, item2}
        )

    def test__on_entry_added_to_group_creates_group(self):
        account = unittest.mock.Mock(["jid"])
        account.jid = TEST_ACCOUNT_JID
        item1 = aioxmpp.roster.Item(
            TEST_PEER_JID,
            name="Foobar",
            groups={"A"},
        )
        self.r._on_entry_added(account, item1)

        self.assertEqual(len(self.c.roster.root), 1)

        self.r._on_entry_added_to_group(account, item1, "B")

        self.assertEqual(len(self.c.roster.root), 2)
        self.assertIsInstance(
            self.c.roster.root[0],
            roster.Group)
        self.assertIsInstance(
            self.c.roster.root[1],
            roster.Group)

        self.assertSetEqual(
            set(group.label for group in self.c.roster.root),
            {"A",  "B"}
        )

        self.assertSetEqual(
            set(self.r.group_map),
            {"A", "B"},
        )

        for group in self.c.roster.root:
            self.assertEqual(len(group), 1)
            contact = group[0]
            self.assertIsInstance(contact, roster.Contact)
            self.assertEqual(len(contact), 1)
            via = contact[0]
            self.assertIsInstance(via, roster.Via)
            self.assertEqual(via.account_jid, account.jid)
            self.assertIs(via.roster_item, item1)

    def test__on_entry_removed_from_group_uses__EraseVia_on_group(self):
        account = unittest.mock.Mock(["jid"])
        account.jid = TEST_ACCOUNT_JID
        item = aioxmpp.roster.Item(
            TEST_PEER_JID,
            name="Foobar",
            groups={"A", "B"},
        )
        self.r._on_entry_added(account, item)

        with unittest.mock.patch("mlxc.roster._EraseVia") as _EraseVia:
            self.r._on_entry_removed_from_group(account, item, "B")

        self.assertSequenceEqual(
            _EraseVia.mock_calls,
            [
                unittest.mock.call(item),
                unittest.mock.call().visit(self.r.group_map["B"])
            ]
        )

    def test__on_entry_removed_uses__EraseVia_on_whole_tree(self):
        account = unittest.mock.Mock(["jid"])
        account.jid = TEST_ACCOUNT_JID
        item = aioxmpp.roster.Item(
            TEST_PEER_JID,
            name="Foobar",
            groups={"A", "B"},
        )
        self.r._on_entry_added(account, item)

        with unittest.mock.patch("mlxc.roster._EraseVia") as _EraseVia:
            self.r._on_entry_removed(account, item)

        self.assertSequenceEqual(
            _EraseVia.mock_calls,
            [
                unittest.mock.call(item),
                unittest.mock.call().visit(self.c.roster.root)
            ]
        )

    def test_connect_to_initially_enabled_accounts(self):
        c = ClientMock()
        acc1 = c.accounts.new_account(TEST_ACCOUNT_JID)
        acc2 = c.accounts.new_account(
            TEST_ACCOUNT_JID.replace(domain="bar.baz"))
        c.accounts.set_account_enabled(acc1.jid, True)

        with unittest.mock.patch.object(
                roster.Plugin,
                "_on_account_enabling") as on_account_enabling:
            r = roster.Plugin(c)

        self.assertSequenceEqual(
            on_account_enabling.mock_calls,
            [
                unittest.mock.call(acc1, c.account_state(acc1)),
            ]
        )

    def test_connect_to_client_events_on_init(self):
        c = ClientMock()
        with contextlib.ExitStack() as stack:
            on_account_enabling = stack.enter_context(
                unittest.mock.patch.object(
                    c.on_account_enabling,
                    "connect"
                )
            )
            on_account_disabling = stack.enter_context(
                unittest.mock.patch.object(
                    c.on_account_disabling,
                    "connect"
                )
            )

            r = roster.Plugin(c)

        on_account_enabling.assert_called_with(
            r._on_account_enabling
        )

        on_account_disabling.assert_called_with(
            r._on_account_disabling
        )

    def test_disconnect_from_client_events_on_close(self):
        c = ClientMock()
        with contextlib.ExitStack() as stack:
            on_account_enabling = stack.enter_context(
                unittest.mock.patch.object(
                    c,
                    "on_account_enabling"
                )
            )
            on_account_disabling = stack.enter_context(
                unittest.mock.patch.object(
                    c,
                    "on_account_disabling"
                )
            )

            r = roster.Plugin(c)
            aioxmpp.testutils.run_coroutine(r.close())

        on_account_enabling.disconnect.assert_called_with(
            on_account_enabling.connect()
        )

        on_account_disabling.disconnect.assert_called_with(
            on_account_disabling.connect()
        )

    def tearDown(self):
        del self.r
        del self.c
