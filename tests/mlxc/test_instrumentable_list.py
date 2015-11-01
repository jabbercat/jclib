import collections.abc
import functools
import unittest
import unittest.mock

import aioxmpp.callbacks

from mlxc.instrumentable_list import (
    IList,
    ModelList,
    ModelListView,
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
        self.mock = unittest.mock.Mock()

        self.mock.register_item.return_value = False
        self.mock.unregister_item.return_value = False
        self.mlist.on_register_item.connect(
            self.mock.register_item
        )
        self.mlist.on_unregister_item.connect(
            self.mock.unregister_item
        )

        self.mlist.begin_insert_rows = self.mock.begin_insert_rows
        self.mlist.end_insert_rows = self.mock.end_insert_rows
        self.mlist.begin_remove_rows = self.mock.begin_remove_rows
        self.mlist.end_remove_rows = self.mock.end_remove_rows
        self.mlist.begin_move_rows = self.mock.begin_move_rows
        self.mlist.end_move_rows = self.mock.end_move_rows

    def test_init_bare(self):
        mlist = ModelList()
        self.assertIsInstance(mlist.on_register_item,
                              aioxmpp.callbacks.AdHocSignal)
        self.assertIsInstance(mlist.on_unregister_item,
                              aioxmpp.callbacks.AdHocSignal)
        self.assertIsNone(mlist.begin_insert_rows)
        self.assertIsNone(mlist.end_insert_rows)
        self.assertIsNone(mlist.begin_remove_rows)
        self.assertIsNone(mlist.end_remove_rows)
        self.assertIsNone(mlist.begin_move_rows)
        self.assertIsNone(mlist.end_move_rows)

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
            self.mock.mock_calls,
            [
                unittest.mock.call.begin_insert_rows(None, 0, 0),
                unittest.mock.call.register_item(1),
                unittest.mock.call.end_insert_rows(),
                unittest.mock.call.begin_insert_rows(None, 0, 0),
                unittest.mock.call.register_item(2),
                unittest.mock.call.end_insert_rows(),
                unittest.mock.call.begin_insert_rows(None, 1, 1),
                unittest.mock.call.register_item(3),
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
            self.mock.mock_calls,
            [
                unittest.mock.call.begin_insert_rows(None, 0, 0),
                unittest.mock.call.register_item(1),
                unittest.mock.call.end_insert_rows(),
                unittest.mock.call.begin_insert_rows(None, 0, 0),
                unittest.mock.call.register_item(2),
                unittest.mock.call.end_insert_rows(),
                unittest.mock.call.begin_insert_rows(None, 2, 2),
                unittest.mock.call.register_item(3),
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
            self.mock.mock_calls,
            [
                unittest.mock.call.begin_insert_rows(None, 0, 0),
                unittest.mock.call.register_item(1),
                unittest.mock.call.end_insert_rows(),
                unittest.mock.call.begin_insert_rows(None, 0, 0),
                unittest.mock.call.register_item(2),
                unittest.mock.call.end_insert_rows(),
                unittest.mock.call.begin_insert_rows(None, 1, 1),
                unittest.mock.call.register_item(3),
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
            self.mock.mock_calls,
            [
                unittest.mock.call.begin_insert_rows(None, 0, 0),
                unittest.mock.call.register_item(1),
                unittest.mock.call.end_insert_rows(),
                unittest.mock.call.begin_insert_rows(None, 0, 0),
                unittest.mock.call.register_item(2),
                unittest.mock.call.end_insert_rows(),
                unittest.mock.call.begin_insert_rows(None, 0, 0),
                unittest.mock.call.register_item(3),
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

        self.mock.mock_calls.clear()

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
            self.mock.mock_calls,
            [
                unittest.mock.call.begin_remove_rows(None, 0, 0),
                unittest.mock.call.unregister_item(2),
                unittest.mock.call.end_remove_rows(),
                unittest.mock.call.begin_remove_rows(None, 1, 1),
                unittest.mock.call.unregister_item(1),
                unittest.mock.call.end_remove_rows(),
                unittest.mock.call.begin_remove_rows(None, 0, 0),
                unittest.mock.call.unregister_item(3),
                unittest.mock.call.end_remove_rows(),
            ]
        )

    def test_delitem_single_out_of_bounds(self):
        self.mlist.insert(0, 1)
        self.mlist.insert(0, 2)
        self.mlist.insert(1, 3)

        self.mock.mock_calls.clear()

        with self.assertRaises(IndexError):
            del self.mlist[10]

        with self.assertRaises(IndexError):
            del self.mlist[-10]

        self.assertSequenceEqual(self.mock.mock_calls, [])

    def test_delitem_positive_slice_with_unity_stride(self):
        self.mlist.insert(0, 1)
        self.mlist.insert(0, 2)
        self.mlist.insert(1, 3)

        self.mock.mock_calls.clear()

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
            self.mock.mock_calls,
            [
                unittest.mock.call.begin_remove_rows(None, 1, 2),
                unittest.mock.call.unregister_item(3),
                unittest.mock.call.unregister_item(1),
                unittest.mock.call.end_remove_rows(),
                unittest.mock.call.begin_remove_rows(None, 0, 0),
                unittest.mock.call.unregister_item(2),
                unittest.mock.call.end_remove_rows(),
            ]
        )

    def test_delitem_negative_slice_with_unity_stride(self):
        self.mlist.insert(0, 1)
        self.mlist.insert(0, 2)
        self.mlist.insert(1, 3)

        self.mock.mock_calls.clear()

        del self.mlist[-3:]

        self.assertSequenceEqual(list(self.mlist), [])

        self.assertSequenceEqual(
            self.mock.mock_calls,
            [
                unittest.mock.call.begin_remove_rows(None, 0, 2),
                unittest.mock.call.unregister_item(2),
                unittest.mock.call.unregister_item(3),
                unittest.mock.call.unregister_item(1),
                unittest.mock.call.end_remove_rows(),
            ]
        )

    def test_delitem_negative_slice_with_negative_unity_stride(self):
        self.mlist.insert(0, 1)
        self.mlist.insert(0, 2)
        self.mlist.insert(1, 3)

        self.mock.mock_calls.clear()

        del self.mlist[-1:-4:-1]

        self.assertSequenceEqual(list(self.mlist), [])

        self.assertSequenceEqual(
            self.mock.mock_calls,
            [
                unittest.mock.call.begin_remove_rows(None, 0, 2),
                unittest.mock.call.unregister_item(2),
                unittest.mock.call.unregister_item(3),
                unittest.mock.call.unregister_item(1),
                unittest.mock.call.end_remove_rows(),
            ]
        )

    def test_delitem_positive_slice_with_negative_unity_stride(self):
        self.mlist.insert(0, 1)
        self.mlist.insert(0, 2)
        self.mlist.insert(1, 3)

        self.mock.mock_calls.clear()

        del self.mlist[2:0:-1]

        self.assertSequenceEqual(list(self.mlist), [2])

        self.assertSequenceEqual(
            self.mock.mock_calls,
            [
                unittest.mock.call.begin_remove_rows(None, 1, 2),
                unittest.mock.call.unregister_item(3),
                unittest.mock.call.unregister_item(1),
                unittest.mock.call.end_remove_rows(),
            ]
        )

    def test_delitem_positive_slice_with_non_unity_stride(self):
        self.mlist.insert(0, 1)
        self.mlist.insert(0, 2)
        self.mlist.insert(1, 3)

        self.mock.mock_calls.clear()

        del self.mlist[::2]

        self.assertSequenceEqual(list(self.mlist), [3])

        self.assertSequenceEqual(
            self.mock.mock_calls,
            [
                unittest.mock.call.begin_remove_rows(None, 0, 0),
                unittest.mock.call.unregister_item(2),
                unittest.mock.call.end_remove_rows(),
                unittest.mock.call.begin_remove_rows(None, 1, 1),
                unittest.mock.call.unregister_item(1),
                unittest.mock.call.end_remove_rows(),
            ]
        )

    def test_setitem_single(self):
        self.mlist.insert(0, 1)
        self.mlist.insert(0, 2)
        self.mlist.insert(1, 3)

        self.mock.mock_calls.clear()

        self.mlist[1] = 10

        self.assertSequenceEqual(list(self.mlist), [2, 10, 1])

        self.assertSequenceEqual(
            self.mock.mock_calls,
            [
                unittest.mock.call.begin_remove_rows(None, 1, 1),
                unittest.mock.call.unregister_item(3),
                unittest.mock.call.end_remove_rows(),
                unittest.mock.call.begin_insert_rows(None, 1, 1),
                unittest.mock.call.register_item(10),
                unittest.mock.call.end_insert_rows(),
            ]
        )

    def test_setitem_single_negative(self):
        self.mlist.insert(0, 1)
        self.mlist.insert(0, 2)
        self.mlist.insert(1, 3)

        self.mock.mock_calls.clear()

        self.mlist[-1] = 10

        self.assertSequenceEqual(list(self.mlist), [2, 3, 10])

        self.assertSequenceEqual(
            self.mock.mock_calls,
            [
                unittest.mock.call.begin_remove_rows(None, 2, 2),
                unittest.mock.call.unregister_item(1),
                unittest.mock.call.end_remove_rows(),
                unittest.mock.call.begin_insert_rows(None, 2, 2),
                unittest.mock.call.register_item(10),
                unittest.mock.call.end_insert_rows(),
            ]
        )

    def test_setitem_out_of_bounds(self):
        self.mlist.insert(0, 1)
        self.mlist.insert(0, 2)
        self.mlist.insert(1, 3)

        self.mock.mock_calls.clear()

        with self.assertRaises(IndexError):
            self.mlist[10] = 10

        with self.assertRaises(IndexError):
            self.mlist[-10] = 10

        self.assertSequenceEqual(list(self.mlist), [2, 3, 1])

        self.assertSequenceEqual(
            self.mock.mock_calls,
            [
            ]
        )

    def test_setitem_positive_slice_with_unity_stride(self):
        self.mlist.insert(0, 1)
        self.mlist.insert(0, 2)
        self.mlist.insert(1, 3)

        self.mock.mock_calls.clear()

        self.mlist[1:] = [10, 11, 12]

        self.assertSequenceEqual(list(self.mlist), [2, 10, 11, 12])

        self.assertSequenceEqual(
            self.mock.mock_calls,
            [
                unittest.mock.call.begin_remove_rows(None, 1, 2),
                unittest.mock.call.unregister_item(3),
                unittest.mock.call.unregister_item(1),
                unittest.mock.call.end_remove_rows(),
                unittest.mock.call.begin_insert_rows(None, 1, 3),
                unittest.mock.call.register_item(10),
                unittest.mock.call.register_item(11),
                unittest.mock.call.register_item(12),
                unittest.mock.call.end_insert_rows(),
            ]
        )

    def test_setitem_negative_slice_with_unity_stride(self):
        self.mlist.insert(0, 1)
        self.mlist.insert(0, 2)
        self.mlist.insert(1, 3)

        self.mock.mock_calls.clear()

        self.mlist[-1:] = [10, 11, 12]

        self.assertSequenceEqual(list(self.mlist), [2, 3, 10, 11, 12])

        self.assertSequenceEqual(
            self.mock.mock_calls,
            [
                unittest.mock.call.begin_remove_rows(None, 2, 2),
                unittest.mock.call.unregister_item(1),
                unittest.mock.call.end_remove_rows(),
                unittest.mock.call.begin_insert_rows(None, 2, 4),
                unittest.mock.call.register_item(10),
                unittest.mock.call.register_item(11),
                unittest.mock.call.register_item(12),
                unittest.mock.call.end_insert_rows(),
            ]
        )

    def test_setitem_negative_slice_with_negative_unity_stride(self):
        self.mlist.insert(0, 1)
        self.mlist.insert(0, 2)
        self.mlist.insert(1, 3)

        self.mock.mock_calls.clear()

        self.mlist[-1:-4:-1] = [10, 11, 12]

        self.assertSequenceEqual(list(self.mlist), [10, 11, 12])

        self.assertSequenceEqual(
            self.mock.mock_calls,
            [
                unittest.mock.call.begin_remove_rows(None, 0, 2),
                unittest.mock.call.unregister_item(2),
                unittest.mock.call.unregister_item(3),
                unittest.mock.call.unregister_item(1),
                unittest.mock.call.end_remove_rows(),
                unittest.mock.call.begin_insert_rows(None, 0, 2),
                unittest.mock.call.register_item(10),
                unittest.mock.call.register_item(11),
                unittest.mock.call.register_item(12),
                unittest.mock.call.end_insert_rows(),
            ]
        )

    def test_setitem_positive_slice_with_negative_unity_stride(self):
        self.mlist.insert(0, 1)
        self.mlist.insert(0, 2)
        self.mlist.insert(1, 3)

        self.mock.mock_calls.clear()

        self.mlist[2:0:-1] = [10, 11, 12]

        self.assertSequenceEqual(list(self.mlist), [2, 10, 11, 12])

        self.assertSequenceEqual(
            self.mock.mock_calls,
            [
                unittest.mock.call.begin_remove_rows(None, 1, 2),
                unittest.mock.call.unregister_item(3),
                unittest.mock.call.unregister_item(1),
                unittest.mock.call.end_remove_rows(),
                unittest.mock.call.begin_insert_rows(None, 1, 3),
                unittest.mock.call.register_item(10),
                unittest.mock.call.register_item(11),
                unittest.mock.call.register_item(12),
                unittest.mock.call.end_insert_rows(),
            ]
        )

    def test_setitem_slice_with_non_unity_stride(self):
        self.mlist.insert(0, 1)
        self.mlist.insert(0, 2)
        self.mlist.insert(1, 3)

        self.mock.mock_calls.clear()

        with self.assertRaisesRegex(
                IndexError,
                "non-unity strides not supported"):
            self.mlist[::2] = [1, 2, 3]

        with self.assertRaisesRegex(
                IndexError,
                "non-unity strides not supported"):
            self.mlist[::-2] = [1, 2, 3]

        self.assertSequenceEqual(
            self.mock.mock_calls,
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

        self.mock.mock_calls.clear()

        self.mlist.move(2, 4)

        self.assertSequenceEqual(
            list(self.mlist),
            [
                0, 1, 3, 2, 4, 5
            ]
        )

        self.assertSequenceEqual(
            self.mock.mock_calls,
            [
                unittest.mock.call.begin_move_rows(None, 2, 2, None, 4),
                unittest.mock.call.end_move_rows(),
            ]
        )

    def test_move_forward_with_negative_indices(self):
        self.mlist[:] = [0, 1, 2, 3, 4, 5]

        self.mock.mock_calls.clear()

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
            self.mock.mock_calls,
            [
                unittest.mock.call.begin_move_rows(None, 2, 2, None, 5),
                unittest.mock.call.end_move_rows(),
                unittest.mock.call.begin_move_rows(None, 3, 3, None, 5),
                unittest.mock.call.end_move_rows(),
            ]
        )

    def test_move_backward(self):
        self.mlist[:] = [0, 1, 2, 3, 4, 5]

        self.mock.mock_calls.clear()

        self.mlist.move(2, 0)

        self.assertSequenceEqual(
            list(self.mlist),
            [
                2, 0, 1, 3, 4, 5
            ]
        )

        self.assertSequenceEqual(
            self.mock.mock_calls,
            [
                unittest.mock.call.begin_move_rows(None, 2, 2, None, 0),
                unittest.mock.call.end_move_rows(),
            ]
        )

    def test_move_backward_with_negative_indices(self):
        self.mlist[:] = [0, 1, 2, 3, 4, 5]

        self.mock.mock_calls.clear()

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
            self.mock.mock_calls,
            [
                unittest.mock.call.begin_move_rows(None, 5, 5, None, 0),
                unittest.mock.call.end_move_rows(),
                unittest.mock.call.begin_move_rows(None, 5, 5, None, 0),
                unittest.mock.call.end_move_rows(),
            ]
        )

    def test_move_rejects_out_of_bounds_indices(self):
        self.mlist[:] = [0, 1, 2, 3, 4, 5]

        self.mock.mock_calls.clear()

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

        self.mock.mock_calls.clear()

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
            self.mock.mock_calls,
            [
            ]
        )

    def test_move_ignores_invalid_move(self):
        self.mlist[:] = [0, 1, 2, 3, 4, 5]

        self.mock.mock_calls.clear()

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
            self.mock.mock_calls,
            [
            ]
        )

    def test_reverse_with_odd_item_count_uses_move(self):
        self.mlist[:] = [1, 2, 3, 4, 5]

        self.mock.mock_calls.clear()

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

        self.mock.mock_calls.clear()

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

        self.mock.mock_calls.clear()

        self.assertEqual(self.mlist.pop(1), 2)

        self.assertSequenceEqual(
            self.mock.mock_calls,
            [
                unittest.mock.call.begin_remove_rows(None, 1, 1),
                unittest.mock.call.unregister_item(2),
                unittest.mock.call.end_remove_rows(),
            ]
        )

    def test_pop_negative_index(self):
        self.mlist[:] = [1, 2, 3]

        self.mock.mock_calls.clear()

        self.assertEqual(self.mlist.pop(-1), 3)

        self.assertSequenceEqual(
            self.mock.mock_calls,
            [
                unittest.mock.call.begin_remove_rows(None, 2, 2),
                unittest.mock.call.unregister_item(3),
                unittest.mock.call.end_remove_rows(),
            ]
        )

    def test_pop_rejects_out_of_bounds_indices(self):
        self.mlist[:] = [1, 2, 3]

        self.mock.mock_calls.clear()

        with self.assertRaises(IndexError):
            self.mlist.pop(10)

        with self.assertRaises(IndexError):
            self.mlist.pop(-10)

        self.assertSequenceEqual(
            self.mock.mock_calls,
            [
            ]
        )

    def test_pop_without_index(self):
        self.mlist[:] = [1, 2, 3]

        self.mock.mock_calls.clear()

        self.mlist.pop()

        self.assertSequenceEqual(
            self.mock.mock_calls,
            [
                unittest.mock.call.begin_remove_rows(None, 2, 2),
                unittest.mock.call.unregister_item(3),
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
        self.mock.mock_calls.clear()

        self.mlist.clear()

        self.assertSequenceEqual(
            self.mock.mock_calls,
            [
                unittest.mock.call.begin_remove_rows(None, 0, 2),
                unittest.mock.call.unregister_item(1),
                unittest.mock.call.unregister_item(2),
                unittest.mock.call.unregister_item(3),
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
                unittest.mock.call(1),
                unittest.mock.call(3),
                unittest.mock.call(2),
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


class TestModelListView(unittest.TestCase):
    def setUp(self):
        self.mock = unittest.mock.Mock()
        self.backend = ModelList()
        self.view = ModelListView(self.backend)

        self.view.begin_insert_rows = self.mock.begin_insert_rows
        self.view.end_insert_rows = self.mock.end_insert_rows
        self.view.begin_remove_rows = self.mock.begin_remove_rows
        self.view.end_remove_rows = self.mock.end_remove_rows
        self.view.begin_move_rows = self.mock.begin_move_rows
        self.view.end_move_rows = self.mock.end_move_rows

    def test_init(self):
        backend = ModelList()
        view = ModelListView(self.backend)

        self.assertIsNone(view.begin_insert_rows)
        self.assertIsNone(view.begin_move_rows)
        self.assertIsNone(view.begin_remove_rows)

        self.assertIsNone(view.end_insert_rows)
        self.assertIsNone(view.end_move_rows)
        self.assertIsNone(view.end_remove_rows)

        view._begin_insert_rows(object(), object(), object())
        view._begin_move_rows(object(), object(), object(), object(), object())
        view._begin_remove_rows(object(), object(), object())

        view._end_insert_rows()
        view._end_move_rows()
        view._end_remove_rows()

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
        self.assertEqual(self.backend.begin_insert_rows,
                         self.view._begin_insert_rows)
        self.assertEqual(self.backend.begin_move_rows,
                         self.view._begin_move_rows)
        self.assertEqual(self.backend.begin_remove_rows,
                         self.view._begin_remove_rows)
        self.assertEqual(self.backend.end_insert_rows,
                         self.view._end_insert_rows)
        self.assertEqual(self.backend.end_move_rows,
                         self.view._end_move_rows)
        self.assertEqual(self.backend.end_remove_rows,
                         self.view._end_remove_rows)

    def test__begin_insert_rows(self):
        a, b, c = object(), object(), object()
        self.view._begin_insert_rows(a, b, c)
        self.mock.begin_insert_rows.assert_called_with(a, b, c)

    def test__begin_move_rows(self):
        a, b, c, d, e = object(), object(), object(), object(), object()
        self.view._begin_move_rows(a, b, c, d, e)
        self.mock.begin_move_rows.assert_called_with(a, b, c, d, e)

    def test__begin_remove_rows(self):
        a, b, c = object(), object(), object()
        self.view._begin_remove_rows(a, b, c)
        self.mock.begin_remove_rows.assert_called_with(a, b, c)

    def test__end_insert_rows(self):
        self.view._end_insert_rows()
        self.mock.end_insert_rows.assert_called_with()

    def test__end_move_rows(self):
        self.view._end_move_rows()
        self.mock.end_move_rows.assert_called_with()

    def test__end_remove_rows(self):
        self.view._end_remove_rows()
        self.mock.end_remove_rows.assert_called_with()

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
