import mlxc.instrumentable_list


class Node:
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._parent = None

    @property
    def parent(self):
        return self._parent

    def _add_to_parent(self, new_parent):
        if self._parent is not None:
            raise RuntimeError("parent already set")
        self._parent = new_parent

    def _remove_from_parent(self):
        if self._parent is None:
            raise RuntimeError("parent is not set")
        self._parent = None


class Container(mlxc.instrumentable_list.ModelList):
    def __init__(self, *args, **kwargs):
        self.on_register_item.connect(self._set_item_parent)
        self.on_unregister_item.connect(self._unset_item_parent)
        super().__init__(*args, **kwargs)

    def _set_item_parent(self, item):
        item._add_to_parent(self)

    def _unset_item_parent(self, item):
        item._remove_from_parent()

    def _begin_insert_rows(self, start, end):
        if self.begin_insert_rows is not None:
            self.begin_insert_rows(self, start, end)

    def _begin_move_rows(self, srcindex1, srcindex2, destindex):
        if self.begin_move_rows is not None:
            self.begin_move_rows(self, srcindex1, srcindex2, self, destindex)

    def _begin_remove_rows(self, start, end):
        if self.begin_remove_rows is not None:
            self.begin_remove_rows(self, start, end)

    def inject(self, index, iterable):
        items = list(iterable)
        self._register_items(items)
        self._storage[index:index] = items

    def eject(self, start, end):
        result = self._storage[start:end]
        self._unregister_items(result)
        del self._storage[start:end]
        return result


class Tree:
    def __init__(self):
        super().__init__()
        self._root = Container()

    @property
    def root(self):
        return self._root


class Walker:
    def visit(self, node):
        try:
            visitor = getattr(self, "visit_"+type(node).__name__)
        except AttributeError:
            visitor = self.generic_visit
        visitor(node)

    def generic_visit(self, node):
        if isinstance(node, Container):
            for item in node:
                self.visit(item)
