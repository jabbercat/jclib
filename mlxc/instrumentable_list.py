import collections.abc
import contextlib

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
    models.

    It provides the following callbacks which notify the user about list
    mutation. Note that all these are simple attributes which default to
    :data:`None` and to which a user can assign callables; these are no
    signals.

    .. method:: begin_insert_rows(_, index1, index2)

       This attribute is called before rows are inserted at `index1` up to
       (including) `index2`. The existing rows are not removed. The number of
       rows inserted is `index2-index1+1`.

       The first argument is always :data:`None`. This is for consistency with
       future tree-like models, which will use that argument to pass
       information about the parent item in which the change occurs. This is
       analogous (but not directly compatible) to the :meth:`beginInsertRows`
       method of :class:`QAbstractItemModel`.

    .. method:: end_insert_rows()

       This attribute is called after rows have been inserted.

    .. method:: begin_remove_rows(_, index1, index2)

       This attribute is called before rows are removed from `index1` up to (and
       including) `index2`.

       The same note as for :meth:`begin_insert_rows` holds for the first
       argument.

    .. method:: end_remove_rows()

       This attribute is called after rows have been removed.

    .. method:: begin_move_rows(_, srcindex1, srcindex2, _, destindex)

       This attribute is called before rows are moved from `srcindex1` to
       `destindex`. The rows which are being moved are those addressed by the
       indices from `srcindex1` up to (and including) `srcindex2`.

       Note that the rows are inserted such that they always appear in front of
       the item which is addressed by `destindex` *before* the rows are removed
       for moving.

       The same note as for :meth:`begin_insert_rows` holds for the first
       and fourth argument.

    .. attribute:: end_move_rows()

       This attribute is called after rows have been moved.

    The above attributes are called whenever neccessary by the mutable sequence
    implementation. The usual methods and operators of mutable sequences are
    available. For some methods special rules hold and others have been addded:

    .. automethod:: move

    .. automethod:: reverse

    """

    begin_insert_rows = None
    end_insert_rows = None
    begin_remove_rows = None
    end_remove_rows = None
    begin_move_rows = None
    end_move_rows = None

    def __init__(self, initial=()):
        super().__init__()
        self._storage = list(initial)

    def _check_and_normalize_index(self, index):
        if abs(index) > len(self._storage) or index == len(self._storage):
            raise IndexError("list index out of bounds")
        if index < 0:
            return index % len(self._storage)
        return index

    def _begin_insert_rows(self, parent, index1, index2):
        if self.begin_insert_rows is not None:
            self.begin_insert_rows(parent, index1, index2)

    def _end_insert_rows(self):
        if self.end_insert_rows is not None:
            self.end_insert_rows()

    def _begin_remove_rows(self, parent, index1, index2):
        if self.begin_remove_rows is not None:
            self.begin_remove_rows(parent, index1, index2)

    def _end_remove_rows(self):
        if self.end_remove_rows is not None:
            self.end_remove_rows()

    def _begin_move_rows(self,
                         srcparent, index1, index2,
                         destparent, destindex):
        if self.begin_move_rows is not None:
            self.begin_move_rows(srcparent, index1, index2,
                                 destparent, destindex)

    def _end_move_rows(self):
        if self.end_move_rows is not None:
            self.end_move_rows()

    def __len__(self):
        return len(self._storage)

    def __getitem__(self, index):
        return self._storage[index]

    def __delitem__(self, index):
        if isinstance(index, slice):
            start, end, stride = index.indices(len(self._storage))
            if stride == 1:
                self._begin_remove_rows(None, start, end-1)
                del self._storage[index]
                self._end_remove_rows()
            elif stride == -1:
                self._begin_remove_rows(None, end+1, start)
                del self._storage[index]
                self._end_remove_rows()
            else:
                # we have to resolve non-unity strides one by one due to hook
                # constraints
                ndeleted = 0
                for i in range(start, end, stride):
                    del self[i-ndeleted]
                    ndeleted += 1
            return

        index = self._check_and_normalize_index(index)

        self._begin_remove_rows(None, index, index)
        del self._storage[index]
        self._end_remove_rows()

    def __setitem__(self, index, item):
        if isinstance(index, slice):
            items = list(item)
            start, end, stride = index.indices(len(self._storage))
            if stride == 1:
                self._begin_remove_rows(None, start, end-1)
                del self._storage[index]
                self._end_remove_rows()
                self._begin_insert_rows(None, start, len(items)+start-1)
                self._storage[start:start] = items
                self._end_insert_rows()
            elif stride == -1:
                self._begin_remove_rows(None, end+1, start)
                del self._storage[index]
                self._end_remove_rows()
                self._begin_insert_rows(None, end+1, len(items)+end)
                self._storage[end+1:end+1] = items
                self._end_insert_rows()
            else:
                raise IndexError("non-unity strides not supported")
            return

        index = self._check_and_normalize_index(index)
        self._begin_remove_rows(None, index, index)
        del self._storage[index]
        self._end_remove_rows()
        self._begin_insert_rows(None, index, index)
        self._storage.insert(index, item)
        self._end_insert_rows()

    def insert(self, index, item):
        if index > len(self._storage):
            index = len(self._storage)
        elif index < 0:
            if index < -len(self._storage):
                index = 0
            else:
                index = index % len(self._storage)

        self._begin_insert_rows(None, index, index)
        self._storage.insert(index, item)
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

        if index1 == index2 or index1 == index2-1:
            return

        self._begin_move_rows(None, index1, index1, None, index2)
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
        for i in range(len(self._storage)//2):
            self.move(i, upper)
            if upper-2 > i:
                self.move(upper-2, i)
            upper -= 1

    def pop(self, index):
        index = self._check_and_normalize_index(index)
        self._begin_remove_rows(None, index, index)
        result = self._storage.pop(index)
        self._end_remove_rows()
        return result
