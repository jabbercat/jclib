import abc
import collections.abc
import contextlib
import weakref

import aioxmpp.callbacks


class IList(collections.abc.MutableSequence):
    """
    Create and return a new instrumented list. An :class:`IList` instance is a
    mutable sequence where addition and removal of elements can be hooked into
    with signals.

    If `iterable` is not :data:`None`, the items from the iterable are inserted
    into the list right away. This obviously misses the callbacks, as no
    callbacks have been registered yet.

    .. method:: on_register_item(item)

       This signal is called whenever an item is inserted into the list in any
       way (e.g. by item assignment, call to :meth:`append`, :meth:`insert`,
       …).

       .. note::

          A non-obvious situation in which this signal is fired is when during
          a bulk removal (clear, `del` operator with a slice or the likes), a
          call to :meth:`on_unregister_item` raises an exception. In that case,
          all items which have already had their call to
          :meth:`on_unregister_item` will be re-registered.

    .. method:: on_unregister_item(item)

       This signal is called whenever an item is removed from the list in any
       way (e.g. by item assignment, call to :meth:`remove`,
       `del` operator, ...).

       .. warning::

          Raising from a callback registered with :meth:`on_unregister_item`
          will abort the deletion operation. The item (and any other items
          which were about to be deleted) remain in the list and the exception
          is re-raised from the deletion method.

          In general, it is better to avoid raising from functions directly
          connected to the :meth:`on_unregister_item` signal.

          If aioxmpp version >= 0.5 is used, raising from a signal has no
          effect, as signals provide full isolation.

    The usual methods and operators of a mutable sequence are available. All
    methods and operators which return a new sequence will return a plain
    :class:`list` instead of a new :class:`IList`.
    """

    on_register_item = aioxmpp.callbacks.Signal()
    on_unregister_item = aioxmpp.callbacks.Signal()

    def __init__(self, iterable=None):
        super().__init__()
        if iterable is not None:
            self._storage = list(iterable)
        else:
            self._storage = []

    def _unregister_slice(self, sl):
        items = self[sl]
        i = None
        # this is a rather interesting use of ExitStack: we add the
        # on_register_item calls for each unregistered item to the stack; they
        # will be called when the stack unwinds due to an exception. The call
        # to .pop_all() at the end of the with-block prevents them from being
        # called when the with-block is left without an exception.
        with contextlib.ExitStack() as stack:
            for i, item in enumerate(items):
                self.on_unregister_item(item)
                stack.callback(self.on_register_item, item)
            stack.pop_all()

    def __len__(self):
        return len(self._storage)

    def __getitem__(self, index):
        return self._storage[index]

    def __delitem__(self, index):
        if isinstance(index, slice):
            # multiple items
            self._unregister_slice(index)
            del self._storage[index]
        else:
            item = self[index]
            self.on_unregister_item(item)
            del self._storage[index]

    def __setitem__(self, index, item):
        if isinstance(index, slice):
            items = item
            self._unregister_slice(index)
            self._storage[index] = items
            for item in items:
                self.on_register_item(item)
        else:
            old_item = self[index]
            self.on_unregister_item(old_item)
            self._storage[index] = item
            self.on_register_item(item)

    def insert(self, index, item):
        self._storage.insert(index, item)
        self.on_register_item(item)

    def reverse(self):
        self._storage.reverse()


class ModelList(collections.abc.MutableSequence):
    """
    A model list is a mutable sequence suitable for use with Qt-like list
    models. The consturctor forwards the keyword arguments to the next classes
    in the resolution order.

    It provides the following callbacks which notify the user about list
    mutation. Note that all these are simple attributes which default to
    :data:`None` and to which a user can assign callables; these are no
    signals.

    .. method:: begin_insert_rows(_, index1, index2)

       This signal is called before rows are inserted at `index1` up to
       (including) `index2`. The existing rows are not removed. The number of
       rows inserted is `index2-index1+1`.

       The first argument is always :data:`None`. This is for consistency with
       future tree-like models, which will use that argument to pass
       information about the parent item in which the change occurs. This is
       analogous (but not directly compatible) to the :meth:`beginInsertRows`
       method of :class:`QAbstractItemModel`.

    .. method:: end_insert_rows()

       This signal is called after rows have been inserted.

    .. method:: begin_remove_rows(_, index1, index2)

       This signal is called before rows are removed from `index1` up to (and
       including) `index2`.

       The same note as for :meth:`begin_insert_rows` holds for the first
       argument.

    .. method:: end_remove_rows()

       This signal is called after rows have been removed.

    .. method:: begin_move_rows(_, srcindex1, srcindex2, _, destindex)

       This signal is called before rows are moved from `srcindex1` to
       `destindex`. The rows which are being moved are those addressed by the
       indices from `srcindex1` up to (and including) `srcindex2`.

       Note that the rows are inserted such that they always appear in front of
       the item which is addressed by `destindex` *before* the rows are removed
       for moving.

       The same note as for :meth:`begin_insert_rows` holds for the first
       and fourth argument.

    .. method:: end_move_rows()

       This signal is called after rows have been moved.

    .. method:: data_changed(_, index1, index2, column1, column2, roles)

        This signal is called from :meth:`refresh_data`. It is never emitted
        automatically.

        The arguments are those passed to :meth:`refresh_data`; the first
        argument is always :data:`None`.

    The above attributes are called whenever neccessary by the mutable sequence
    implementation. In addition, signals having an identical function to those
    found in :class:`IList` are found:

    .. method:: on_register_item(item, index)

       A :class:`aioxmpp.callbacks.Signal` which is called whenever an entry is
       newly added to the list. It is called after the item has been added to
       the backing storage, it can thus already been found in the list.

       It is called between :meth:`begin_insert_rows` and
       :meth:`end_insert_rows`. Methods connected directly to this signal
       **must not** raise. If they do, the list is left in an inconsistent
       state.

       In future versions, exceptions might be silently swallowed or re-raised
       after the insertion operation has been completed. Aborting an insertion
       operation is not possible due to constraints in the API provided by the
       above callbacks.

       In contrast to :meth:`begin_insert_rows`, :meth:`on_register_item` is
       also called during initialisation.

    .. method:: on_unregister_item(item)

       A :class:`aioxmpp.callbacks.Signal` which is called whenever an entry is
       finally removed from the list. It is called while the item is still in
       the list.

       With respect to exceptions, the same conditions as for
       :meth:`on_register_item` hold.

    Note that :meth:`on_register_item` and :meth:`on_unregister_item` are not
    called during :meth:`move` operations, as the items stay in the list.

    The usual methods and operators of mutable sequences are
    available. For some methods special rules hold and others have been addded:

    .. automethod:: move

    .. automethod:: reverse

    """

    on_register_item = aioxmpp.callbacks.Signal()
    on_unregister_item = aioxmpp.callbacks.Signal()

    begin_insert_rows = aioxmpp.callbacks.Signal()
    end_insert_rows = aioxmpp.callbacks.Signal()
    begin_remove_rows = aioxmpp.callbacks.Signal()
    end_remove_rows = aioxmpp.callbacks.Signal()
    begin_move_rows = aioxmpp.callbacks.Signal()
    end_move_rows = aioxmpp.callbacks.Signal()
    data_changed = aioxmpp.callbacks.Signal()

    def __init__(self, initial=(), **kwargs):
        super().__init__(**kwargs)
        items = list(initial)
        self._storage = items
        self._register_items(items, 0)

    def _check_and_normalize_index(self, index):
        if abs(index) > len(self._storage) or index == len(self._storage):
            raise IndexError("list index out of bounds")
        if index < 0:
            return index % len(self._storage)
        return index

    def _register_items(self, items, base_index):
        for i, item in enumerate(items):
            self.on_register_item(item, base_index + i)

    def _unregister_items(self, items):
        for item in items:
            self.on_unregister_item(item)

    def _begin_insert_rows(self, index1, index2):
        self.begin_insert_rows(None, index1, index2)

    def _end_insert_rows(self):
        self.end_insert_rows()

    def _begin_remove_rows(self, index1, index2):
        self.begin_remove_rows(None, index1, index2)

    def _end_remove_rows(self):
        self.end_remove_rows()

    def _begin_move_rows(self, index1, index2, destindex):
        self.begin_move_rows(None, index1, index2,
                             None, destindex)

    def _end_move_rows(self):
        self.end_move_rows()

    def __len__(self):
        return len(self._storage)

    def __getitem__(self, index):
        return self._storage[index]

    def __delitem__(self, index):
        if isinstance(index, slice):
            start, end, stride = index.indices(len(self._storage))
            if stride == 1:
                self._begin_remove_rows(start, end - 1)
                self._unregister_items(self._storage[index])
                del self._storage[index]
                self._end_remove_rows()
            elif stride == -1:
                self._begin_remove_rows(end + 1, start)
                self._unregister_items(reversed(self._storage[index]))
                del self._storage[index]
                self._end_remove_rows()
            else:
                # we have to resolve non-unity strides one by one due to hook
                # constraints
                ndeleted = 0
                for i in range(start, end, stride):
                    del self[i - ndeleted]
                    ndeleted += 1
            return

        index = self._check_and_normalize_index(index)

        self._begin_remove_rows(index, index)
        self._unregister_items([self._storage[index]])
        del self._storage[index]
        self._end_remove_rows()

    def __setitem__(self, index, item):
        if isinstance(index, slice):
            items = list(item)
            start, end, stride = index.indices(len(self._storage))
            if stride == 1:
                if start != end:
                    self._begin_remove_rows(start, end - 1)
                    self._unregister_items(self._storage[index])
                    del self._storage[index]
                    self._end_remove_rows()
                self._begin_insert_rows(start, len(items) + start - 1)
                self._storage[start:start] = items
                self._register_items(items, start)
                self._end_insert_rows()
            elif stride == -1:
                if start - end != len(items):
                    raise ValueError(
                        "attempt to assign sequence of size {}"
                        " to extended slice of size {}".format(
                            len(items),
                            start - end
                        )
                    )
                self._begin_remove_rows(end + 1, start)
                self._unregister_items(reversed(self._storage[index]))
                del self._storage[index]
                self._end_remove_rows()
                self._begin_insert_rows(end + 1, len(items) + end)
                self._storage[end + 1:end + 1] = items
                self._register_items(items, end + 1)
                self._end_insert_rows()
            else:
                raise IndexError("non-unity strides not supported")
            return

        index = self._check_and_normalize_index(index)
        self._begin_remove_rows(index, index)
        self._unregister_items([self._storage[index]])
        del self._storage[index]
        self._end_remove_rows()
        self._begin_insert_rows(index, index)
        self._storage.insert(index, item)
        self._register_items([item], index)
        self._end_insert_rows()

    def insert(self, index, item):
        if index > len(self._storage):
            index = len(self._storage)
        elif index < 0:
            if index < -len(self._storage):
                index = 0
            else:
                index = index % len(self._storage)

        self._begin_insert_rows(index, index)
        self._storage.insert(index, item)
        self._register_items([item], index)
        self._end_insert_rows()

    def move(self, index1, index2):
        """
        Move a row from `index1` to `index2`. The row is re-inserted in front
        of the item which is addressed by `index2` at the time :meth:`move` is
        called.
        """
        index1 = self._check_and_normalize_index(index1)

        if index2 != len(self._storage):
            index2 = self._check_and_normalize_index(index2)

        if index1 == index2 or index1 == index2 - 1:
            return

        self._begin_move_rows(index1, index1, index2)
        if index2 > index1:
            index2 -= 1
        item = self._storage.pop(index1)
        self._storage.insert(index2, item)
        self._end_move_rows()

    def reverse(self):
        """
        Reverses the contents of the model list.

        The implementation of reverse is not optimal for performance, as it
        uses :meth:`move`. This is for better user experience, as selections in
        views which use the :class:`ModelList` will still work (and anything
        else which requires persistent indices).
        """

        upper = len(self._storage)
        for i in range(len(self._storage) // 2):
            self.move(i, upper)
            if upper - 2 > i:
                self.move(upper - 2, i)
            upper -= 1

    def pop(self, index=-1):
        index = self._check_and_normalize_index(index)
        self._begin_remove_rows(index, index)
        self._unregister_items([self._storage[index]])
        result = self._storage.pop(index)
        self._end_remove_rows()
        return result

    def clear(self):
        del self[:]

    def refresh_data(self, slice, column1=0, column2=0, roles=None):
        if column1 is None:
            if column2 == 0:
                column2 = None
            elif column2 is not None:
                raise ValueError(
                    "either both or no columns must be None"
                )

        if column1 is not None and column2 < column1:
            raise ValueError(
                "end column must be greater than or equal to start column"
            )

        start, end, stride = slice.indices(len(self))
        if stride != 1:
            raise ValueError("slice must have stride 1")

        self.data_changed(
            None,
            start, end - 1,
            column1, column2,
            roles,
        )


class ModelListView(collections.abc.Sequence):
    begin_insert_rows = aioxmpp.callbacks.Signal()
    end_insert_rows = aioxmpp.callbacks.Signal()
    begin_remove_rows = aioxmpp.callbacks.Signal()
    end_remove_rows = aioxmpp.callbacks.Signal()
    begin_move_rows = aioxmpp.callbacks.Signal()
    end_move_rows = aioxmpp.callbacks.Signal()

    def __init__(self, backend):
        super().__init__()
        self._backend = backend
        self._backend.begin_insert_rows.connect(self.begin_insert_rows)
        self._backend.begin_move_rows.connect(self.begin_move_rows)
        self._backend.begin_remove_rows.connect(self.begin_remove_rows)
        self._backend.end_insert_rows.connect(self.end_insert_rows)
        self._backend.end_move_rows.connect(self.end_move_rows)
        self._backend.end_remove_rows.connect(self.end_remove_rows)

    def __getitem__(self, index):
        return self._backend[index]

    def __len__(self):
        return len(self._backend)

    def __iter__(self):
        return iter(self._backend)

    def __reversed__(self):
        return reversed(self._backend)

    def __contains__(self, item):
        return item in self._backend

    def index(self, item):
        return self._backend.index(item)

    def count(self, item):
        return self._backend.count(item)


class ModelTreeNode(collections.abc.MutableSequence):
    def __init__(self, tree):
        super().__init__()
        self._items = []
        self._tree = tree
        self._parent = None
        self._parent_index = None

    @property
    def parent(self):
        return self._parent

    @property
    def parent_index(self):
        return self._parent_index

    def _set_parent(self, new_parent, new_parent_index):
        assert new_parent is None or new_parent._tree is self._tree
        self._parent = new_parent
        self._parent_index = new_parent_index

    def _adopt_items(self, items, base_index, stride):
        for i, item in enumerate(items):
            assert item.parent is None
            item._set_parent(self, base_index + i * stride)

    def _release_items(self, items):
        for item in items:
            assert item.parent is self
            item._set_parent(None, None)

    def _shift_indices(self, slice_, offset):
        assert isinstance(slice_, slice)
        for item in self._items[slice_]:
            item._parent_index += offset

    def _insert_moved_nodes(self, nodes, indexdest):
        if not hasattr(nodes, "__len__"):
            nodes = list(nodes)

        self._items[indexdest:indexdest] = nodes
        self._adopt_items(
            self._items[indexdest:indexdest + len(nodes)],
            indexdest,
            1,
        )
        self._shift_indices(
            slice(indexdest + len(nodes), None),
            len(nodes)
        )

    def _extract_moving_nodes(self, slice_):
        start, stop, step = slice_.indices(len(self._items))
        if step != 1:
            raise ValueError("non-unity non-forward slices not supported")

        result = self._items[slice_]
        self._release_items(result)
        self._shift_indices(slice(stop, None), start - stop)
        del self._items[slice_]
        return result

    def _check_and_normalize_index(self, index):
        if abs(index) > len(self._items) or index == len(self._items):
            raise IndexError("list index out of bounds")
        if index < 0:
            return index % len(self._items)
        return index

    def __delitem__(self, slice_):
        if isinstance(slice_, slice):
            start, stop, step = slice_.indices(len(self._items))
            if start == stop:
                return

            if step == -1:
                start, stop = stop + 1, start + 1
                step = 1

            if step != 1 and step > 0:
                ndeleted = 0
                for index in range(*slice_.indices(len(self._items))):
                    del self[index - ndeleted]
                    ndeleted += 1
                return
            elif step < 0:
                for index in range(*slice_.indices(len(self._items))):
                    del self[index]
                return

            self._tree._node_begin_remove_rows(
                self,
                start,
                stop - 1)
            self._release_items(self._items[slice_])
            self._shift_indices(slice(stop, None), start - stop)
            del self._items[slice_]
            self._tree._node_end_remove_rows(self)
            return

        index = self._check_and_normalize_index(slice_)
        self._tree._node_begin_remove_rows(self, index, index)
        self._release_items([self._items[index]])
        self._shift_indices(slice(index + 1, None), -1)
        del self._items[index]
        self._tree._node_end_remove_rows(self)

    def __getitem__(self, slice_):
        return self._items[slice_]

    def __setitem__(self, slice_, items):
        if isinstance(slice_, slice):
            items = list(items)
            start, stop, step = slice_.indices(len(self._items))

            if step == 1:
                if start != stop:
                    self._tree._node_begin_remove_rows(self, start, stop - 1)
                    self._release_items(self._items[slice_])
                    self._shift_indices(slice(stop, None), -(stop - start))
                    del self._items[slice_]
                    self._tree._node_end_remove_rows(self)
                if items:
                    self._tree._node_begin_insert_rows(self,
                                                       start,
                                                       start + len(items) - 1)
                    self._items[start:start] = items
                    self._adopt_items(
                        self._items[start:start + len(items)],
                        start,
                        1
                    )
                    self._shift_indices(slice(start + len(items), None),
                                        len(items))
                    self._tree._node_end_insert_rows(self)
            elif step == -1:
                if start - stop != len(items):
                    raise ValueError(
                        "attempt to assign sequence of size {}"
                        " to extended slice of size {}".format(
                            len(items),
                            start - stop
                        )
                    )

                if start == stop:
                    return

                start, stop = stop + 1, start + 1
                step = 1
                self._tree._node_begin_remove_rows(self, start, stop - 1)
                self._release_items(self._items[slice_])
                del self._items[slice_]
                self._tree._node_end_remove_rows(self)
                self._tree._node_begin_insert_rows(self,
                                                   start,
                                                   start + len(items) - 1)
                self._items[start:start] = reversed(items)
                self._adopt_items(
                    self._items[start:start + len(items)],
                    start,
                    1
                )
                self._tree._node_end_insert_rows(self)
            else:
                raise ValueError(
                    "non-contiguous assignments not supported"
                )

            return

        index = self._check_and_normalize_index(slice_)
        self._tree._node_begin_remove_rows(self, index, index)
        self._release_items([self._items[index]])
        self._shift_indices(slice(index + 1, None), -1)
        del self._items[index]
        self._tree._node_end_remove_rows(self)
        self._tree._node_begin_insert_rows(self, index, index)
        self._items.insert(index, items)
        self._adopt_items([items], index, 1)
        self._shift_indices(slice(index + 1, None), 1)
        self._tree._node_end_insert_rows(self)

    def __len__(self):
        return len(self._items)

    def insert(self, index, item):
        if index != len(self):
            index = self._check_and_normalize_index(index)

        self._tree._node_begin_insert_rows(self, index, index)
        self._items.insert(index, item)
        self._shift_indices(slice(index + 1, None), 1)
        self._adopt_items([item], index, 1)
        self._tree._node_end_insert_rows(self)

    def extend(self, items):
        if not hasattr(items, "__len__"):
            items = list(items)

        start = len(self._items)

        self._tree._node_begin_insert_rows(
            self,
            start,
            start + len(items) - 1
        )
        self._items.extend(items)
        self._adopt_items(self._items[start:], start, 1)
        self._tree._node_end_insert_rows(self)

    def clear(self):
        del self[:]

    def __repr__(self):
        return "<{}.{} in {} with {!r} at 0x{:x}>".format(
            type(self).__module__,
            type(self).__name__,
            self._tree,
            self._items,
            id(self)
        )

    def refresh_data(self, slice_, column1=0, column2=0, roles=None):
        if column1 is None and column2 == 0:
            column2 = None

        if column1 is not None and column2 is not None and column2 < column1:
            raise ValueError(
                "end column must be greater than or equal to start column"
            )

        start, stop, step = slice_.indices(len(self._items))
        if step != 1:
            raise ValueError("slice must have stride 1")

        self._tree._node_data_changed(
            self, start, stop - 1,
            column1,
            column2,
            roles,
        )

    def refresh_self(self, column1=0, column2=0, roles=None):
        self.parent.refresh_data(
            slice(self.parent_index, self.parent_index + 1),
            column1, column2,
            roles,
        )


class ModelTreeNodeHolder(metaclass=abc.ABCMeta):
    """
    :class:`ModelTreeNodeHolder` can be used as mix-in in situations where
    tree-node like functionality is desired, but it is not desirable to inherit
    from :class:`ModelTreeNode`.

    To use :class:`ModelTreeNodeHolder`, a class must provide the :attr:`_node`
    property implementation. It must provide access to the
    :class:`ModelTreeNode` which represents the position of the object in the
    tree. Even though the :attr:`_node` may be :data:`None` on construction, it
    is required that the :attr:`_node` is properly initialised with a
    :class:`ModelTreeNode` when an object of a class inheriting from
    :class:`ModelTreeNodeHolder` is inserted into the tree.

    .. automethod:: _set_parent

    .. autoattribute:: _node

    .. autoattribute:: parent

    .. autoattribute:: _parent_index
    """

    @abc.abstractproperty
    def _node(self):
        """
        This property must be provided by subclasses. It must return the
        :class:`ModelTreeNode` instance of the object.

        Write access is not required.
        """

    @property
    def parent(self):
        """
        The parent of the :attr:`_node`. This is part of the interface required
        to mimic a :class:`ModelTreeNode`.
        """
        return self._node.parent

    @property
    def _parent_index(self):
        """
        The index of the :attr:`_node` in its parent. This is part of the
        interface required to mimic a :class:`ModelTreeNode` and should be
        considered an implementation detail.
        """
        return self._node._parent_index

    @_parent_index.setter
    def _parent_index(self, value):
        self._node._parent_index = value

    def _set_parent(self, new_parent, new_index):
        """
        This method is required to mimic a :class:`ModelTreeNode` and must not
        be called directly by user code or overriden in subclasses.

        Its arguments and behaviour are an implementation detail.
        """
        self._node._set_parent(new_parent, new_index)


class ModelTree:
    begin_insert_rows = aioxmpp.callbacks.Signal()
    end_insert_rows = aioxmpp.callbacks.Signal()
    begin_remove_rows = aioxmpp.callbacks.Signal()
    end_remove_rows = aioxmpp.callbacks.Signal()
    begin_move_rows = aioxmpp.callbacks.Signal()
    end_move_rows = aioxmpp.callbacks.Signal()
    data_changed = aioxmpp.callbacks.Signal()

    def __init__(self):
        super().__init__()
        self.root = self._make_root(self)

    @classmethod
    def _make_root(cls, instance):
        return ModelTreeNode(instance)

    def _node_begin_insert_rows(self, node, index1, index2):
        self.begin_insert_rows(
            node,
            index1,
            index2
        )

    def _node_begin_move_rows(self, index1, index2, indexdest):
        pass

    def _node_begin_remove_rows(self, node, index1, index2):
        self.begin_remove_rows(
            node,
            index1,
            index2
        )

    def _node_end_insert_rows(self, node):
        self.end_insert_rows()

    def _node_end_move_rows(self, node):
        pass

    def _node_end_remove_rows(self, node):
        self.end_remove_rows()

    def _node_data_changed(self, node,
                           index1, index2,
                           column1, column2,
                           roles):
        self.data_changed(
            node,
            (index1, column1),
            (index2, column2),
            roles
        )
