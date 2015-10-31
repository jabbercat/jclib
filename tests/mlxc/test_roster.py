import contextlib
import unittest
import unittest.mock

import aioxmpp.presence
import aioxmpp.roster
import aioxmpp.structs
import aioxmpp.testutils
import aioxmpp.utils

import mlxc.config
import mlxc.instrumentable_list as ilist
import mlxc.plugin as plugin
import mlxc.roster as roster
import mlxc.visitor as visitor

from mlxc.utils import mlxc_namespaces

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


class DummyNode(roster.Node):
    def to_xso(self):
        pass


class DummyContainer(roster.Container):
    def to_xso(self):
        pass


class TestNode(unittest.TestCase):
    def test_is_abstract(self):
        with self.assertRaisesRegexp(TypeError, "abstract.*to_xso"):
            node = roster.Node()

    def test_init_default(self):
        item = DummyNode()
        self.assertIsNone(item.parent)
        self.assertIsNone(item.index_at_parent)
        self.assertIsNone(item.root)

    def setUp(self):
        self.item = DummyNode()

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
        self.cont = DummyContainer()
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
        items = [DummyNode(), DummyNode()]
        new_items = [DummyNode()]
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
        items = [DummyNode(), DummyNode(), DummyNode()]
        self.cont.extend(items)
        for i, item in enumerate(self.cont):
            self.assertEqual(item.index_at_parent, i,
                             "index not set on extend")

        self.cont.move(2, 0)
        for i, item in enumerate(self.cont):
            self.assertEqual(item.index_at_parent, i,
                             "index not updated with move")

    def test_indices_are_set_and_updated_on_forward_move(self):
        items = [DummyNode(), DummyNode(), DummyNode()]
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
        items = [DummyNode(), DummyNode(), DummyNode()]
        self.cont.extend(items)
        for i, item in enumerate(self.cont):
            self.assertEqual(item.index_at_parent, i,
                             "index not set on extend")

        del self.cont[0:2]
        for i, item in enumerate(self.cont):
            self.assertEqual(item.index_at_parent, i,
                             "index not updated with remove")

    def test_inject_does_not_emit_model_events_but_emits_register(self):
        items = [DummyNode(), DummyNode(), DummyNode()]
        more_items = [DummyNode(),
                      DummyNode(),
                      DummyNode()]
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
        items = [DummyNode() for i in range(5)]
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
        items = [DummyNode() for i in range(5)]
        self.cont[:] = items
        self.mock.mock_calls.clear()

        self.cont.eject(1, 3)

        self.assertNotEqual(self.cont[2].index_at_parent, 2)

    def test_indices_are_incorrect_after_inject(self):
        items = [DummyNode(), DummyNode(), DummyNode()]
        more_items = [DummyNode(),
                      DummyNode(),
                      DummyNode()]
        self.cont[:] = items
        self.mock.mock_calls.clear()

        def generate():
            yield from more_items

        self.cont.inject(1, generate())

        self.assertNotEqual(self.cont[2].index_at_parent, 2)

    def test_reindex_patches_incorrect_indices(self):
        items = [DummyNode(), DummyNode(), DummyNode()]
        more_items = [DummyNode(),
                      DummyNode(),
                      DummyNode()]
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
        cont = DummyContainer([obj])
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
        items = [DummyNode(), DummyNode(), DummyNode()]
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
        self.via = roster.Via(
            TEST_ACCOUNT_JID,
            TEST_PEER_JID
        )

    def test_init(self):
        self.assertEqual(self.via.account_jid, TEST_ACCOUNT_JID)
        self.assertIsNone(self.via.roster_item)

        self.assertIs(self.via.peer_jid, TEST_PEER_JID)
        self.assertIsNone(self.via.name)
        self.assertEqual(self.via.subscription, "none")
        self.assertFalse(self.via.approved)
        self.assertIsNone(self.via.ask)

    def test_init_with_roster_item(self):
        item = aioxmpp.roster.Item(TEST_PEER_JID)
        via = roster.Via(TEST_ACCOUNT_JID, item)
        self.assertEqual(via.account_jid, TEST_ACCOUNT_JID)
        self.assertIs(via.roster_item, item)

        item.subscription = "both"
        item.ask = "subscribe"
        item.approved = True
        item.name = "foo"

        self.assertIs(via.peer_jid, item.jid)
        self.assertIs(via.name, item.name)
        self.assertIs(via.subscription, item.subscription)
        self.assertIs(via.approved, item.approved)

    def test_account_jid_not_writable(self):
        with self.assertRaises(AttributeError):
            self.via.account_jid = TEST_ACCOUNT_JID

    def test_peer_jid_not_writable(self):
        with self.assertRaises(AttributeError):
            self.via.peer_jid = TEST_PEER_JID

    def test_label_not_writable(self):
        with self.assertRaises(AttributeError):
            self.via.label = "foo"

    def test_name_not_writable(self):
        with self.assertRaises(AttributeError):
            self.via.name = "foo"

    def test_subscription_not_writable(self):
        with self.assertRaises(AttributeError):
            self.via.subscription = "none"

    def test_approved_not_writable(self):
        with self.assertRaises(AttributeError):
            self.via.approved = True

    def test_setting_roster_item_to_none_latches(self):
        via = roster.Via(TEST_ACCOUNT_JID, TEST_PEER_JID)
        self.assertEqual(via.account_jid, TEST_ACCOUNT_JID)

        item = aioxmpp.roster.Item(TEST_PEER_JID)
        via.roster_item = item
        item.subscription = "both"
        item.ask = "subscribe"
        item.approved = True
        item.name = "foo"

        self.assertIs(via.peer_jid, item.jid)
        self.assertIs(via.label, item.name)
        self.assertIs(via.subscription, item.subscription)
        self.assertIs(via.approved, item.approved)

        via.roster_item = None

        self.assertIsNone(via.roster_item)
        self.assertEqual(via.peer_jid, item.jid)
        self.assertEqual(via.name, item.name)
        self.assertEqual(via.subscription, item.subscription)
        self.assertEqual(via.approved, item.approved)

    def test_setting_roster_item_redirects_other_attributes(self):
        via = roster.Via(TEST_ACCOUNT_JID, TEST_PEER_JID)
        self.assertEqual(via.account_jid, TEST_ACCOUNT_JID)

        item = aioxmpp.roster.Item(TEST_PEER_JID)
        via.roster_item = item
        item.subscription = "both"
        item.ask = "subscribe"
        item.approved = True
        item.name = "foo"

        self.assertIs(via.peer_jid, item.jid)
        self.assertIs(via.label, item.name)
        self.assertIs(via.subscription, item.subscription)
        self.assertIs(via.approved, item.approved)

    def test_label_returns_jid_if_name_is_unset(self):
        item = aioxmpp.roster.Item(TEST_PEER_JID)
        self.via.roster_item = item
        self.assertEqual(self.via.label, str(item.jid))

    def test_label_returns_name_if_set(self):
        item = aioxmpp.roster.Item(TEST_PEER_JID)
        item.name = "fnord"
        self.via.roster_item = item
        self.assertEqual(self.via.label, item.name)

    def test_metacontact_supported_as_parent(self):
        contact = roster.MetaContact()
        self.assertTrue(self.via.parent_supported(contact))

    def test_group_supported_as_parent(self):
        group = roster.Group("foo")
        self.assertTrue(self.via.parent_supported(group))

    def test_node_not_supported_as_parent(self):
        self.assertFalse(self.via.parent_supported(DummyNode()))

    def test_xso_round_trip(self):
        via = roster.Via(TEST_ACCOUNT_JID, TEST_PEER_JID)
        self.assertEqual(via.account_jid, TEST_ACCOUNT_JID)

        item = aioxmpp.roster.Item(TEST_PEER_JID)
        via.roster_item = item
        item.subscription = "both"
        item.ask = "subscribe"
        item.approved = True
        item.name = "foo"
        via.roster_item = None

        # the above fills the via with some interesting data

        xso = via.to_xso()
        new_via = xso.to_object()
        for attr in [
                "account_jid",
                "peer_jid",
                "name",
                "label",
                "subscription",
                "approved",
                "name",
            ]:
            self.assertEqual(
                getattr(via, attr),
                getattr(new_via, attr),
                "attribute {}".format(attr)
            )

    def tearDown(self):
        del self.via


class TestVia_XSORepr(unittest.TestCase):
    def test_is_roster_item_xso(self):
        self.assertTrue(issubclass(
            roster.Via.XSORepr,
            aioxmpp.roster.xso.Item
        ))

    def test_tag(self):
        self.assertEqual(
            roster.Via.XSORepr.TAG,
            (mlxc_namespaces.roster, "via")
        )

    def test_account_jid(self):
        self.assertIsInstance(
            roster.Via.XSORepr.account_jid,
            aioxmpp.xso.Attr
        )
        self.assertEqual(
            roster.Via.XSORepr.account_jid.tag,
            (None, "account")
        )
        self.assertIsInstance(
            roster.Via.XSORepr.account_jid.type_,
            aioxmpp.xso.JID
        )
        self.assertIs(
            roster.Via.XSORepr.account_jid.default,
            aioxmpp.xso.NO_DEFAULT
        )

    def test_can_be_child_of_metacontact(self):
        self.assertIs(
            roster.MetaContact.XSORepr.CHILD_MAP[roster.Via.XSORepr.TAG],
            roster.MetaContact.XSORepr.children
        )
        self.assertIn(
            roster.Via.XSORepr,
            roster.MetaContact.XSORepr.children._classes,
        )

    def test_can_be_child_of_group(self):
        self.assertIs(
            roster.Group.XSORepr.CHILD_MAP[roster.Via.XSORepr.TAG],
            roster.Group.XSORepr.children
        )
        self.assertIn(
            roster.Via.XSORepr,
            roster.Group.XSORepr.children._classes,
        )


class TestMetaContact(unittest.TestCase):
    def test_is_container(self):
        self.assertTrue(issubclass(
            roster.MetaContact,
            roster.Container
        ))

    def test_is_node(self):
        self.assertTrue(issubclass(
            roster.MetaContact,
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

        self.contact = roster.MetaContact()

    def test_init(self):
        self.assertIsNone(self.contact.label)

    def test_group_supported_as_parent(self):
        group = roster.Group("foo")
        self.assertTrue(self.contact.parent_supported(group))

    def test_container_not_supported_as_parent(self):
        container = DummyContainer()
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

    def test_xso_roundtrip(self):
        self.contact.extend([self.via1, self.via2])
        self.contact.label = "foobar"

        xso = self.contact.to_xso()
        self.assertIsInstance(xso, roster.MetaContact.XSORepr)
        new_contact = xso.to_object()

        self.assertEqual(new_contact.label, self.contact.label)
        self.assertEqual(len(new_contact), 2)

        for v1, v2 in zip(self.contact, new_contact):
            self.assertIsInstance(v2, roster.Via)
            self.assertEqual(v1.account_jid, v2.account_jid)
            self.assertEqual(v1.peer_jid, v2.peer_jid)


    def tearDown(self):
        del self.contact


class TestMetaContact_XSORepr(unittest.TestCase):
    def test_is_xso(self):
        self.assertTrue(issubclass(
            roster.MetaContact.XSORepr,
            aioxmpp.xso.XSO
        ))

    def test_tag(self):
        self.assertEqual(
            roster.MetaContact.XSORepr.TAG,
            (mlxc_namespaces.roster, "meta")
        )

    def test_label(self):
        self.assertIsInstance(
            roster.MetaContact.XSORepr.label,
            aioxmpp.xso.Attr
        )
        self.assertEqual(
            roster.MetaContact.XSORepr.label.tag,
            (None, "label"),
        )
        self.assertIsNone(roster.MetaContact.XSORepr.label.default)

    def test_children(self):
        self.assertIsInstance(
            roster.MetaContact.XSORepr.children,
            aioxmpp.xso.ChildList
        )

    def test_can_be_child_of_group(self):
        self.assertIs(
            roster.Group.XSORepr.CHILD_MAP[roster.MetaContact.XSORepr.TAG],
            roster.Group.XSORepr.children
        )
        self.assertIn(
            roster.MetaContact.XSORepr,
            roster.Group.XSORepr.children._classes,
        )


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
        self.assertFalse(self.group.parent_supported(DummyContainer()))

    def test_xso_roundtrip(self):
        group = roster.Group(
            "foo",
            initial=[
                roster.Group(
                    "bar",
                    initial=[
                        roster.Via(TEST_ACCOUNT_JID, TEST_PEER_JID),
                        roster.Via(TEST_ACCOUNT_JID, TEST_PEER_JID2),
                    ]
                ),
                roster.MetaContact(
                    initial=[
                        roster.Via(TEST_ACCOUNT_JID, TEST_PEER_JID),
                        roster.Via(TEST_ACCOUNT_JID, TEST_PEER_JID2),
                    ]
                )
            ]
        )

        xso = group.to_xso()
        self.assertIsInstance(xso, roster.Group.XSORepr)
        new_group = xso.to_object()

        self.assertEqual(len(group), len(new_group))
        for c1, c2 in zip(group, new_group):
            self.assertIs(type(c1), type(c2))
            self.assertEqual(len(c1), len(c2))
            if isinstance(c1, roster.Group):
                self.assertEqual(c1.label, c2.label)
            for cc1, cc2 in zip(c1, c2):
                self.assertIs(type(c1), type(c2))
                self.assertEqual(cc1.account_jid, cc1.account_jid)
                self.assertEqual(cc2.peer_jid, cc2.peer_jid)

    def tearDown(self):
        del self.group


class TestGroup_XSORepr(unittest.TestCase):
    def test_is_xso(self):
        self.assertTrue(issubclass(
            roster.Group.XSORepr,
            aioxmpp.xso.XSO
        ))

    def test_tag(self):
        self.assertEqual(
            roster.Group.XSORepr.TAG,
            (mlxc_namespaces.roster, "group")
        )

    def test_label(self):
        self.assertIsInstance(
            roster.Group.XSORepr.label,
            aioxmpp.xso.Attr
        )
        self.assertEqual(
            roster.Group.XSORepr.label.tag,
            (None, "label")
        )
        self.assertIs(
            roster.Group.XSORepr.label.default,
            aioxmpp.xso.NO_DEFAULT
        )

    def test_children(self):
        self.assertIsInstance(
            roster.Group.XSORepr.children,
            aioxmpp.xso.ChildList
        )

    def test_can_be_child_of_itself(self):
        self.assertIs(
            roster.Group.XSORepr.CHILD_MAP[roster.Group.XSORepr.TAG],
            roster.Group.XSORepr.children
        )
        self.assertIn(
            roster.Group.XSORepr,
            roster.Group.XSORepr.children._classes,
        )


    def test_can_be_child_of_tree_root(self):
        self.assertIs(
            roster.TreeRoot.XSORepr.CHILD_MAP[roster.Group.XSORepr.TAG],
            roster.TreeRoot.XSORepr.children
        )
        self.assertIn(
            roster.Group.XSORepr,
            roster.TreeRoot.XSORepr.children._classes,
        )


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

    def test_xso_roundtrip(self):
        self.root.append(roster.Group("foo"))

        xso = self.root.to_xso()
        self.assertIsInstance(xso, roster.TreeRoot.XSORepr)
        new_root = roster.TreeRoot()
        new_root.append(roster.Group("bar"))
        new_root.load_from_xso(xso)

        self.assertEqual(len(new_root), len(self.root))
        self.assertEqual(new_root[0].label, self.root[0].label)

    def tearDown(self):
        del self.root


class TestTreeRoot_XSORepr(unittest.TestCase):
    def test_is_xso(self):
        self.assertTrue(issubclass(
            roster.TreeRoot.XSORepr,
            aioxmpp.xso.XSO
        ))

    def test_tag(self):
        self.assertEqual(
            roster.TreeRoot.XSORepr.TAG,
            (mlxc_namespaces.roster, "tree")
        )

    def test_declare_ns(self):
        self.assertDictEqual(
            roster.TreeRoot.XSORepr.DECLARE_NS,
            {
                None: mlxc_namespaces.roster,
                "xmpp": aioxmpp.utils.namespaces.rfc6121_roster
            }
        )

    def test_children(self):
        self.assertIsInstance(
            roster.TreeRoot.XSORepr.children,
            aioxmpp.xso.ChildList
        )


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

        items = [DummyNode(), DummyNode()]
        cont = DummyContainer(items)

        Visitor().visit(cont)

        self.assertSequenceEqual(
            mock.mock_calls,
            [
                unittest.mock.call(item)
                for item in items
            ]
        )

    def test_default_implementation_for_Node(self):
        roster.TreeVisitor().visit(DummyNode())


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
                ),
                unittest.mock.call.state.summon(
                    aioxmpp.presence.Service
                ),
                unittest.mock.call.state.summon(
                ).on_available.connect(
                    c._on_resource_available
                ),
                unittest.mock.call.state.summon(
                ).on_changed.connect(
                    c._on_resource_presence_changed
                ),
                unittest.mock.call.state.summon(
                ).on_unavailable.connect(
                    c._on_resource_unavailable
                ),
            ]
        )

        self.assertEqual(
            c.roster_service,
            base.state.summon()
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

    def test__on_resource_available(self):
        full_jid, stanza = object(), object()
        self.c._on_resource_available(full_jid, stanza)

        self.assertSequenceEqual(
            self.base.mock_calls,
            [
                unittest.mock.call.plugin._on_resource_available(
                    self.base.account,
                    full_jid,
                    stanza,
                )
            ]
        )

    def test__on_resource_presence_changed(self):
        full_jid, stanza = object(), object()
        self.c._on_resource_presence_changed(full_jid, stanza)

        self.assertSequenceEqual(
            self.base.mock_calls,
            [
                unittest.mock.call.plugin._on_resource_presence_changed(
                    self.base.account,
                    full_jid,
                    stanza,
                )
            ]
        )

    def test__on_resource_unavailable(self):
        full_jid, stanza = object(), object()
        self.c._on_resource_unavailable(full_jid, stanza)

        self.assertSequenceEqual(
            self.base.mock_calls,
            [
                unittest.mock.call.plugin._on_resource_unavailable(
                    self.base.account,
                    full_jid,
                    stanza,
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
                    aioxmpp.presence.Service
                ),
                unittest.mock.call.state.summon(
                ).on_available.connect(
                    c._on_resource_available
                ),
                unittest.mock.call.state.summon(
                ).on_changed.connect(
                    c._on_resource_presence_changed
                ),
                unittest.mock.call.state.summon(
                ).on_unavailable.connect(
                    c._on_resource_unavailable
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
                ),
                unittest.mock.call.state.summon(
                ).on_available.disconnect(
                    base.state.summon().on_available.connect()
                ),
                unittest.mock.call.state.summon(
                ).on_changed.disconnect(
                    base.state.summon().on_changed.connect()
                ),
                unittest.mock.call.state.summon(
                ).on_unavailable.disconnect(
                    base.state.summon().on_unavailable.connect()
                ),
            ]
        )

    def tearDown(self):
        del self.c
        del self.base


class Test_EraseVia(unittest.TestCase):
    def setUp(self):
        self.item = aioxmpp.roster.Item(TEST_PEER_JID)
        self.v = roster._EraseVia(self.item)

    def test_init_defaults(self):
        self.assertTrue(self.v.deep)

    def test_init(self):
        v = roster._EraseVia(self.item, deep=False)
        self.assertFalse(v.deep)

    def test_delete_empty_metacontact_at_parent(self):
        tree = roster.Group(
            "foo",
            initial=[
                roster.MetaContact(initial=[
                    roster.Via(TEST_ACCOUNT_JID, self.item)
                ]),
            ]
        )
        self.v.visit(tree)
        self.assertEqual(len(tree), 0)

    def test_delete_at_group(self):
        tree = roster.Group(
            "foo",
            initial=[
                roster.Via(TEST_ACCOUNT_JID, self.item)
            ]
        )
        self.v.visit(tree)
        self.assertEqual(len(tree), 0)

    def test_keep_nonempty_metacontact_and_delete_via(self):
        other_item = aioxmpp.roster.Item(TEST_PEER_JID)
        tree = roster.Group(
            "foo",
            initial=[
                roster.MetaContact(initial=[
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
                roster.MetaContact(initial=[
                    roster.Via(TEST_ACCOUNT_JID.replace(localpart="X"),
                               aioxmpp.roster.Item(TEST_PEER_JID))
                ]),
            ]
        )
        self.v.visit(tree)
        self.assertEqual(len(tree), 1)

    def test_do_not_descend_into_subgroups_if_deep_is_false(self):
        self.v.deep = False
        tree = roster.Group(
            "foo",
            initial=[
                roster.Group(
                    "bar",
                    initial=[
                        roster.Via(TEST_ACCOUNT_JID, self.item),
                    ]
                ),
                roster.MetaContact(initial=[
                    roster.Via(TEST_ACCOUNT_JID, self.item)
                ]),
            ]
        )
        self.v.visit(tree)
        self.assertEqual(len(tree[0]), 1)
        self.assertEqual(len(tree), 1)


    def tearDown(self):
        del self.v


class Test_RecoverXMPPRoster(unittest.TestCase):
    def setUp(self):
        self.v = roster._RecoverXMPPRoster(TEST_ACCOUNT_JID)

    def test_recovers_vias(self):
        self.tree = roster.TreeRoot(
            initial=[
                roster.Group(
                    "foo",
                    initial=[
                        roster.MetaContact(
                            initial=[
                                roster.Via(TEST_ACCOUNT_JID, TEST_PEER_JID),
                                roster.Via(TEST_ACCOUNT_JID, TEST_PEER_JID2),
                            ]
                        ),
                    ]
                ),
                roster.Group(
                    "bar",
                    initial=[
                        roster.Via(TEST_ACCOUNT_JID, TEST_PEER_JID2),
                        roster.Via(TEST_ACCOUNT_JID.replace(localpart="bar"),
                                   TEST_PEER_JID),
                    ]
                ),
                roster.Group(
                    "baz",
                    initial=[
                        roster.Via(TEST_ACCOUNT_JID, TEST_PEER_JID),
                    ]
                )
            ]
        )

        self.assertDictEqual(
            self.v.visit(self.tree),
            {
                str(TEST_PEER_JID): {
                    "subscription": "none",
                    "approved": False,
                    "ask": None,
                    "name": None,
                    "groups": {"foo", "baz"},
                },
                str(TEST_PEER_JID2): {
                    "subscription": "none",
                    "approved": False,
                    "ask": None,
                    "name": None,
                    "groups": {"foo", "bar"},
                }
            }
        )

    def tearDown(self):
        del self.v


class Test_SetupMaps(unittest.TestCase):
    def setUp(self):
        self.dest = unittest.mock.Mock()
        self.dest._group_map = {}
        self.v = roster._SetupMaps(self.dest)

    def test_recovers_groups(self):
        tree = roster.TreeRoot(
            initial=[
                roster.Group(
                    "foo",
                    initial=[
                        roster.MetaContact(
                            initial=[
                                roster.Via(TEST_ACCOUNT_JID, TEST_PEER_JID),
                                roster.Via(TEST_ACCOUNT_JID, TEST_PEER_JID2),
                            ]
                        ),
                    ]
                ),
                roster.Group(
                    "bar",
                    initial=[
                        roster.Via(TEST_ACCOUNT_JID, TEST_PEER_JID2),
                        roster.Via(TEST_ACCOUNT_JID.replace(localpart="bar"),
                                   TEST_PEER_JID),
                    ]
                ),
                roster.Group(
                    "baz",
                    initial=[
                        roster.Via(TEST_ACCOUNT_JID, TEST_PEER_JID),
                    ]
                )
            ]
        )

        self.v.visit(tree)

        self.assertDictEqual(
            self.dest._group_map,
            {
                "foo": tree[0],
                "bar": tree[1],
                "baz": tree[2]
            }
        )

    def tearDown(self):
        del self.v
        del self.dest


class TestPlugin(unittest.TestCase):
    def test_is_plugin(self):
        self.assertTrue(issubclass(
            roster.Plugin,
            plugin.Base
        ))

    def setUp(self):
        self.base = unittest.mock.Mock()
        self.base.client = ClientMock()
        self.c = self.base.client
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

    def test_load_roster_state(self):
        self.base.mock_calls.clear()

        with contextlib.ExitStack() as stack:
            json_load = stack.enter_context(unittest.mock.patch(
                "json.load",
                new=self.base.json_load
            ))

            self.r.load_roster_state(self.base.account.jid,
                                     self.base.roster_service)

        calls = list(self.base.mock_calls)

        self.assertSequenceEqual(
            calls,
            [
                unittest.mock.call.client.config_manager.open_single(
                    roster.Plugin.UID,
                    mlxc.config.escape_dirname("xmpp:{}.json".format(
                        self.base.account.jid)
                    ),
                    mode="r"),
                unittest.mock.call.client.config_manager.open_single(
                ).__enter__(),
                unittest.mock.call.json_load(
                    self.c.config_manager.open_single()
                ),
                unittest.mock.call.client.config_manager.open_single(
                ).__exit__(None, None, None),
                unittest.mock.call.roster_service.import_from_json(
                    json_load()
                )
            ]
        )

    def test_dump_roster_state(self):
        self.base.mock_calls.clear()

        with contextlib.ExitStack() as stack:
            stack.enter_context(unittest.mock.patch(
                "json.dump",
                new=self.base.json_dump
            ))

            self.r.dump_roster_state(self.base.account.jid,
                                     self.base.roster_service)

        calls = list(self.base.mock_calls)

        self.assertSequenceEqual(
            calls,
            [
                unittest.mock.call.roster_service.export_as_json(),
                unittest.mock.call.client.config_manager.open_single(
                    roster.Plugin.UID,
                    mlxc.config.escape_dirname("xmpp:{}.json".format(
                        self.base.account.jid)
                    ),
                    mode="w"),
                unittest.mock.call.client.config_manager.open_single(
                ).__enter__(),
                unittest.mock.call.json_dump(
                    self.base.roster_service.export_as_json(),
                    self.c.config_manager.open_single(),
                ),
                unittest.mock.call.client.config_manager.open_single(
                ).__exit__(None, None, None),
            ]
        )

    def test__on_account_enabling_summons_roster_and_sets_initial_roster(self):
        self.base.mock_calls.clear()

        with contextlib.ExitStack() as stack:
            stack.enter_context(unittest.mock.patch(
                "mlxc.roster._RosterConnector",
                new=self.base.connector
            ))

            stack.enter_context(unittest.mock.patch.object(
                self.r,
                "load_roster_state",
                new=self.base.load_roster_state
            ))

            self.r._on_account_enabling(
                self.base.account,
                self.base.state)

        calls = list(self.base.mock_calls)
        self.assertSequenceEqual(
            calls,
            [
                unittest.mock.call.connector(
                    self.r,
                    self.base.account,
                    self.base.state),
                unittest.mock.call.load_roster_state(
                    self.base.account.jid,
                    self.base.connector().roster_service
                )
            ]
        )

    def test__on_writeback_dumps_roster_state_of_enabled_accounts(self):
        self.base.mock_calls.clear()

        with contextlib.ExitStack() as stack:
            stack.enter_context(unittest.mock.patch(
                "mlxc.roster._RosterConnector",
                new=self.base.connector
            ))

            stack.enter_context(unittest.mock.patch.object(
                self.r,
                "load_roster_state"
            ))

            stack.enter_context(unittest.mock.patch.object(
                self.r,
                "dump_roster_state",
                new=self.base.dump_roster_state
            ))

            self.r._on_account_enabling(
                self.base.account1,
                self.base.state1)

            self.r._on_account_enabling(
                self.base.account2,
                self.base.state2)

            self.base.mock_calls.clear()
            self.c.config_manager.on_writeback()

        calls = list(self.base.mock_calls)
        self.assertIn(
            unittest.mock.call.dump_roster_state(
                self.base.account1.jid,
                self.base.connector().roster_service
            ),
            calls
        )
        self.assertIn(
            unittest.mock.call.dump_roster_state(
                self.base.account2.jid,
                self.base.connector().roster_service
            ),
            calls
        )

    def test__on_account_disabling_disconnects_from_roster_and_writes_back_roster(self):
        self.base.mock_calls.clear()

        with contextlib.ExitStack() as stack:
            stack.enter_context(unittest.mock.patch(
                "mlxc.roster._RosterConnector",
                new=self.base.connector
            ))

            stack.enter_context(unittest.mock.patch.object(
                self.r,
                "load_roster_state"
            ))

            stack.enter_context(unittest.mock.patch.object(
                self.r,
                "dump_roster_state",
                new=self.base.dump_roster_state
            ))

            self.r._on_account_enabling(
                self.base.account,
                self.base.state)
            self.base.mock_calls.clear()
            self.r._on_account_disabling(
                self.base.account,
                self.base.state,
                reason=None)


        calls = list(self.base.mock_calls)
        self.assertSequenceEqual(
            calls,
            [
                unittest.mock.call.dump_roster_state(
                    self.base.account.jid,
                    self.base.connector().roster_service
                ),
                unittest.mock.call.connector().close()
            ]
        )

    def test__on_account_disabling_twice_is_noop(self):
        with contextlib.ExitStack() as stack:
            stack.enter_context(unittest.mock.patch(
                "mlxc.roster._RosterConnector",
                new=self.base.connector
            ))

            stack.enter_context(unittest.mock.patch(
                "json.load",
                new=self.base.json_load
            ))

            stack.enter_context(unittest.mock.patch(
                "json.dump",
                new=self.base.json_dump
            ))

            self.r._on_account_enabling(
                self.base.account,
                self.base.state)
            self.r._on_account_disabling(
                self.base.account,
                self.base.state,
                reason=None)

            self.base.mock_calls.clear()
            self.r._on_account_disabling(
                self.base.account,
                self.base.state,
                reason=None)

        calls = list(self.base.mock_calls)
        self.assertSequenceEqual(
            calls,
            [
            ]
        )

    def test__on_entry_added_creates_groups_and_vias(self):
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
            via = group[0]
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
        via = group[0]
        self.assertIsInstance(via, roster.Via)
        self.assertIs(via.roster_item, item1)

        group = self.r.group_map["C"]
        self.assertEqual(len(group), 1)
        via = group[0]
        self.assertIsInstance(via, roster.Via)
        self.assertEqual(via.roster_item, item2)

        group = self.r.group_map["A"]
        self.assertEqual(len(group), 2)
        for via in group:
            self.assertIsInstance(via, roster.Via)

        self.assertSetEqual(
            set(via.roster_item for via in group),
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
            via = group[0]
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
                unittest.mock.call(item, deep=False),
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
                unittest.mock.call(item, deep=True),
                unittest.mock.call().visit(self.c.roster.root)
            ]
        )

    def test__on_resource_available_updates_vias(self):
        pass

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

            on_loaded = stack.enter_context(
                unittest.mock.patch.object(
                    c.on_loaded,
                    "connect"
                )
            )

            on_writeback = stack.enter_context(
                unittest.mock.patch.object(
                    c.config_manager.on_writeback,
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

        on_loaded.assert_called_with(
            r._on_loaded
        )

        on_writeback.assert_called_with(
            r._on_writeback
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

            on_loaded = stack.enter_context(
                unittest.mock.patch.object(
                    c,
                    "on_loaded"
                )
            )

            on_writeback = stack.enter_context(
                unittest.mock.patch.object(
                    c.config_manager,
                    "on_writeback"
                )
            )

            r = roster.Plugin(c)
            aioxmpp.testutils.run_coroutine(r.close())

        on_account_enabling.disconnect.assert_called_with(
            on_account_enabling.connect()
        )

        on_loaded.disconnect.assert_called_with(
            on_loaded.connect()
        )

        on_account_disabling.disconnect.assert_called_with(
            on_account_disabling.connect()
        )

        on_writeback.disconnect.assert_called_with(
            on_writeback.connect()
        )

    def tearDown(self):
        del self.r
        del self.c
