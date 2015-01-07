import mlxc.roster_model

from . import Qt, utils

class RosterModel(Qt.QAbstractItemModel):
    DRAG_MIME_TYPE = "application/x-mlxcsigneddragkey"

    def __init__(self, root):
        super().__init__()
        self._root = root

    def _get_entry(self, index):
        if index.isValid():
            return index.internalPointer()
        return self._root

    def _get_entry_view(self, index):
        entry = self._get_entry(index)
        if entry is None:
            return None
        return entry.view

    def index(self, row, column, parent):
        parent = self._get_entry(parent)
        if not (0 <= row < len(parent)):
            return Qt.QModelIndex()

        index = self.createIndex(row, column, parent[row])
        return index

    def parent(self, index):
        entry = self._get_entry(index)
        if entry is None:
            return Qt.QModelIndex()
        return self.index_for_node(entry.get_parent())

    def index_for_node(self, node, column=0):
        parent = node.get_parent()
        if parent is None:
            return Qt.QModelIndex()
        row = parent.index(node)
        return self.createIndex(row, column, node)

    def hasChildren(self, index):
        return self._get_entry_view(index).has_children()

    def flags(self, index):
        return self._get_entry_view(index).flags()

    def columnCount(self, *args):
        return 2

    def rowCount(self, index):
        return self._get_entry_view(index).row_count()

    def data(self, index, role):
        view = self._get_entry_view(index)
        if view is None:
            return
        return view.data(role, column=index.column())

        # if role == Qt.Qt.DisplayRole:
        #     return entry.label
        # elif role == Qt.Qt.ToolTipRole:
        #     if isinstance(entry, QtRosterVia):
        #         return "{}\non account {}".format(
        #             entry.peer_jid,
        #             entry.account_jid)
        #     elif isinstance(entry, QtRosterContact):
        #         return "\n".join(str(child.peer_jid) for
        #                          child in entry)

    def mimeTypes(self):
        return [self.DRAG_MIME_TYPE]

    def mimeData(self, indexes):
        if not indexes:
            return

        objects = list(filter(None, map(self._get_entry, indexes)))

        data = Qt.QMimeData()
        data.setData(self.DRAG_MIME_TYPE, utils.start_drag(objects))
        return data

    def canDropMimeData(self, data, action, row, column, parent):
        print(data, action, row, column, parent)
        if not data.hasData(self.DRAG_MIME_TYPE):
            print("no mime")
            return False
        key = data.data(self.DRAG_MIME_TYPE)
        data = utils.get_drag(key)
        if data is None:
            print("no data")
            return False

        if action & Qt.Qt.ActionMask != Qt.Qt.MoveAction:
            print("no")
            return False
        print("yes")
        return True

    def dropMimeData(self, data, action, row, column, parent):
        print(data, action, row, column, parent)
        if not data.hasFormat(self.DRAG_MIME_TYPE):
            return False
        items = utils.pop_drag(data.data(self.DRAG_MIME_TYPE))
        if items is None:
            return False

        if action & Qt.Qt.ActionMask != Qt.Qt.MoveAction:
            return False

        if not items:
            return True
        node, = items
        parent_node = self._get_entry(parent)
        if isinstance(parent_node, QtRosterVia):
            return False

        if isinstance(node, QtRosterVia):
            if parent_node.has_via(node.account_jid, node.peer_jid):
                Qt.QMessageBox.warning(
                    None,
                    "Invalid operation",
                    "The contact is already in this group").show()
                return False
            if isinstance(parent_node, QtRosterContact):
                target_was_meta = True
                metacontact = parent_node
                parent_node = metacontact.parent
            else:
                target_was_meta = False
                metacontact = None
            raise NotImplementedError()
        raise NotImplementedError()

        return False

    def supportedDropActions(self):
        return Qt.Qt.MoveAction

    def supportedDragActions(self):
        return Qt.Qt.MoveAction

class QtRosterNodeView(mlxc.roster_model.RosterNodeView):
    @property
    def model(self):
        return self._obj.get_root().model

    def get_my_index(self):
        return self.model.index_for_node(self._obj)

    def get_parent_index(self):
        return self.model.index_for_node(self._obj.get_parent())

    def flags(self):
        return (Qt.Qt.ItemIsSelectable | Qt.Qt.ItemIsEnabled
                | Qt.Qt.ItemIsDragEnabled)

    def data(self, role, column=0):
        if column != 0:
            return

        if role == Qt.Qt.DisplayRole:
            return self._obj.label

    def has_children(self):
        return False

    def row_count(self):
        return 0

class QtRosterContainerView(QtRosterNodeView,
                            mlxc.roster_model.RosterContainerView):
    def flags(self):
        return super().flags() | Qt.Qt.ItemIsDropEnabled

    def has_children(self):
        return True

    def row_count(self):
        return len(self._obj)

    def pre_insert(self, at, objs):
        self.model.beginInsertRows(self.get_my_index(),
                                   at,
                                   at+len(objs)-1)

    def post_insert(self, at, objs):
        self.model.endInsertRows()

    def pre_remove(self, sl, objs):
        self.model.beginRemoveRows(self.get_my_index(),
                                   sl.start,
                                   sl.end)

    def post_remove(self, sl, objs):
        self.model.endRemoveRows()

class QtRosterContactView(QtRosterContainerView):
    def prop_changed(self, prop, new_value):
        my_index = self.get_my_index()
        self.model.dataChanged.emit(
            my_index,
            my_index.sibling(my_index.row(), 1)
        )

    def flags(self):
        flags = super().flags()
        if not self._obj.any_account_available:
            flags &= ~Qt.Qt.ItemIsEnabled
        return flags

class QtRosterViaView(QtRosterNodeView):
    def prop_changed(self, prop, new_value):
        my_index = self.get_my_index()
        self.model.dataChanged.emit(
            my_index,
            my_index.sibling(my_index.row(), 1)
        )

    def data(self, role, column=0):
        if column == 1:
            if role == Qt.Qt.DisplayRole:
                available = self._obj.presence.available
                if available:
                    return "A"
                return "N"
        else:
            return super().data(role, column=column)

    def flags(self):
        flags = super().flags()
        if not self._obj.account_available:
            flags &= ~Qt.Qt.ItemIsEnabled
        return flags

class QtRoster(mlxc.roster_model.Roster):
    def __init__(self):
        super().__init__()
        self.model = RosterModel(self)

    def make_view(self, for_object):
        if isinstance(for_object, mlxc.roster_model.RosterVia):
            return QtRosterViaView(for_object)
        elif isinstance(for_object, mlxc.roster_model.RosterContact):
            return QtRosterContactView(for_object)
        elif isinstance(for_object, mlxc.roster_model.RosterContainer):
            return QtRosterContainerView(for_object)
        elif isinstance(for_object, mlxc.roster_model.RosterNode):
            return QtRosterNodeView(for_object)
        else:
            raise NotImplementedError("no view for {}".format(for_object))
