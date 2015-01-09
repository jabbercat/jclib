import logging

logger = logging.getLogger(__name__)

import mlxc.roster_model

from . import Qt, utils

import mlxc.utils

class RosterModel(Qt.QAbstractItemModel):
    DRAG_MIME_TYPE = "application/x-mlxcsigneddragkey"

    def __init__(self, root):
        super().__init__()
        self._root = root

    def get_entry(self, index):
        if index.isValid():
            return index.internalPointer()
        return self._root

    def get_entry_view(self, index):
        entry = self.get_entry(index)
        if entry is None:
            return None
        return entry.view

    def index(self, row, column, parent):
        parent = self.get_entry(parent)
        if not (0 <= row < len(parent)):
            return Qt.QModelIndex()

        index = self.createIndex(row, column, parent[row])
        return index

    def parent(self, index):
        entry = self.get_entry(index)
        if entry is None:
            return Qt.QModelIndex()
        return self.index_for_node(entry.get_parent())

    def index_for_node(self, node, column=0):
        if node is None:
            return Qt.QModelIndex()
        parent = node.get_parent()
        if parent is None:
            return Qt.QModelIndex()
        row = parent.index(node)
        return self.createIndex(row, column, node)

    def hasChildren(self, index):
        return self.get_entry_view(index).has_children()

    def flags(self, index):
        return self.get_entry_view(index).flags()

    def columnCount(self, *args):
        return 2

    def rowCount(self, index):
        return self.get_entry_view(index).row_count()

    def data(self, index, role):
        view = self.get_entry_view(index)
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

        # we have to deduplicate, as columns may be involved :)
        objects = list(set(filter(None, map(self.get_entry, indexes))))

        data = Qt.QMimeData()
        data.setData(self.DRAG_MIME_TYPE, utils.start_drag(objects))
        return data

    def canDropMimeData(self, data, action, row, column, parent):
        print("can drop mime data? FIXME this is short-circuited!")
        return True

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
        new_parent = self.get_entry(parent)
        old_parent = node.get_parent()

        if old_parent is None:
            print("old parent is None")
            return False

        if not isinstance(new_parent, mlxc.roster_model.RosterContainer):
            print("new parent is not a container")
            # not a container, we cannot do anything sensible
            return False

        if not node.can_move_to_parent(new_parent):
            print("move is predicted to fail")
            return False

        i = old_parent.index(node)
        del old_parent[i]
        try:
            new_parent.append(node)
        except:
            old_parent.insert(i, node)
            logger.exception("failed to drop node: ")
            return False
        else:
            node.get_root().dispatch_event(
                mlxc.roster_model.GenericRosterEvent(
                    mlxc.roster_model.GenericRosterEventType)
            )
            return True

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

    def context_menu(self, roster_dlg, pos):
        pass

class QtRosterContainerView(QtRosterNodeView,
                            mlxc.roster_model.RosterContainerView):
    def flags(self):
        return super().flags() | Qt.Qt.ItemIsDropEnabled

    def has_children(self):
        return bool(len(self._obj))

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
                                   sl.stop)

    def post_remove(self, sl, objs):
        self.model.endRemoveRows()

class QtRosterContactView(QtRosterContainerView):
    def __init__(self, for_object):
        super().__init__(for_object)
        self._expandable = False

    @property
    def expandable(self):
        return self._expandable

    @expandable.setter
    def expandable(self, value):
        if value == self._expandable:
            return
        self._expandable = value
        if len(self._obj):
            if value:
                # fake re-insertion of children
                self.model.beginInsertRows(
                    self.get_my_index(),
                    0, len(self._obj)-1)
                self.model.endInsertRows()
            else:
                self.model.beginRemoveRows(
                    self.get_my_index(),
                    0, len(self._obj)-1)
                self.model.endRemoveRows()

    def data(self, role, column=0):
        if column == 1:
            if role == Qt.Qt.DisplayRole:
                available = self._obj.presence.available
                if available:
                    return "A"
                return "N"
        elif role == Qt.Qt.ToolTipRole:
            tooltip = "<hr />".join(
                child.view.data(
                    role, tooltip_account_notice=False)
                for child in self._obj)
            return tooltip
        else:
            return super().data(role, column=column)

    def has_children(self):
        return self._expandable and len(self._obj)

    def row_count(self):
        if not self._expandable:
            return 0
        return len(self._obj)

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

    def context_menu(self, roster_dlg, pos):
        menu = Qt.QMenu()
        action = menu.addAction("Expandable")
        action.setCheckable(True)
        action.setChecked(self.expandable)

        active_action = menu.exec(pos)
        self.expandable = action.isChecked()
        if active_action:
            # FIXME: this is utterly wrong...
            roster_dlg.roster_view.setExpanded(self.get_my_index(), True)


class QtRosterViaView(QtRosterNodeView):
    def prop_changed(self, prop, new_value):
        my_index = self.get_my_index()
        self.model.dataChanged.emit(
            my_index,
            my_index.sibling(my_index.row(), 1)
        )

    def data(self, role, column=0,
             tooltip_account_notice=True):
        if column == 1:
            if role == Qt.Qt.DisplayRole:
                available = self._obj.presence.available
                if available:
                    return "A"
                return "N"
        elif role == Qt.Qt.ToolTipRole:
            root = self._obj.get_root()

            title_str = "<h2>{}</h2>".format(self._obj.peer_jid)
            account_str = "<b>Account: </b>{}".format(self._obj.account_jid)

            if not self._obj.account_available:
                # no point in showing additional information here
                msg = "{}<div>{}</div>".format(
                    title_str,
                    account_str)
                if tooltip_account_notice:
                    info_str = ("<i>Note: </i>The above account is"
                                " disconnected. Full information on the contact"
                                " is not available.")
                    msg += "<div>{}</div>".format(info_str)
                return msg

            presence_str = "</div><div>".join(
                "<b>Status ({}): </b>{}".format(
                    resource, mlxc.utils.presencetostr(state))
                for resource, state in self._obj.get_all_presence().items()
            )
            if not presence_str:
                presence_str = "<b>Status: </b>Not available"
            roster_item = root.get_roster_item(self._obj.account_jid,
                                               self._obj.peer_jid)
            if not roster_item:
                subscription = "none"
            else:
                subscription = roster_item.subscription
            subscription_str = "<b>Subscription: </b>{}".format(
                subscription)

            return "{}<div>{}</div><div>{}</div></ul><div>{}</div>".format(
                title_str,
                account_str,
                presence_str,
                subscription_str)
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
