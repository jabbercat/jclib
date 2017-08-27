import collections.abc
import itertools
import functools
import unittest
import unittest.mock

import aioxmpp.callbacks

from aioxmpp.testutils import (
    make_listener,
)

from mlxc.instrumentable_list import (
    IList,
    ModelList,
    ModelListView,
    JoinedModelListView,
    ModelTree,
    ModelTreeNode,
    ModelTreeNodeHolder,
)


class TestInstrumentableList(unittest.TestCase):
    def test_is_mutable_sequence(self):
        self.assertTrue(issubclass(
            IList,
            collections.abc.MutableSequence
        ))

    def test_signals(self):
        self.assertIsInstance(
            IList.on_register_item,
            aioxmpp.callbacks.Signal
        )

        self.assertIsInstance(
            IList.on_unregister_item,
            aioxmpp.callbacks.Signal
        )

    def setUp(self):
        self.ilist = IList()
        self.mock = unittest.mock.Mock()
        self.mock.register.return_value = False
        self.mock.unregister.return_value = False
        self.ilist.on_register_item.connect(self.mock.register)
        self.ilist.on_unregister_item.connect(self.mock.unregister)

    def test_insert_and_iter(self):
        self.ilist.insert(0, 1)
        self.ilist.insert(0, 2)
        self.ilist.insert(1, 3)

        self.assertSequenceEqual(
            list(self.ilist),
            [2, 3, 1]
        )

    def test_insert_calls_register(self):
        self.ilist.insert(0, 1)
        self.ilist.insert(0, 2)
        self.ilist.insert(1, 3)

        self.assertSequenceEqual(
            self.mock.mock_calls,
            [
                unittest.mock.call.register(1),
                unittest.mock.call.register(2),
                unittest.mock.call.register(3),
            ]
        )

    def test_delitem_single(self):
        self.ilist.insert(0, 1)
        self.ilist.insert(0, 2)
        self.ilist.insert(1, 3)

        del self.ilist[1]

        self.assertSequenceEqual(
            list(self.ilist),
            [2, 1]
        )

        del self.ilist[1]

        self.assertSequenceEqual(
            list(self.ilist),
            [2]
        )

        del self.ilist[0]

        self.assertSequenceEqual(
            list(self.ilist),
            []
        )

        self.assertSequenceEqual(
            self.mock.mock_calls,
            [
                unittest.mock.call.register(1),
                unittest.mock.call.register(2),
                unittest.mock.call.register(3),
                unittest.mock.call.unregister(3),
                unittest.mock.call.unregister(1),
                unittest.mock.call.unregister(2),
            ]
        )

    def test_delitem_slice(self):
        self.ilist.insert(0, 1)
        self.ilist.insert(0, 2)
        self.ilist.insert(1, 3)

        del self.ilist[:]

        self.assertSequenceEqual(
            list(self.ilist),
            []
        )

        self.assertSequenceEqual(
            self.mock.mock_calls,
            [
                unittest.mock.call.register(1),
                unittest.mock.call.register(2),
                unittest.mock.call.register(3),
                unittest.mock.call.unregister(2),
                unittest.mock.call.unregister(3),
                unittest.mock.call.unregister(1),
            ]
        )

    def test_setitem_single(self):
        self.ilist.insert(0, 1)
        self.ilist.insert(0, 2)
        self.ilist.insert(1, 3)

        self.ilist[1] = 4

        self.assertSequenceEqual(
            list(self.ilist),
            [2, 4, 1]
        )

        self.assertSequenceEqual(
            self.mock.mock_calls,
            [
                unittest.mock.call.register(1),
                unittest.mock.call.register(2),
                unittest.mock.call.register(3),
                unittest.mock.call.unregister(3),
                unittest.mock.call.register(4),
            ]
        )

    def test_setitem_slice(self):
        self.ilist.insert(0, 1)
        self.ilist.insert(0, 2)
        self.ilist.insert(1, 3)

        self.ilist[1:] = [4, 5, 6]

        self.assertSequenceEqual(
            list(self.ilist),
            [2, 4, 5, 6]
        )

        self.assertSequenceEqual(
            self.mock.mock_calls,
            [
                unittest.mock.call.register(1),
                unittest.mock.call.register(2),
                unittest.mock.call.register(3),
                unittest.mock.call.unregister(3),
                unittest.mock.call.unregister(1),
                unittest.mock.call.register(4),
                unittest.mock.call.register(5),
                unittest.mock.call.register(6),
            ]
        )

    @unittest.skipIf(
        aioxmpp.version_info[:2] >= (0, 5),
        "aioxmpp provides isolation"
    )
    def test_delitem_slice_rolls_back_on_exception(self):
        exc = Exception()

        n = 2

        def raise_after(exc, *args):
            nonlocal n
            n -= 1
            if n <= 0:
                raise exc

        self.ilist.on_unregister_item.connect(
            functools.partial(raise_after, exc)
        )

        self.ilist[:] = [3, 2, 1]

        with self.assertRaises(Exception) as ctx:
            del self.ilist[:]

        self.assertIs(ctx.exception, exc)


        self.assertSequenceEqual(
            self.mock.mock_calls,
            [
                unittest.mock.call.register(3),
                unittest.mock.call.register(2),
                unittest.mock.call.register(1),
                unittest.mock.call.unregister(3),
                unittest.mock.call.unregister(2),
                unittest.mock.call.register(3),
            ]
        )

    @unittest.skipIf(
        aioxmpp.version_info[:2] >= (0, 5),
        "aioxmpp provides isolation"
    )
    def test_setitem_slice_rolls_back_on_exception(self):
        exc = Exception()

        n = 2

        def raise_after(exc, *args):
            nonlocal n
            n -= 1
            if n <= 0:
                raise exc

        self.ilist.on_unregister_item.connect(
            functools.partial(raise_after, exc)
        )

        self.ilist[:] = [3, 2, 1]

        with self.assertRaises(Exception) as ctx:
            self.ilist[:] = [4, 5, 6]

        self.assertIs(ctx.exception, exc)


        self.assertSequenceEqual(
            self.mock.mock_calls,
            [
                unittest.mock.call.register(3),
                unittest.mock.call.register(2),
                unittest.mock.call.register(1),
                unittest.mock.call.unregister(3),
                unittest.mock.call.unregister(2),
                unittest.mock.call.register(3),
            ]
        )

    def test_reverse_is_inplace_and_does_not_trigger_events(self):
        self.ilist[:] = [1, 2, 3]
        self.mock.mock_calls.clear()

        self.ilist.reverse()
        self.assertSequenceEqual(
            list(self.ilist),
            [3, 2, 1]
        )

        self.assertSequenceEqual(
            self.mock.mock_calls,
            [
            ]
        )

    def test_init_with_list(self):
        l = [1, 2, 3]

        ilist = IList(l)

        l.append(4)

        self.assertSequenceEqual(
            list(ilist),
            [1, 2, 3]
        )

    def test_init_with_iterable(self):
        l = (x for x in range(10) if x % 2 == 0)

        ilist = IList(l)

        self.assertSequenceEqual(
            list(ilist),
            [0, 2, 4, 6, 8]
        )


class TestModelList(unittest.TestCase):
    def test_is_mutable_sequence(self):
        self.assertTrue(issubclass(
            ModelList,
            collections.abc.MutableSequence,
        ))

    def setUp(self):
        self.mlist = ModelList()
        self.listener = make_listener(self.mlist)

    def test_init_bare(self):
        mlist = ModelList()
        self.assertIsInstance(mlist.on_register_item,
                              aioxmpp.callbacks.AdHocSignal)
        self.assertIsInstance(mlist.on_unregister_item,
                              aioxmpp.callbacks.AdHocSignal)
        self.assertIsInstance(mlist.begin_insert_rows,
                              aioxmpp.callbacks.AdHocSignal)
        self.assertIsInstance(mlist.end_insert_rows,
                              aioxmpp.callbacks.AdHocSignal)
        self.assertIsInstance(mlist.begin_remove_rows,
                              aioxmpp.callbacks.AdHocSignal)
        self.assertIsInstance(mlist.end_remove_rows,
                              aioxmpp.callbacks.AdHocSignal)
        self.assertIsInstance(mlist.begin_move_rows,
                              aioxmpp.callbacks.AdHocSignal)
        self.assertIsInstance(mlist.end_move_rows,
                              aioxmpp.callbacks.AdHocSignal)

    def test_init_with_items(self):
        def generator():
            yield 2
            yield 1
            yield 3
        mlist = ModelList(generator())
        self.assertSequenceEqual(mlist, [2, 1, 3])

    def test_insert(self):
        self.mlist.insert(0, 1)
        self.mlist.insert(0, 2)
        self.mlist.insert(1, 3)

        self.assertSequenceEqual(
            list(self.mlist),
            [
                2, 3, 1
            ]
        )

        self.assertSequenceEqual(
            self.listener.mock_calls,
            [
                unittest.mock.call.begin_insert_rows(None, 0, 0),
                unittest.mock.call.on_register_item(1, 0),
                unittest.mock.call.end_insert_rows(),
                unittest.mock.call.begin_insert_rows(None, 0, 0),
                unittest.mock.call.on_register_item(2, 0),
                unittest.mock.call.end_insert_rows(),
                unittest.mock.call.begin_insert_rows(None, 1, 1),
                unittest.mock.call.on_register_item(3, 1),
                unittest.mock.call.end_insert_rows(),
            ]
        )

    def test_insert_large_index_is_correctly_mapped(self):
        self.mlist.insert(0, 1)
        self.mlist.insert(0, 2)
        self.mlist.insert(100, 3)

        self.assertSequenceEqual(
            list(self.mlist),
            [
                2, 1, 3
            ]
        )

        self.assertSequenceEqual(
            self.listener.mock_calls,
            [
                unittest.mock.call.begin_insert_rows(None, 0, 0),
                unittest.mock.call.on_register_item(1, 0),
                unittest.mock.call.end_insert_rows(),
                unittest.mock.call.begin_insert_rows(None, 0, 0),
                unittest.mock.call.on_register_item(2, 0),
                unittest.mock.call.end_insert_rows(),
                unittest.mock.call.begin_insert_rows(None, 2, 2),
                unittest.mock.call.on_register_item(3, 2),
                unittest.mock.call.end_insert_rows(),
            ]
        )

    def test_insert_negative_index_is_correctly_mapped(self):
        self.mlist.insert(0, 1)
        self.mlist.insert(0, 2)
        self.mlist.insert(-1, 3)

        self.assertSequenceEqual(
            list(self.mlist),
            [
                2, 3, 1
            ]
        )

        self.assertSequenceEqual(
            self.listener.mock_calls,
            [
                unittest.mock.call.begin_insert_rows(None, 0, 0),
                unittest.mock.call.on_register_item(1, 0),
                unittest.mock.call.end_insert_rows(),
                unittest.mock.call.begin_insert_rows(None, 0, 0),
                unittest.mock.call.on_register_item(2, 0),
                unittest.mock.call.end_insert_rows(),
                unittest.mock.call.begin_insert_rows(None, 1, 1),
                unittest.mock.call.on_register_item(3, 1),
                unittest.mock.call.end_insert_rows(),
            ]
        )

    def test_insert_negative_out_of_bounds_index_is_correctly_mapped(self):
        self.mlist.insert(0, 1)
        self.mlist.insert(0, 2)
        self.mlist.insert(-11, 3)

        self.assertSequenceEqual(
            list(self.mlist),
            [
                3, 2, 1
            ]
        )

        self.assertSequenceEqual(
            self.listener.mock_calls,
            [
                unittest.mock.call.begin_insert_rows(None, 0, 0),
                unittest.mock.call.on_register_item(1, 0),
                unittest.mock.call.end_insert_rows(),
                unittest.mock.call.begin_insert_rows(None, 0, 0),
                unittest.mock.call.on_register_item(2, 0),
                unittest.mock.call.end_insert_rows(),
                unittest.mock.call.begin_insert_rows(None, 0, 0),
                unittest.mock.call.on_register_item(3, 0),
                unittest.mock.call.end_insert_rows(),
            ]
        )

    def test_insert_calls_register_after_item_is_added_to_storage(self):
        def cb(item):
            self.assertIn(item, self.mlist)

        self.mlist.on_register_item.connect(cb)

        self.mlist.insert(0, 1)

    def test_delitem_unregisters_item_before_removal(self):
        def cb(item):
            self.assertIn(item, self.mlist)

        self.mlist.on_unregister_item.connect(cb)

        self.mlist.insert(0, 1)
        del self.mlist[0]

    def test_delitem_single(self):
        self.mlist.insert(0, 1)
        self.mlist.insert(0, 2)
        self.mlist.insert(1, 3)

        self.listener.mock_calls.clear()

        del self.mlist[0]

        self.assertSequenceEqual(
            list(self.mlist),
            [
                3, 1
            ]
        )

        del self.mlist[1]

        self.assertSequenceEqual(
            list(self.mlist),
            [
                3
            ]
        )

        del self.mlist[-1]

        self.assertSequenceEqual(list(self.mlist), [])

        self.assertSequenceEqual(
            self.listener.mock_calls,
            [
                unittest.mock.call.begin_remove_rows(None, 0, 0),
                unittest.mock.call.on_unregister_item(2),
                unittest.mock.call.end_remove_rows(),
                unittest.mock.call.begin_remove_rows(None, 1, 1),
                unittest.mock.call.on_unregister_item(1),
                unittest.mock.call.end_remove_rows(),
                unittest.mock.call.begin_remove_rows(None, 0, 0),
                unittest.mock.call.on_unregister_item(3),
                unittest.mock.call.end_remove_rows(),
            ]
        )

    def test_delitem_single_out_of_bounds(self):
        self.mlist.insert(0, 1)
        self.mlist.insert(0, 2)
        self.mlist.insert(1, 3)

        self.listener.mock_calls.clear()

        with self.assertRaises(IndexError):
            del self.mlist[10]

        with self.assertRaises(IndexError):
            del self.mlist[-10]

        self.assertSequenceEqual(self.listener.mock_calls, [])

    def test_delitem_positive_slice_with_unity_stride(self):
        self.mlist.insert(0, 1)
        self.mlist.insert(0, 2)
        self.mlist.insert(1, 3)

        self.listener.mock_calls.clear()

        del self.mlist[1:]

        self.assertSequenceEqual(
            list(self.mlist),
            [
                2
            ]
        )

        del self.mlist[:]

        self.assertSequenceEqual(list(self.mlist), [])

        self.assertSequenceEqual(
            self.listener.mock_calls,
            [
                unittest.mock.call.begin_remove_rows(None, 1, 2),
                unittest.mock.call.on_unregister_item(3),
                unittest.mock.call.on_unregister_item(1),
                unittest.mock.call.end_remove_rows(),
                unittest.mock.call.begin_remove_rows(None, 0, 0),
                unittest.mock.call.on_unregister_item(2),
                unittest.mock.call.end_remove_rows(),
            ]
        )

    def test_delitem_negative_slice_with_unity_stride(self):
        self.mlist.insert(0, 1)
        self.mlist.insert(0, 2)
        self.mlist.insert(1, 3)

        self.listener.mock_calls.clear()

        del self.mlist[-3:]

        self.assertSequenceEqual(list(self.mlist), [])

        self.assertSequenceEqual(
            self.listener.mock_calls,
            [
                unittest.mock.call.begin_remove_rows(None, 0, 2),
                unittest.mock.call.on_unregister_item(2),
                unittest.mock.call.on_unregister_item(3),
                unittest.mock.call.on_unregister_item(1),
                unittest.mock.call.end_remove_rows(),
            ]
        )

    def test_delitem_negative_slice_with_negative_unity_stride(self):
        self.mlist.insert(0, 1)
        self.mlist.insert(0, 2)
        self.mlist.insert(1, 3)

        self.listener.mock_calls.clear()

        del self.mlist[-1:-4:-1]

        self.assertSequenceEqual(list(self.mlist), [])

        self.assertSequenceEqual(
            self.listener.mock_calls,
            [
                unittest.mock.call.begin_remove_rows(None, 0, 2),
                unittest.mock.call.on_unregister_item(2),
                unittest.mock.call.on_unregister_item(3),
                unittest.mock.call.on_unregister_item(1),
                unittest.mock.call.end_remove_rows(),
            ]
        )

    def test_delitem_positive_slice_with_negative_unity_stride(self):
        self.mlist.insert(0, 1)
        self.mlist.insert(0, 2)
        self.mlist.insert(1, 3)

        self.listener.mock_calls.clear()

        del self.mlist[2:0:-1]

        self.assertSequenceEqual(list(self.mlist), [2])

        self.assertSequenceEqual(
            self.listener.mock_calls,
            [
                unittest.mock.call.begin_remove_rows(None, 1, 2),
                unittest.mock.call.on_unregister_item(3),
                unittest.mock.call.on_unregister_item(1),
                unittest.mock.call.end_remove_rows(),
            ]
        )

    def test_delitem_positive_slice_with_non_unity_stride(self):
        self.mlist.insert(0, 1)
        self.mlist.insert(0, 2)
        self.mlist.insert(1, 3)

        self.listener.mock_calls.clear()

        del self.mlist[::2]

        self.assertSequenceEqual(list(self.mlist), [3])

        self.assertSequenceEqual(
            self.listener.mock_calls,
            [
                unittest.mock.call.begin_remove_rows(None, 0, 0),
                unittest.mock.call.on_unregister_item(2),
                unittest.mock.call.end_remove_rows(),
                unittest.mock.call.begin_remove_rows(None, 1, 1),
                unittest.mock.call.on_unregister_item(1),
                unittest.mock.call.end_remove_rows(),
            ]
        )

    def test_setitem_single(self):
        self.mlist.insert(0, 1)
        self.mlist.insert(0, 2)
        self.mlist.insert(1, 3)

        self.listener.mock_calls.clear()

        self.mlist[1] = 10

        self.assertSequenceEqual(list(self.mlist), [2, 10, 1])

        self.assertSequenceEqual(
            self.listener.mock_calls,
            [
                unittest.mock.call.begin_remove_rows(None, 1, 1),
                unittest.mock.call.on_unregister_item(3),
                unittest.mock.call.end_remove_rows(),
                unittest.mock.call.begin_insert_rows(None, 1, 1),
                unittest.mock.call.on_register_item(10, 1),
                unittest.mock.call.end_insert_rows(),
            ]
        )

    def test_setitem_as_bulk_insert_does_not_generate_removal(self):
        self.mlist.extend([1, 2, 3])
        self.listener.mock_calls.clear()

        self.mlist[1:1] = [10, 20, 30]

        self.assertSequenceEqual(list(self.mlist), [1, 10, 20, 30, 2, 3])

        self.assertSequenceEqual(
            self.listener.mock_calls,
            [
                unittest.mock.call.begin_insert_rows(None, 1, 3),
                unittest.mock.call.on_register_item(10, 1),
                unittest.mock.call.on_register_item(20, 2),
                unittest.mock.call.on_register_item(30, 3),
                unittest.mock.call.end_insert_rows(),
            ]
        )

    def test_setitem_reject_mismatching_size_of_ext_slices(self):
        self.mlist.extend([1, 2, 3])
        self.listener.mock_calls.clear()

        with self.assertRaisesRegex(
                ValueError,
                r"attempt to assign sequence of size \d+ to extended slice of size \d+"):
            self.mlist[1:1:-1] = [10, 20, 30]

        self.assertSequenceEqual(list(self.mlist), [1, 2, 3])

        self.assertSequenceEqual(
            self.listener.mock_calls,
            [
            ]
        )

    def test_setitem_single_negative(self):
        self.mlist.insert(0, 1)
        self.mlist.insert(0, 2)
        self.mlist.insert(1, 3)

        self.listener.mock_calls.clear()

        self.mlist[-1] = 10

        self.assertSequenceEqual(list(self.mlist), [2, 3, 10])

        self.assertSequenceEqual(
            self.listener.mock_calls,
            [
                unittest.mock.call.begin_remove_rows(None, 2, 2),
                unittest.mock.call.on_unregister_item(1),
                unittest.mock.call.end_remove_rows(),
                unittest.mock.call.begin_insert_rows(None, 2, 2),
                unittest.mock.call.on_register_item(10, 2),
                unittest.mock.call.end_insert_rows(),
            ]
        )

    def test_setitem_out_of_bounds(self):
        self.mlist.insert(0, 1)
        self.mlist.insert(0, 2)
        self.mlist.insert(1, 3)

        self.listener.mock_calls.clear()

        with self.assertRaises(IndexError):
            self.mlist[10] = 10

        with self.assertRaises(IndexError):
            self.mlist[-10] = 10

        self.assertSequenceEqual(list(self.mlist), [2, 3, 1])

        self.assertSequenceEqual(
            self.listener.mock_calls,
            [
            ]
        )

    def test_setitem_positive_slice_with_unity_stride(self):
        self.mlist.insert(0, 1)
        self.mlist.insert(0, 2)
        self.mlist.insert(1, 3)

        self.listener.mock_calls.clear()

        self.mlist[1:] = [10, 11, 12]

        self.assertSequenceEqual(list(self.mlist), [2, 10, 11, 12])

        self.assertSequenceEqual(
            self.listener.mock_calls,
            [
                unittest.mock.call.begin_remove_rows(None, 1, 2),
                unittest.mock.call.on_unregister_item(3),
                unittest.mock.call.on_unregister_item(1),
                unittest.mock.call.end_remove_rows(),
                unittest.mock.call.begin_insert_rows(None, 1, 3),
                unittest.mock.call.on_register_item(10, 1),
                unittest.mock.call.on_register_item(11, 2),
                unittest.mock.call.on_register_item(12, 3),
                unittest.mock.call.end_insert_rows(),
            ]
        )

    def test_setitem_negative_slice_with_unity_stride(self):
        self.mlist.insert(0, 1)
        self.mlist.insert(0, 2)
        self.mlist.insert(1, 3)

        self.listener.mock_calls.clear()

        self.mlist[-1:] = [10, 11, 12]

        self.assertSequenceEqual(list(self.mlist), [2, 3, 10, 11, 12])

        self.assertSequenceEqual(
            self.listener.mock_calls,
            [
                unittest.mock.call.begin_remove_rows(None, 2, 2),
                unittest.mock.call.on_unregister_item(1),
                unittest.mock.call.end_remove_rows(),
                unittest.mock.call.begin_insert_rows(None, 2, 4),
                unittest.mock.call.on_register_item(10, 2),
                unittest.mock.call.on_register_item(11, 3),
                unittest.mock.call.on_register_item(12, 4),
                unittest.mock.call.end_insert_rows(),
            ]
        )

    def test_setitem_negative_slice_with_negative_unity_stride(self):
        self.mlist.insert(0, 1)
        self.mlist.insert(0, 2)
        self.mlist.insert(1, 3)

        self.listener.mock_calls.clear()

        self.mlist[-1:-4:-1] = [10, 11, 12]

        self.assertSequenceEqual(list(self.mlist), [10, 11, 12])

        self.assertSequenceEqual(
            self.listener.mock_calls,
            [
                unittest.mock.call.begin_remove_rows(None, 0, 2),
                unittest.mock.call.on_unregister_item(2),
                unittest.mock.call.on_unregister_item(3),
                unittest.mock.call.on_unregister_item(1),
                unittest.mock.call.end_remove_rows(),
                unittest.mock.call.begin_insert_rows(None, 0, 2),
                unittest.mock.call.on_register_item(10, 0),
                unittest.mock.call.on_register_item(11, 1),
                unittest.mock.call.on_register_item(12, 2),
                unittest.mock.call.end_insert_rows(),
            ]
        )

    def test_setitem_positive_slice_with_negative_unity_stride(self):
        self.mlist.insert(0, 1)
        self.mlist.insert(0, 2)
        self.mlist.insert(1, 3)

        self.listener.mock_calls.clear()

        self.mlist[2:0:-1] = [10, 11]

        self.assertSequenceEqual(list(self.mlist), [2, 10, 11])

        self.assertSequenceEqual(
            self.listener.mock_calls,
            [
                unittest.mock.call.begin_remove_rows(None, 1, 2),
                unittest.mock.call.on_unregister_item(3),
                unittest.mock.call.on_unregister_item(1),
                unittest.mock.call.end_remove_rows(),
                unittest.mock.call.begin_insert_rows(None, 1, 2),
                unittest.mock.call.on_register_item(10, 1),
                unittest.mock.call.on_register_item(11, 2),
                unittest.mock.call.end_insert_rows(),
            ]
        )

    def test_setitem_slice_with_non_unity_stride(self):
        self.mlist.insert(0, 1)
        self.mlist.insert(0, 2)
        self.mlist.insert(1, 3)

        self.listener.mock_calls.clear()

        with self.assertRaisesRegex(
                IndexError,
                "non-unity strides not supported"):
            self.mlist[::2] = [1, 2, 3]

        with self.assertRaisesRegex(
                IndexError,
                "non-unity strides not supported"):
            self.mlist[::-2] = [1, 2, 3]

        self.assertSequenceEqual(
            self.listener.mock_calls,
            [
            ]
        )

    def test_len(self):
        self.assertEqual(len(self.mlist), 0)

        self.mlist.insert(0, 1)

        self.assertEqual(len(self.mlist), 1)

        self.mlist[:] = [1, 2, 3]

        self.assertEqual(len(self.mlist), 3)

        del self.mlist[:]

        self.assertEqual(len(self.mlist), 0)

    def test_move_forward(self):
        self.mlist[:] = [0, 1, 2, 3, 4, 5]

        self.listener.mock_calls.clear()

        self.mlist.move(2, 4)

        self.assertSequenceEqual(
            list(self.mlist),
            [
                0, 1, 3, 2, 4, 5
            ]
        )

        self.assertSequenceEqual(
            self.listener.mock_calls,
            [
                unittest.mock.call.begin_move_rows(None, 2, 2, None, 4),
                unittest.mock.call.end_move_rows(),
            ]
        )

    def test_move_forward_with_negative_indices(self):
        self.mlist[:] = [0, 1, 2, 3, 4, 5]

        self.listener.mock_calls.clear()

        self.mlist.move(2, -1)

        self.assertSequenceEqual(
            list(self.mlist),
            [
                0, 1, 3, 4, 2, 5
            ]
        )

        self.mlist.move(-3, -1)

        self.assertSequenceEqual(
            list(self.mlist),
            [
                0, 1, 3, 2, 4, 5
            ]
        )

        self.assertSequenceEqual(
            self.listener.mock_calls,
            [
                unittest.mock.call.begin_move_rows(None, 2, 2, None, 5),
                unittest.mock.call.end_move_rows(),
                unittest.mock.call.begin_move_rows(None, 3, 3, None, 5),
                unittest.mock.call.end_move_rows(),
            ]
        )

    def test_move_backward(self):
        self.mlist[:] = [0, 1, 2, 3, 4, 5]

        self.listener.mock_calls.clear()

        self.mlist.move(2, 0)

        self.assertSequenceEqual(
            list(self.mlist),
            [
                2, 0, 1, 3, 4, 5
            ]
        )

        self.assertSequenceEqual(
            self.listener.mock_calls,
            [
                unittest.mock.call.begin_move_rows(None, 2, 2, None, 0),
                unittest.mock.call.end_move_rows(),
            ]
        )

    def test_move_backward_with_negative_indices(self):
        self.mlist[:] = [0, 1, 2, 3, 4, 5]

        self.listener.mock_calls.clear()

        self.mlist.move(-1, 0)

        self.assertSequenceEqual(
            list(self.mlist),
            [
                5, 0, 1, 2, 3, 4
            ]
        )

        self.mlist.move(5, -6)

        self.assertSequenceEqual(
            list(self.mlist),
            [
                4, 5, 0, 1, 2, 3
            ]
        )

        self.assertSequenceEqual(
            self.listener.mock_calls,
            [
                unittest.mock.call.begin_move_rows(None, 5, 5, None, 0),
                unittest.mock.call.end_move_rows(),
                unittest.mock.call.begin_move_rows(None, 5, 5, None, 0),
                unittest.mock.call.end_move_rows(),
            ]
        )

    def test_move_rejects_out_of_bounds_indices(self):
        self.mlist[:] = [0, 1, 2, 3, 4, 5]

        self.listener.mock_calls.clear()

        with self.assertRaises(IndexError):
            self.mlist.move(-10, 0)

        with self.assertRaises(IndexError):
            self.mlist.move(0, -10)

        with self.assertRaises(IndexError):
            self.mlist.move(10, 0)

        with self.assertRaises(IndexError):
            self.mlist.move(0, 10)

    def test_move_ignores_noop_move(self):
        self.mlist[:] = [0, 1, 2, 3, 4, 5]

        self.listener.mock_calls.clear()

        # these four operations are identical and all noops
        self.mlist.move(2, 2)
        self.mlist.move(2, -4)
        self.mlist.move(-4, -4)
        self.mlist.move(-4, 2)

        self.assertSequenceEqual(
            list(self.mlist),
            [
                0, 1, 2, 3, 4, 5
            ]
        )

        self.assertSequenceEqual(
            self.listener.mock_calls,
            [
            ]
        )

    def test_move_ignores_invalid_move(self):
        self.mlist[:] = [0, 1, 2, 3, 4, 5]

        self.listener.mock_calls.clear()

        # these four operations are identical and all invalid
        self.mlist.move(2, 3)
        self.mlist.move(2, -3)
        self.mlist.move(-4, -3)
        self.mlist.move(-4, 3)

        self.assertSequenceEqual(
            list(self.mlist),
            [
                0, 1, 2, 3, 4, 5
            ]
        )

        self.assertSequenceEqual(
            self.listener.mock_calls,
            [
            ]
        )

    def test_reverse_with_odd_item_count_uses_move(self):
        self.mlist[:] = [1, 2, 3, 4, 5]

        self.listener.mock_calls.clear()

        with unittest.mock.patch.object(self.mlist, "move") as move:
            self.mlist.reverse()

        self.assertSequenceEqual(
            move.mock_calls,
            [
                unittest.mock.call(0, 5),
                unittest.mock.call(3, 0),
                unittest.mock.call(1, 4),
                unittest.mock.call(2, 1)
            ]
        )

    def test_reverse_with_even_item_count_uses_move(self):
        self.mlist[:] = [1, 2, 3, 4, 5, 6]

        self.listener.mock_calls.clear()

        with unittest.mock.patch.object(self.mlist, "move") as move:
            self.mlist.reverse()

        self.assertSequenceEqual(
            move.mock_calls,
            [
                unittest.mock.call(0, 6),
                unittest.mock.call(4, 0),
                unittest.mock.call(1, 5),
                unittest.mock.call(3, 1),
                unittest.mock.call(2, 4)
            ]
        )

    def test_reverse_uses_move_correctly_even(self):
        l = list(range(10))
        self.mlist[:] = l

        self.mlist.reverse()
        l.reverse()

        self.assertSequenceEqual(l, self.mlist)

    def test_reverse_uses_move_correctly_odd(self):
        l = list(range(11))
        self.mlist[:] = l

        self.mlist.reverse()
        l.reverse()

        self.assertSequenceEqual(l, self.mlist)

    def test_pop(self):
        self.mlist[:] = [1, 2, 3]

        self.listener.mock_calls.clear()

        self.assertEqual(self.mlist.pop(1), 2)

        self.assertSequenceEqual(
            self.listener.mock_calls,
            [
                unittest.mock.call.begin_remove_rows(None, 1, 1),
                unittest.mock.call.on_unregister_item(2),
                unittest.mock.call.end_remove_rows(),
            ]
        )

    def test_pop_negative_index(self):
        self.mlist[:] = [1, 2, 3]

        self.listener.mock_calls.clear()

        self.assertEqual(self.mlist.pop(-1), 3)

        self.assertSequenceEqual(
            self.listener.mock_calls,
            [
                unittest.mock.call.begin_remove_rows(None, 2, 2),
                unittest.mock.call.on_unregister_item(3),
                unittest.mock.call.end_remove_rows(),
            ]
        )

    def test_pop_rejects_out_of_bounds_indices(self):
        self.mlist[:] = [1, 2, 3]

        self.listener.mock_calls.clear()

        with self.assertRaises(IndexError):
            self.mlist.pop(10)

        with self.assertRaises(IndexError):
            self.mlist.pop(-10)

        self.assertSequenceEqual(
            self.listener.mock_calls,
            [
            ]
        )

    def test_pop_without_index(self):
        self.mlist[:] = [1, 2, 3]

        self.listener.mock_calls.clear()

        self.mlist.pop()

        self.assertSequenceEqual(
            self.listener.mock_calls,
            [
                unittest.mock.call.begin_remove_rows(None, 2, 2),
                unittest.mock.call.on_unregister_item(3),
                unittest.mock.call.end_remove_rows(),
            ]
        )

        self.assertSequenceEqual(
            self.mlist,
            [
                1, 2
            ]
        )

    def test_clear(self):
        self.mlist[:] = [1, 2, 3]
        self.listener.mock_calls.clear()

        self.mlist.clear()

        self.assertSequenceEqual(
            self.listener.mock_calls,
            [
                unittest.mock.call.begin_remove_rows(None, 0, 2),
                unittest.mock.call.on_unregister_item(1),
                unittest.mock.call.on_unregister_item(2),
                unittest.mock.call.on_unregister_item(3),
                unittest.mock.call.end_remove_rows(),
            ]
        )

        self.assertSequenceEqual(
            self.mlist,
            []
        )

    def test_register_item_is_called_on_initialisation(self):
        def generate():
            yield 1
            yield 3
            yield 2

        with unittest.mock.patch.object(
                ModelList,
                "on_register_item") as on_register_item:
            mlist = ModelList(generate())
            self.assertSequenceEqual(
                mlist,
                [1, 3, 2]
            )

        self.assertSequenceEqual(
            on_register_item.mock_calls,
            [
                unittest.mock.call(1, 0),
                unittest.mock.call(3, 1),
                unittest.mock.call(2, 2),
            ]
        )

    def test_init_forwards_keyword_arguments(self):
        class Foo:
            def __init__(self, *args, **kwargs):
                self.args = args
                self.kwargs = kwargs

        class Bar(ModelList, Foo):
            pass

        b = Bar(x="a")
        self.assertDictEqual(
            b.kwargs,
            {
                "x": "a"
            }
        )

    def test_refresh_data(self):
        self.mlist[:] = range(5)

        self.mlist.refresh_data(
            slice(1, 3)
        )

        self.listener.data_changed.assert_called_once_with(
            None, 1, 2, 0, 0, None
        )

    def test_refresh_data_checks_column_range(self):
        self.mlist[:] = range(5)

        with self.assertRaisesRegex(
                ValueError,
                "end column must be greater than or equal to start column"):
            self.mlist.refresh_data(
                slice(1, 3),
                3, 1
            )

        self.listener.data_changed.assert_not_called()

    def test_refresh_data_allows_None_columns(self):
        self.mlist[:] = range(5)

        self.mlist.refresh_data(
            slice(1, 3),
            None, None,
        )

        self.listener.data_changed.assert_called_once_with(
            None,
            1, 2,
            None, None,
            None
        )

    def test_refresh_data_sets_colmun2_to_None_if_column1_is_None(self):
        self.mlist[:] = range(5)

        self.mlist.refresh_data(
            slice(1, 3),
            None,
        )

        self.listener.data_changed.assert_called_once_with(
            None,
            1, 2,
            None, None,
            None
        )

    def test_refresh_data_does_not_Noneify_column2_if_column2_is_nonzero(self):
        self.mlist[:] = range(5)

        with self.assertRaisesRegex(
                ValueError,
                "either both or no columns must be None"):
            self.mlist.refresh_data(
                slice(1, 3),
                None, 2
            )

        self.listener.data_changed.assert_not_called()

    def test_refresh_data_rejects_non_unity_non_forward_slice(self):
        self.mlist[:] = range(5)

        with self.assertRaisesRegex(
                ValueError,
                "slice must have stride 1"):
            self.mlist.refresh_data(
                slice(1, 3, -1),
            )

        self.listener.data_changed.assert_not_called()

        with self.assertRaisesRegex(
                ValueError,
                "slice must have stride 1"):
            self.mlist.refresh_data(
                slice(1, 3, 2),
            )

        self.listener.data_changed.assert_not_called()

    def test_refresh_data_passes_roles(self):
        self.mlist[:] = range(5)

        self.mlist.refresh_data(
            slice(1, 3),
            roles=unittest.mock.sentinel.roles
        )

        self.listener.data_changed.assert_called_once_with(
            None,
            1, 2,
            0, 0,
            unittest.mock.sentinel.roles,
        )


class TestModelListView(unittest.TestCase):
    def setUp(self):
        self.mock = unittest.mock.Mock()
        self.backend = ModelList()
        self.view = ModelListView(self.backend)

        self.view.begin_insert_rows.connect(self.mock.begin_insert_rows)
        self.view.end_insert_rows.connect(self.mock.end_insert_rows)
        self.view.begin_remove_rows.connect(self.mock.begin_remove_rows)
        self.view.end_remove_rows.connect(self.mock.end_remove_rows)
        self.view.begin_move_rows.connect(self.mock.begin_move_rows)
        self.view.end_move_rows.connect(self.mock.end_move_rows)

    def test_init(self):
        backend = ModelList()
        view = ModelListView(backend)

        self.assertIsInstance(view.begin_insert_rows,
                              aioxmpp.callbacks.AdHocSignal)
        self.assertIsInstance(view.begin_move_rows,
                              aioxmpp.callbacks.AdHocSignal)
        self.assertIsInstance(view.begin_remove_rows,
                              aioxmpp.callbacks.AdHocSignal)

        self.assertIsInstance(view.end_insert_rows,
                              aioxmpp.callbacks.AdHocSignal)
        self.assertIsInstance(view.end_move_rows,
                              aioxmpp.callbacks.AdHocSignal)
        self.assertIsInstance(view.end_remove_rows,
                              aioxmpp.callbacks.AdHocSignal)

        self.assertIsInstance(view.data_changed,
                              aioxmpp.callbacks.AdHocSignal)

    def test_is_sequence(self):
        self.assertTrue(issubclass(
            ModelListView,
            collections.abc.Sequence
        ))

    def test_is_not_mutable_sequence(self):
        self.assertFalse(issubclass(
            ModelListView,
            collections.abc.MutableSequence
        ))

    def test_attaches_to_backend(self):
        backend = unittest.mock.Mock()
        view = ModelListView(backend)

        backend.begin_insert_rows.connect.assert_called_with(
            view.begin_insert_rows
        )

        backend.begin_remove_rows.connect.assert_called_with(
            view.begin_remove_rows
        )

        backend.begin_move_rows.connect.assert_called_with(
            view.begin_move_rows
        )

        backend.end_insert_rows.connect.assert_called_with(
            view.end_insert_rows
        )

        backend.end_remove_rows.connect.assert_called_with(
            view.end_remove_rows
        )

        backend.end_move_rows.connect.assert_called_with(
            view.end_move_rows
        )

        backend.data_changed.connect.assert_called_once_with(
            view.data_changed
        )

    def test___getitem__forwards_to_backend(self):
        with unittest.mock.patch.object(
                ModelList, "__getitem__") as getitem:
            sl = object()
            result = self.view[sl]

        getitem.assert_called_with(sl)
        self.assertEqual(result, getitem())

    def test___len__forwards_to_backend(self):
        with unittest.mock.patch.object(
                ModelList, "__len__") as len_:
            result = len(self.view)

        len_.assert_called_with()
        self.assertEqual(result, int(len_()))

    def test__iter__forwards_to_backend(self):
        with unittest.mock.patch.object(
                ModelList, "__iter__") as iter_:
            result = iter(self.view)

        iter_.assert_called_with()
        self.assertEqual(result, iter_())

    def test__reversed__forwards_to_backend(self):
        with unittest.mock.patch.object(
                ModelList, "__reversed__") as reversed_:
            result = reversed(self.view)

        reversed_.assert_called_with()
        self.assertEqual(result, reversed_())

    def test__contains__forwards_to_backend(self):
        with unittest.mock.patch.object(
                ModelList, "__contains__") as contains:
            item = object()
            result = item in self.view

        contains.assert_called_with(item)
        self.assertEqual(result, bool(contains()))

    def test_index_forwards_to_backend(self):
        with unittest.mock.patch.object(
                self.backend,
                "index") as index:
            item = object()
            result = self.view.index(item)

        index.assert_called_with(item)
        self.assertEqual(result, index())

    def test_count_forwards_to_backend(self):
        with unittest.mock.patch.object(
                self.backend,
                "count") as count:
            item = object()
            result = self.view.count(item)

        count.assert_called_with(item)
        self.assertEqual(result, count())

    def tearDown(self):
        del self.view
        del self.backend


class TestModelTreeNode(unittest.TestCase):
    def setUp(self):
        self.tree = unittest.mock.Mock()
        self.root = ModelTreeNode(self.tree)
        self.nodes = [
            ModelTreeNode(self.tree)
            for i in range(5)
        ]

    def tearDown(self):
        for i, node in enumerate(self.root):
            self.assertIs(node.parent, self.root, i)
            self.assertEqual(node.parent_index, i)

        del self.root
        del self.tree
        del self.nodes

    def test_is_mutable_sequence(self):
        self.assertIsInstance(
            self.root,
            collections.abc.MutableSequence,
        )

    def test_insert_getitem_len(self):
        self.root.insert(0, self.nodes[0])

        self.assertEqual(len(self.root), 1)

        self.assertIs(
            self.root[0],
            self.nodes[0]
        )

    def test_insert_notifies_tree(self):
        self.root.insert(0, self.nodes[0])

        self.assertSequenceEqual(
            self.tree.mock_calls,
            [
                unittest.mock.call._node_begin_insert_rows(self.root, 0, 0),
                unittest.mock.call._node_end_insert_rows(self.root),
            ]
        )

    def test_insert_emits_correct_index_for_negative_arguments(self):
        self.root.extend(self.nodes[:2])
        self.tree.mock_calls.clear()

        self.root.insert(-1, self.nodes[2])

        self.assertSequenceEqual(
            self.tree.mock_calls,
            [
                unittest.mock.call._node_begin_insert_rows(self.root, 1, 1),
                unittest.mock.call._node_end_insert_rows(self.root),
            ]
        )

    def test_insert_emits_correct_index_for_len_argument(self):
        self.root.extend(self.nodes[:2])
        self.tree.mock_calls.clear()

        self.root.insert(len(self.root), self.nodes[2])

        self.assertSequenceEqual(
            self.tree.mock_calls,
            [
                unittest.mock.call._node_begin_insert_rows(self.root, 2, 2),
                unittest.mock.call._node_end_insert_rows(self.root),
            ]
        )

    def test_extend_is_efficient(self):
        self.root.extend(self.nodes)

        self.assertSequenceEqual(
            self.root,
            self.nodes,
        )

        self.assertSequenceEqual(
            self.tree.mock_calls,
            [
                unittest.mock.call._node_begin_insert_rows(self.root, 0, 4),
                unittest.mock.call._node_end_insert_rows(self.root),
            ]
        )

    def test_delitem_single(self):
        self.root.extend(self.nodes)
        self.tree.mock_calls.clear()

        del self.root[2]

        self.assertSequenceEqual(
            self.root,
            [
                self.nodes[0],
                self.nodes[1],
                self.nodes[3],
                self.nodes[4],
            ]
        )

        self.assertSequenceEqual(
            self.tree.mock_calls,
            [
                unittest.mock.call._node_begin_remove_rows(self.root, 2, 2),
                unittest.mock.call._node_end_remove_rows(self.root),
            ]
        )

    def test_delitem_empty(self):
        self.root.extend(self.nodes)
        self.tree.mock_calls.clear()

        del self.root[2:2]

        self.assertSequenceEqual(
            self.root,
            [
                self.nodes[0],
                self.nodes[1],
                self.nodes[2],
                self.nodes[3],
                self.nodes[4],
            ]
        )

        self.assertSequenceEqual(
            self.tree.mock_calls,
            [
            ]
        )

    def test_delitem_single_negative_index(self):
        self.root.extend(self.nodes)
        self.tree.mock_calls.clear()

        del self.root[-2]

        self.assertSequenceEqual(
            self.root,
            [
                self.nodes[0],
                self.nodes[1],
                self.nodes[2],
                self.nodes[4],
            ]
        )

        self.assertSequenceEqual(
            self.tree.mock_calls,
            [
                unittest.mock.call._node_begin_remove_rows(self.root, 3, 3),
                unittest.mock.call._node_end_remove_rows(self.root),
            ]
        )

    def test_delitem_contiguous_slice(self):
        self.root.extend(self.nodes)
        self.tree.mock_calls.clear()

        del self.root[1:4]

        self.assertSequenceEqual(
            self.root,
            [
                self.nodes[0],
                self.nodes[4],
            ]
        )

        self.assertSequenceEqual(
            self.tree.mock_calls,
            [
                unittest.mock.call._node_begin_remove_rows(self.root, 1, 3),
                unittest.mock.call._node_end_remove_rows(self.root),
            ]
        )

    def test_delitem_contiguous_reverse_slice(self):
        self.root.extend(self.nodes)
        self.tree.mock_calls.clear()

        del self.root[3:0:-1]

        self.assertSequenceEqual(
            self.root,
            [
                self.nodes[0],
                self.nodes[4],
            ]
        )

        self.assertSequenceEqual(
            self.tree.mock_calls,
            [
                unittest.mock.call._node_begin_remove_rows(self.root, 1, 3),
                unittest.mock.call._node_end_remove_rows(self.root),
            ]
        )

    def test_delitem_non_contiguous_slice(self):
        self.root.extend(self.nodes)
        self.tree.mock_calls.clear()

        del self.root[1:4:2]

        self.assertSequenceEqual(
            self.root,
            [
                self.nodes[0],
                self.nodes[2],
                self.nodes[4],
            ]
        )

        self.assertSequenceEqual(
            self.tree.mock_calls,
            [
                unittest.mock.call._node_begin_remove_rows(self.root, 1, 1),
                unittest.mock.call._node_end_remove_rows(self.root),
                unittest.mock.call._node_begin_remove_rows(self.root, 2, 2),
                unittest.mock.call._node_end_remove_rows(self.root),
            ]
        )

    def test_delitem_non_contiguous_reverse_slice(self):
        self.root.extend(self.nodes)
        self.tree.mock_calls.clear()

        del self.root[3:0:-2]

        self.assertSequenceEqual(
            self.root,
            [
                self.nodes[0],
                self.nodes[2],
                self.nodes[4],
            ]
        )

        self.assertSequenceEqual(
            self.tree.mock_calls,
            [
                unittest.mock.call._node_begin_remove_rows(self.root, 3, 3),
                unittest.mock.call._node_end_remove_rows(self.root),
                unittest.mock.call._node_begin_remove_rows(self.root, 1, 1),
                unittest.mock.call._node_end_remove_rows(self.root),
            ]
        )

    def test_setitem_single(self):
        self.root.extend(self.nodes[:3])
        self.tree.mock_calls.clear()

        self.root[1] = self.nodes[3]

        self.assertSequenceEqual(
            self.root,
            [
                self.nodes[0],
                self.nodes[3],
                self.nodes[2],
            ]
        )

        self.assertSequenceEqual(
            self.tree.mock_calls,
            [
                unittest.mock.call._node_begin_remove_rows(self.root, 1, 1),
                unittest.mock.call._node_end_remove_rows(self.root),
                unittest.mock.call._node_begin_insert_rows(self.root, 1, 1),
                unittest.mock.call._node_end_insert_rows(self.root),
            ]
        )

    def test_setitem_single_negative_index(self):
        self.root.extend(self.nodes[:3])
        self.tree.mock_calls.clear()

        self.root[-1] = self.nodes[3]

        self.assertSequenceEqual(
            self.root,
            [
                self.nodes[0],
                self.nodes[1],
                self.nodes[3],
            ]
        )

        self.assertSequenceEqual(
            self.tree.mock_calls,
            [
                unittest.mock.call._node_begin_remove_rows(self.root, 2, 2),
                unittest.mock.call._node_end_remove_rows(self.root),
                unittest.mock.call._node_begin_insert_rows(self.root, 2, 2),
                unittest.mock.call._node_end_insert_rows(self.root),
            ]
        )

    def test_setitem_contigiuous_equal_number(self):
        self.root.extend(self.nodes[:3])
        self.tree.mock_calls.clear()

        self.root[0:2] = self.nodes[3:]

        self.assertSequenceEqual(
            self.root,
            [
                self.nodes[3],
                self.nodes[4],
                self.nodes[2],
            ]
        )

        self.assertSequenceEqual(
            self.tree.mock_calls,
            [
                unittest.mock.call._node_begin_remove_rows(self.root, 0, 1),
                unittest.mock.call._node_end_remove_rows(self.root),
                unittest.mock.call._node_begin_insert_rows(self.root, 0, 1),
                unittest.mock.call._node_end_insert_rows(self.root),
            ]
        )

    def test_setitem_contiguous_nonequal_number(self):
        self.root.extend(self.nodes[:3])
        self.tree.mock_calls.clear()

        self.root[0:1] = self.nodes[3:]

        self.assertSequenceEqual(
            self.root,
            [
                self.nodes[3],
                self.nodes[4],
                self.nodes[1],
                self.nodes[2],
            ]
        )

        self.assertSequenceEqual(
            self.tree.mock_calls,
            [
                unittest.mock.call._node_begin_remove_rows(self.root, 0, 0),
                unittest.mock.call._node_end_remove_rows(self.root),
                unittest.mock.call._node_begin_insert_rows(self.root, 0, 1),
                unittest.mock.call._node_end_insert_rows(self.root),
            ]
        )

    def test_setitem_contiguous_reverse_equal_number(self):
        self.root.extend(self.nodes[:3])
        self.tree.mock_calls.clear()

        self.root[2:0:-1] = self.nodes[3:]

        self.assertSequenceEqual(
            self.root,
            [
                self.nodes[0],
                self.nodes[4],
                self.nodes[3],
            ]
        )

        self.assertSequenceEqual(
            self.tree.mock_calls,
            [
                unittest.mock.call._node_begin_remove_rows(self.root, 1, 2),
                unittest.mock.call._node_end_remove_rows(self.root),
                unittest.mock.call._node_begin_insert_rows(self.root, 1, 2),
                unittest.mock.call._node_end_insert_rows(self.root),
            ]
        )

    def test_setitem_contiguous_reverse_non_equal_number(self):
        self.root.extend(self.nodes[:3])
        self.tree.mock_calls.clear()

        with self.assertRaisesRegex(
                ValueError,
                r"attempt to assign sequence of size \d+ to extended "
                "slice of size \d+"):
            self.root[3:0:-1] = self.nodes[4:]

        self.assertSequenceEqual(
            self.root,
            [
                self.nodes[0],
                self.nodes[1],
                self.nodes[2],
            ]
        )

        self.assertSequenceEqual(
            self.tree.mock_calls,
            [
            ]
        )

    def test_setitem_non_contiguous_equal_number(self):
        self.root.extend(self.nodes[:3])
        self.tree.mock_calls.clear()

        with self.assertRaisesRegex(
                ValueError,
                "non-contiguous assignments not supported"):
            self.root[0:3:2] = self.nodes[3:]

        self.assertSequenceEqual(
            self.root,
            [
                self.nodes[0],
                self.nodes[1],
                self.nodes[2],
            ]
        )

        self.assertSequenceEqual(
            self.tree.mock_calls,
            [
            ]
        )

    def test_setitem_as_replace(self):
        self.root.extend(self.nodes)
        self.tree.mock_calls.clear()

        self.root[:] = self.nodes

        self.assertSequenceEqual(
            self.tree.mock_calls,
            [
                unittest.mock.call._node_begin_remove_rows(self.root, 0, 4),
                unittest.mock.call._node_end_remove_rows(self.root),
                unittest.mock.call._node_begin_insert_rows(self.root, 0, 4),
                unittest.mock.call._node_end_insert_rows(self.root),
            ]
        )

    def test_setitem_does_not_emit_remove_if_noop(self):
        self.root[:] = self.nodes

        self.assertSequenceEqual(
            self.tree.mock_calls,
            [
                unittest.mock.call._node_begin_insert_rows(self.root, 0, 4),
                unittest.mock.call._node_end_insert_rows(self.root),
            ]
        )

    def test_setitem_does_not_emit_insert_if_noop(self):
        self.root.extend(self.nodes)
        self.tree.mock_calls.clear()

        self.root[:] = []

        self.assertSequenceEqual(
            self.tree.mock_calls,
            [
                unittest.mock.call._node_begin_remove_rows(self.root, 0, 4),
                unittest.mock.call._node_end_remove_rows(self.root),
            ]
        )

    def test_reverse_setitem_does_not_emit_insert_or_remove_if_noop(self):
        self.root[::-1] = []

        self.assertSequenceEqual(
            self.tree.mock_calls,
            [
            ]
        )

    def test_clear_is_efficient(self):
        self.root.extend(self.nodes)
        self.tree.mock_calls.clear()

        self.root.clear()

        self.assertSequenceEqual(
            self.tree.mock_calls,
            [
                unittest.mock.call._node_begin_remove_rows(self.root, 0, 4),
                unittest.mock.call._node_end_remove_rows(self.root),
            ]
        )

    def test_insertion_updates_parent_and_index(self):
        self.root.insert(0, self.nodes[0])
        self.root.append(self.nodes[1])
        self.root.extend(self.nodes[2:])

        self.assertSequenceEqual(
            self.root,
            self.nodes,
        )

        for i, node in enumerate(self.root):
            self.assertIs(node.parent, self.root, i)
            self.assertEqual(node.parent_index, i)

    def test_setitem_single_updates_parent_and_index_on_item(self):
        self.root[:] = self.nodes[:4]

        self.root[0] = self.nodes[4]

        for i, node in enumerate(self.root):
            self.assertIs(node.parent, self.root, i)
            self.assertEqual(node.parent_index, i)

        self.assertIsNone(self.nodes[0].parent)
        self.assertIsNone(self.nodes[0].parent_index)

    def test_setitem_contiguous_updates_parent_and_index_on_new_items(self):
        self.root[:] = self.nodes

        self.assertSequenceEqual(
            self.root,
            self.nodes,
        )

        for i, node in enumerate(self.root):
            self.assertIs(node.parent, self.root, i)
            self.assertEqual(node.parent_index, i)

    def test_setitem_contiguous_updates_parent_and_index_released_items(self):
        self.root.extend(self.nodes)

        self.root[:] = []

        for i, node in enumerate(self.root):
            self.assertIs(node.parent, self.root, i)
            self.assertEqual(node.parent_index, i)

        for node in self.nodes:
            self.assertIsNone(node.parent)
            self.assertIsNone(node.parent_index)

    def test_setitem_contiguous_reverse_updates_parent_and_index_on_items(
            self):
        self.root[:] = self.nodes[:2]
        self.root[::-1] = self.nodes[3:]

        for i, node in enumerate(self.root):
            self.assertIs(node.parent, self.root, i)
            self.assertEqual(node.parent_index, i)

        for node in self.nodes[:2]:
            self.assertIsNone(node.parent)
            self.assertIsNone(node.parent_index)

    def test_insert_shifts_indices(self):
        self.root[:] = self.nodes[:4]
        self.root.insert(0, self.nodes[4])

        for i, node in enumerate(self.root):
            self.assertIs(node.parent, self.root, i)
            self.assertEqual(node.parent_index, i)

    def test_setitem_with_non_equal_length_shifts_indices(self):
        self.root[:] = self.nodes[:2]
        self.root[0:1] = self.nodes[2:]

        for i, node in enumerate(self.root):
            self.assertIs(node.parent, self.root, i)
            self.assertEqual(node.parent_index, i)

    def test_delitem_single_sets_parent_on_deleted(self):
        self.root[:] = self.nodes
        del self.root[0]

        self.assertIsNone(self.nodes[0].parent)
        self.assertIsNone(self.nodes[0].parent_index)

    def test_delitem_single_shifts_indices(self):
        self.root[:] = self.nodes
        del self.root[0]

        for i, node in enumerate(self.root):
            self.assertIs(node.parent, self.root, i)
            self.assertEqual(node.parent_index, i)

    def test_delitem_contiguous_sets_parent_on_deleted(self):
        self.root[:] = self.nodes
        del self.root[:2]

        for i, node in enumerate(self.nodes[:2]):
            self.assertIsNone(node.parent, i)
            self.assertIsNone(node.parent_index, i)

    def test_delitem_contiguous_shifts_indices(self):
        self.root[:] = self.nodes
        del self.root[:2]

        for i, node in enumerate(self.nodes[:2]):
            self.assertIsNone(node.parent, i)
            self.assertIsNone(node.parent_index, i)

    def test_delitem_reverse_contiguous_shifts_indices(self):
        self.root[:] = self.nodes
        del self.root[2::-1]

        for i, node in enumerate(self.nodes[:2]):
            self.assertIsNone(node.parent, i)
            self.assertIsNone(node.parent_index, i)

    def test__insert_moved_nodes_inserts(self):
        self.root[:] = [self.nodes[0], ] + self.nodes[3:]

        self.root._insert_moved_nodes(self.nodes[1:3], 1)

        self.assertSequenceEqual(
            self.root,
            self.nodes
        )

    def test__insert_moved_nodes_inserts_sets_parent_on_items(self):
        self.root._insert_moved_nodes(self.nodes, 0)

        self.assertSequenceEqual(
            self.root,
            self.nodes
        )

    def test__insert_moved_nodes_inserts_does_not_emit_events(self):
        self.root._insert_moved_nodes(self.nodes, 0)

        self.assertSequenceEqual(self.tree.mock_calls, [])

    def test__insert_moved_nodes_shifts_indices(self):
        self.root[:] = [self.nodes[0], ] + self.nodes[3:]

        self.root._insert_moved_nodes(self.nodes[1:3], 1)

        self.assertSequenceEqual(
            self.root,
            self.nodes
        )

    def test__extract_moving_nodes_removes_nodes(self):
        self.root[:] = self.nodes

        extracted = self.root._extract_moving_nodes(slice(1, 3))
        self.assertSequenceEqual(
            extracted,
            self.nodes[1:3]
        )

        self.assertSequenceEqual(
            self.root,
            [self.nodes[0], ] + self.nodes[3:]
        )

    def test__extract_moving_nodes_sets_parent_on_removed(self):
        self.root[:] = self.nodes

        extracted = self.root._extract_moving_nodes(slice(1, 3))
        for node in extracted:
            self.assertIsNone(node.parent)
            self.assertIsNone(node.parent_index)

    def test__extract_moving_nodes_shifts_indices(self):
        self.root[:] = self.nodes

        self.root._extract_moving_nodes(slice(1, 3))

        for i, node in enumerate(self.root):
            self.assertIs(node.parent, self.root, i)
            self.assertEqual(node.parent_index, i)

    def test__extract_moving_nodes_does_not_emit_events(self):
        self.root[:] = self.nodes
        self.tree.mock_calls.clear()

        self.root._extract_moving_nodes(slice(1, 3))

        self.assertSequenceEqual(
            self.tree.mock_calls,
            []
        )

    def test__extract_rejects_non_forward_unity_slice(self):
        self.root[:] = self.nodes

        with self.assertRaises(ValueError):
            self.root._extract_moving_nodes(slice(1, 3, -1))

        with self.assertRaises(ValueError):
            self.root._extract_moving_nodes(slice(1, 3, 2))

    def test_refresh_data(self):
        self.root[:] = self.nodes
        self.tree.mock_calls.clear()

        self.root.refresh_data(
            slice(1, 3)
        )

        self.assertSequenceEqual(
            self.tree.mock_calls,
            [
                unittest.mock.call._node_data_changed(
                    self.root,
                    1, 2,
                    0, 0,
                    None
                )
            ]
        )

    def test_refresh_data_checks_column_range(self):
        self.root[:] = self.nodes
        self.tree.mock_calls.clear()

        with self.assertRaisesRegex(
                ValueError,
                "end column must be greater than or equal to start column"):
            self.root.refresh_data(
                slice(1, 3),
                3, 1
            )

    def test_refresh_data_allows_None_columns(self):
        self.root[:] = self.nodes
        self.tree.mock_calls.clear()

        self.root.refresh_data(
            slice(1, 3),
            None, None,
        )

        self.assertSequenceEqual(
            self.tree.mock_calls,
            [
                unittest.mock.call._node_data_changed(
                    self.root,
                    1, 2,
                    None, None,
                    None
                )
            ]
        )

    def test_refresh_data_sets_colmun2_to_None_if_column1_is_None(self):
        self.root[:] = self.nodes
        self.tree.mock_calls.clear()

        self.root.refresh_data(
            slice(1, 3),
            None,
        )

        self.assertSequenceEqual(
            self.tree.mock_calls,
            [
                unittest.mock.call._node_data_changed(
                    self.root,
                    1, 2,
                    None, None,
                    None
                )
            ]
        )

    def test_refresh_data_rejects_non_unity_non_forward_slice(self):
        self.root[:] = self.nodes
        self.tree.mock_calls.clear()

        with self.assertRaisesRegex(
                ValueError,
                "slice must have stride 1"):
            self.root.refresh_data(
                slice(1, 3, -1),
            )

        with self.assertRaisesRegex(
                ValueError,
                "slice must have stride 1"):
            self.root.refresh_data(
                slice(1, 3, 2),
            )

    def test_refresh_self_uses_refresh_from_parent(self):
        self.root[:] = self.nodes
        self.tree.mock_calls.clear()

        with unittest.mock.patch.object(
                self.root, "refresh_data") as refresh_data:
            self.root[1].refresh_self(
                unittest.mock.sentinel.column1,
                unittest.mock.sentinel.column2,
                unittest.mock.sentinel.roles,
            )

        refresh_data.assert_called_once_with(
            slice(self.root[1].parent_index, self.root[1].parent_index+1),
            unittest.mock.sentinel.column1,
            unittest.mock.sentinel.column2,
            unittest.mock.sentinel.roles,
        )

    def test_refresh_self_defaults(self):
        self.root[:] = self.nodes
        self.tree.mock_calls.clear()

        with unittest.mock.patch.object(
                self.root, "refresh_data") as refresh_data:
            self.root[1].refresh_self()

        refresh_data.assert_called_once_with(
            slice(self.root[1].parent_index, self.root[1].parent_index+1),
            0, 0,
            None,
        )


class TestModelTreeNodeHolder(unittest.TestCase):
    class Holder(ModelTreeNodeHolder):
        def __init__(self):
            self.node = None

        @property
        def _node(self):
            return self.node

    def setUp(self):
        self.tree = ModelTree()
        self.mtnh = self.Holder()
        self.mtnh.node = ModelTreeNode(self.tree)

    def tearDown(self):
        del self.mtnh
        del self.tree

    def test_can_be_inserted(self):
        mtn = ModelTreeNode(self.tree)
        mtn.append(self.mtnh)

        self.assertIn(self.mtnh, mtn)

        self.assertIs(self.mtnh.parent, mtn)
        self.assertIs(self.mtnh.node.parent, mtn)

    def test_can_be_removed(self):
        mtn = ModelTreeNode(self.tree)
        mtn.append(self.mtnh)
        mtn.remove(self.mtnh)

        self.assertNotIn(self.mtnh, mtn)

        self.assertIsNone(self.mtnh.parent)
        self.assertIsNone(self.mtnh.node.parent)

    def test_can_work_with_existing(self):
        self.mtnh2 = self.Holder()
        self.mtnh2.node = ModelTreeNode(self.tree)

        mtn = ModelTreeNode(self.tree)
        mtn.append(self.mtnh)
        mtn.append(self.mtnh2)
        mtn.remove(self.mtnh)

        self.assertNotIn(self.mtnh, mtn)

        self.assertIsNone(self.mtnh.parent)
        self.assertIsNone(self.mtnh.node.parent)


class TestModelTree(unittest.TestCase):
    def setUp(self):
        self.tree = ModelTree()
        self.root = self.tree.root

        self.mock = unittest.mock.Mock()
        for name in ["begin_insert_rows",
                     "end_insert_rows",
                     "begin_move_rows",
                     "end_move_rows",
                     "begin_remove_rows",
                     "end_remove_rows",
                     "data_changed"]:
            m = getattr(self.mock, name)
            m.return_value = None
            getattr(self.tree, name).connect(m)

    def tearDown(self):
        del self.root
        del self.tree
        del self.mock

    def test_root(self):
        self.assertIsInstance(self.root, ModelTreeNode)

    def test__node_begin_insert_rows(self):
        self.tree._node_begin_insert_rows(
            self.root,
            unittest.mock.sentinel.index1,
            unittest.mock.sentinel.index2,
        )

        self.assertSequenceEqual(
            self.mock.mock_calls,
            [
                unittest.mock.call.begin_insert_rows(
                    self.root,
                    unittest.mock.sentinel.index1,
                    unittest.mock.sentinel.index2,
                )
            ]
        )

    def test__node_end_insert_rows(self):
        self.tree._node_end_insert_rows(
            self.root,
        )

        self.assertSequenceEqual(
            self.mock.mock_calls,
            [
                unittest.mock.call.end_insert_rows()
            ]
        )

    def test__node_begin_remove_rows(self):
        self.tree._node_begin_remove_rows(
            self.root,
            unittest.mock.sentinel.index1,
            unittest.mock.sentinel.index2,
        )

        self.assertSequenceEqual(
            self.mock.mock_calls,
            [
                unittest.mock.call.begin_remove_rows(
                    self.root,
                    unittest.mock.sentinel.index1,
                    unittest.mock.sentinel.index2,
                )
            ]
        )

    def test__node_end_remove_rows(self):
        self.tree._node_end_remove_rows(
            self.root,
        )

        self.assertSequenceEqual(
            self.mock.mock_calls,
            [
                unittest.mock.call.end_remove_rows()
            ]
        )

    def test__node_data_changed(self):
        self.tree._node_data_changed(
            self.root,
            unittest.mock.sentinel.index1,
            unittest.mock.sentinel.index2,
            unittest.mock.sentinel.column1,
            unittest.mock.sentinel.column2,
            unittest.mock.sentinel.roles
        )

        self.assertSequenceEqual(
            self.mock.mock_calls,
            [
                unittest.mock.call.data_changed(
                    self.root,
                    (unittest.mock.sentinel.index1,
                     unittest.mock.sentinel.column1),
                    (unittest.mock.sentinel.index2,
                     unittest.mock.sentinel.column2),
                    unittest.mock.sentinel.roles
                )
            ]
        )


class TestJoinedModelListView(unittest.TestCase):
    def setUp(self):
        self.l1 = ModelList(["a1", "a2", "a3"])
        self.l2 = ModelList(["b1", "b2"])
        self.l3 = ModelList(["c1", "c2", "c3", "c4"])
        self.j = JoinedModelListView()
        self.j.append_source(self.l1)
        self.j.append_source(self.l2)
        self.j.append_source(self.l3)
        self.listener = make_listener(self.j)

    def tearDown(self):
        del self.j
        del self.l3
        del self.l2
        del self.l1

    def test_len(self):
        self.j = JoinedModelListView()

        self.assertEqual(len(self.j), 0)

    def test_append_source_emits_events(self):
        self.j = JoinedModelListView()
        self.listener = make_listener(self.j)

        begin_length = None

        def check_length(_, index1, index2):
            nonlocal begin_length
            begin_length = len(self.j)

        self.j.begin_insert_rows.connect(check_length)

        self.j.append_source(self.l1)

        self.listener.begin_insert_rows.assert_called_once_with(
            None,
            0, len(self.l1) - 1,
        )

        self.listener.end_insert_rows.assert_called_once_with()

        self.assertEqual(begin_length, 0)

    def test_append_source_extends_length(self):
        self.j = JoinedModelListView()

        self.j.append_source(self.l1)
        self.assertEqual(len(self.j), len(self.l1))

    def test_append_source_makes_items_accessible(self):
        self.j = JoinedModelListView()

        self.assertSequenceEqual(self.j, [])

        self.j.append_source(self.l1)

        self.assertSequenceEqual(
            self.j,
            self.l1,
        )

    def test_append_multiple_sources(self):
        self.j = JoinedModelListView()
        self.listener = make_listener(self.j)

        begin_length = None

        def check_length(_, index1, index2):
            nonlocal begin_length
            begin_length = len(self.j)

        self.j.begin_insert_rows.connect(check_length)

        self.j.append_source(self.l1)
        self.listener.begin_insert_rows.assert_called_once_with(
            None,
            0, len(self.l1) - 1,
        )
        self.listener.end_insert_rows.assert_called_once_with()
        self.assertEqual(begin_length, 0)

        self.listener.begin_insert_rows.reset_mock()
        self.listener.end_insert_rows.reset_mock()

        self.j.append_source(self.l2)
        self.listener.begin_insert_rows.assert_called_once_with(
            None,
            len(self.l1), len(self.l1) + len(self.l2) - 1,
        )
        self.listener.end_insert_rows.assert_called_once_with()
        self.assertEqual(begin_length, len(self.l1))

        self.listener.begin_insert_rows.reset_mock()
        self.listener.end_insert_rows.reset_mock()

        self.j.append_source(self.l3)
        self.listener.begin_insert_rows.assert_called_once_with(
            None,
            len(self.l1) + len(self.l2),
            len(self.l1) + len(self.l2) + len(self.l3) - 1,
        )
        self.listener.end_insert_rows.assert_called_once_with()
        self.assertEqual(begin_length, len(self.l1) + len(self.l2))

        self.assertSequenceEqual(
            list(self.l1) + list(self.l2) + list(self.l3),
            list(self.j)
        )

    def test_index(self):
        for i, v in enumerate(itertools.chain(self.l1, self.l2, self.l3)):
            self.assertEqual(self.j.index(v), i)

    def test_count(self):
        l4 = ModelList(["a1", "b2", "c4", "a1"])
        self.j.append_source(l4)

        self.assertEqual(self.j.count("a2"), 1)
        self.assertEqual(self.j.count("a1"), 3)
        self.assertEqual(self.j.count("b2"), 2)
        self.assertEqual(self.j.count("c4"), 2)

    def test_contains(self):
        self.assertNotIn("a0", self.j)
        self.assertIn("a1", self.j)
        self.assertNotIn("b3", self.j)
        self.assertIn("b2", self.j)
        self.assertNotIn("c5", self.j)
        self.assertIn("c3", self.j)

    def test_iter(self):
        self.assertSequenceEqual(
            list(iter(self.j)),
            list(self.l1) + list(self.l2) + list(self.l3),
        )

    def test_reversed(self):
        concated = list(self.l1) + list(self.l2) + list(self.l3)
        self.assertSequenceEqual(
            list(reversed(self.j)),
            list(reversed(concated)),
        )

    def test_getitem_slice_contiguous_forward(self):
        self.assertSequenceEqual(
            list(self.l1)[1:] + list(self.l2)[:2],
            self.j[1:5],
        )

    def test_getitem_slice_discontiguous_forward(self):
        self.assertSequenceEqual(
            list(self.l1)[1::2] + list(self.l2)[:1],
            self.j[1:5:2],
        )

    def test_getitem_slice_contiguous_reverse(self):
        self.assertSequenceEqual(
            list(self.l3[1::-1]) +
            list(self.l2[::-1]) +
            list(self.l1[2:1:-1]),
            self.j[6:1:-1],
        )

    def test_getitem_slice_contiguous_reverse(self):
        self.assertSequenceEqual(
            list(self.l3[1::-2]) +
            list(self.l2[::-2]) +
            list(self.l1[2:1:-2]),
            self.j[6:1:-2],
        )

    def test_forward_events_from_source_single_append(self):
        self.l2.append("b3")

        self.listener.begin_insert_rows.assert_called_once_with(
            None,
            len(self.l1) + 2,
            len(self.l1) + 2,
        )
        self.listener.end_insert_rows.assert_called_once_with()

        self.assertSequenceEqual(
            list(self.l1) + list(self.l2) + list(self.l3),
            list(self.j),
        )

        self.assertEqual(self.j[6], "c1")
        self.assertEqual(self.j.index("c1"), len(self.l1) + len(self.l2))

    def test_forward_events_from_source_extend(self):
        self.l2[1:1] = ["i1", "i2"]

        self.listener.begin_insert_rows.assert_called_once_with(
            None,
            len(self.l1) + 1,
            len(self.l1) + 2,
        )
        self.listener.end_insert_rows.assert_called_once_with()

        self.assertSequenceEqual(
            list(self.l1) + list(self.l2) + list(self.l3),
            list(self.j),
        )

        self.assertEqual(self.j[7], "c1")
        self.assertEqual(self.j.index("c1"), len(self.l1) + len(self.l2))

    def test_forward_events_from_source_remove(self):
        del self.l2[0]

        self.listener.begin_remove_rows.assert_called_once_with(
            None,
            len(self.l1),
            len(self.l1),
        )
        self.listener.end_remove_rows.assert_called_once_with()

        self.assertSequenceEqual(
            list(self.l1) + list(self.l2) + list(self.l3),
            list(self.j),
        )

        self.assertEqual(self.j[4], "c1")

    def test_forward_events_from_source_remove_multiple(self):
        self.l2.clear()

        self.listener.begin_remove_rows.assert_called_once_with(
            None,
            len(self.l1),
            len(self.l1) + 1,
        )
        self.listener.end_remove_rows.assert_called_once_with()

        self.assertSequenceEqual(
            list(self.l1) + list(self.l2) + list(self.l3),
            list(self.j),
        )

        self.assertEqual(self.j[3], "c1")
        self.assertEqual(self.j.index("c1"), len(self.l1) + len(self.l2))

    def test_forward_events_from_source_remove_multiple(self):
        self.l2.clear()

        self.listener.begin_remove_rows.assert_called_once_with(
            None,
            len(self.l1),
            len(self.l1) + 1,
        )
        self.listener.end_remove_rows.assert_called_once_with()

        self.assertSequenceEqual(
            list(self.l1) + list(self.l2) + list(self.l3),
            list(self.j),
        )

        self.assertEqual(self.j[3], "c1")
        self.assertEqual(self.j.index("c1"), len(self.l1) + len(self.l2))

    def test_forward_events_from_source_move(self):
        self.l2.move(0, 2)

        self.listener.begin_move_rows.assert_called_once_with(
            None, len(self.l1), len(self.l1),
            None, len(self.l1) + 2,
        )
        self.listener.end_move_rows.assert_called_once_with()

        self.assertSequenceEqual(
            list(self.l1) + list(self.l2) + list(self.l3),
            list(self.j),
        )

        self.assertEqual(self.j[5], "c1")

    def test_forward_events_data_changed(self):
        self.l2.refresh_data(slice(0, 2), 0, 2, ["a", "b"])

        self.listener.data_changed.assert_called_once_with(
            None,
            len(self.l1) + 0, len(self.l1) + 1,
            0, 2,
            ["a", "b"]
        )

    def test_remove_source_emits_events(self):
        begin_length = None

        def check_length(_, index1, index2):
            nonlocal begin_length
            begin_length = len(self.j)

        self.j.begin_remove_rows.connect(check_length)

        self.j.remove_source(self.l2)

        self.listener.begin_remove_rows.assert_called_once_with(
            None,
            len(self.l1),
            len(self.l1) + len(self.l2) - 1
        )

        self.listener.end_remove_rows.assert_called_once_with()

        self.assertEqual(begin_length,
                         len(self.l1) + len(self.l2) + len(self.l3))

    def test_remove_source_removes_elements(self):
        self.j.remove_source(self.l2)

        self.assertEqual(len(self.j), len(self.l1) + len(self.l3))

        self.assertSequenceEqual(
            list(self.l1) + list(self.l3),
            list(self.j),
        )

        self.assertEqual(
            self.j[len(self.l1)],
            self.l3[0],
        )

        self.assertEqual(
            self.j.index("c1"),
            len(self.l1),
        )

        self.assertEqual(
            self.j[len(self.l1) + len(self.l3) - 1],
            self.l3[-1]
        )

    def test_no_forwarding_of_events_from_removed_source(self):
        self.j.remove_source(self.l2)

        self.listener.begin_remove_rows.reset_mock()
        self.listener.end_remove_rows.reset_mock()

        self.l2.append("foo")
        self.l2.move(2, 0)
        del self.l2[0]

        self.l2.refresh_data(slice(0, 2))

        self.listener.begin_insert_rows.assert_not_called()
        self.listener.begin_remove_rows.assert_not_called()
        self.listener.begin_move_rows.assert_not_called()

        self.listener.end_insert_rows.assert_not_called()
        self.listener.end_remove_rows.assert_not_called()
        self.listener.end_move_rows.assert_not_called()

        self.listener.data_changed.assert_not_called()
