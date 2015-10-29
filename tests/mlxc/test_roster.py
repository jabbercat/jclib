import contextlib
import unittest
import unittest.mock

import aioxmpp.roster
import aioxmpp.structs

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

    def test_parent_supported(self):
        self.assertFalse(self.item.parent_supported(object()))

    def test__remove_from_parent_sets_parent_to_None(self):
        obj = object()
        self.item._add_to_parent(obj)
        self.item._remove_from_parent()
        self.assertIsNone(self.item.parent)

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


class TestVia(unittest.TestCase):
    def test_is_node(self):
        self.assertTrue(issubclass(
            roster.Via,
            roster.Node
        ))

    def setUp(self):
        self.via = roster.Via(
            TEST_ACCOUNT_JID,
            TEST_PEER_JID
        )

    def test_init(self):
        self.assertEqual(self.via.account_jid, TEST_ACCOUNT_JID)
        self.assertEqual(self.via.peer_jid, TEST_PEER_JID)

    def test_account_jid_not_writable(self):
        with self.assertRaises(AttributeError):
            self.via.account_jid = TEST_ACCOUNT_JID

    def test_peer_jid_not_writable(self):
        with self.assertRaises(AttributeError):
            self.via.peer_jid = TEST_PEER_JID

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
        self.contact = roster.Contact()

    def test_group_supported_as_parent(self):
        group = roster.Group("foo")
        self.assertTrue(self.contact.parent_supported(group))

    def test_container_not_supported_as_parent(self):
        container = roster.Container()
        self.assertFalse(self.contact.parent_supported(container))

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


class TestTree(unittest.TestCase):
    def setUp(self):
        self.tree = roster.Tree()

    def test_root_is_tree_root(self):
        self.assertIsInstance(
            self.tree.root,
            roster.TreeRoot
        )

    def test_root_is_not_writable(self):
        with self.assertRaises(AttributeError):
            self.tree.root = object()

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
            self.assertEqual(via.peer_jid, TEST_PEER_JID)

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
        self.assertEqual(via.peer_jid, item1.jid)

        group = self.r.group_map["C"]
        self.assertEqual(len(group), 1)
        contact = group[0]
        self.assertIsInstance(contact, roster.Contact)
        self.assertEqual(len(contact), 1)
        via = contact[0]
        self.assertIsInstance(via, roster.Via)
        self.assertEqual(via.peer_jid, item2.jid)

        group = self.r.group_map["A"]
        self.assertEqual(len(group), 2)
        for contact in group:
            self.assertIsInstance(contact, roster.Contact)
            self.assertEqual(len(contact), 1)

        self.assertSetEqual(
            set(via.peer_jid for contact in group for via in contact),
            {item1.jid, item2.jid}
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
            self.assertEqual(via.peer_jid, TEST_PEER_JID)

    def tearDown(self):
        del self.r
        del self.c
