import asyncio
import functools
import logging

import asyncio_xmpp.jid

from . import Qt
from .main import run_async_user_task

from .ui import Ui_roster_window, Ui_roster_msg_box, Ui_roster_msg_box_stack

from . import add_contact, account_manager, presence_state_list_model, utils

import mlxc.account
import mlxc.client
import mlxc.roster_model

logger = logging.getLogger(__name__)

class RosterModel(Qt.QAbstractItemModel):
    DRAG_MIME_TYPE = "application/x-mlxcsigneddragkey"

    def __init__(self, root):
        super().__init__()
        self._root = root

    def _get_entry(self, index):
        if index.isValid():
            return index.internalPointer()
        return self._root

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
        return self.index_for_node(entry.parent)

    def index_for_node(self, node, column=0):
        if node.parent is None:
            return Qt.QModelIndex()
        row = node.parent.index(node)
        return self.createIndex(row, column, node)

    def hasChildren(self, index):
        node = self._get_entry(index)
        if isinstance(node, QtRosterContact):
            return node._expanded
        return hasattr(node, "__iter__")

    def flags(self, index):
        flags = (Qt.Qt.ItemIsSelectable | Qt.Qt.ItemIsEnabled
                 | Qt.Qt.ItemIsDragEnabled)
        entry = self._get_entry(index)
        if hasattr(entry, "__iter__"):
            flags |= Qt.Qt.ItemIsDropEnabled
        return flags

    def columnCount(self, *args):
        return 1

    def rowCount(self, index):
        node = self._get_entry(index)
        if isinstance(node, QtRosterContact) and not node._expanded:
            return 0
        return len(node)

    def data(self, index, role):
        entry = self._get_entry(index)
        if entry is None:
            return

        if role == Qt.Qt.DisplayRole:
            return entry.label
        elif role == Qt.Qt.ToolTipRole:
            if isinstance(entry, QtRosterVia):
                return "{}\non account {}".format(
                    entry.peer_jid,
                    entry.account_jid)
            elif isinstance(entry, QtRosterContact):
                return "\n".join(str(child.peer_jid) for
                                 child in entry)

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

class QtRosterNode(mlxc.roster_model.RosterNode):
    def __init__(self, *, parent=None):
        super().__init__(parent=parent)
        if parent is None:
            self.model = RosterModel(self)
        else:
            self.model = parent.model

class QtRosterVia(mlxc.roster_model.RosterVia, QtRosterNode):
    pass

class QtRosterContact(mlxc.roster_model.RosterContact, QtRosterNode):
    def _via(self, **kwargs):
        return QtRosterVia(parent=self, **kwargs)

    def _via_from_etree(self, el):
        return QtRosterVia.from_etree(el, parent=self)

    def _new_via(self, *args, **kwargs):
        logger.debug("_new_via(args=%r, kwargs=%r)", args, kwargs)
        if self._expanded:
            self.model.beginInsertRows(
                self.model.index_for_node(self),
                len(self),
                len(self))
        result = super()._new_via(*args, **kwargs)
        if self._expanded:
            self.model.endInsertRows()
        return result

    def __init__(self, label, **kwargs):
        super().__init__(label, **kwargs)
        self._expanded = False

    def enable_expansion(self):
        if self._expanded:
            return
        self.model.beginInsertRows(
            self.model.index_for_node(self),
            0,
            len(self)-1)
        self._expanded = True
        self.model.endInsertRows()

    def disable_expansion(self):
        if not self._expanded:
            return
        self.model.beginRemoveRows(
            self.model.index_for_node(self),
            0,
            len(self)-1)
        self._expanded = False
        self.model.endRemoveRows()

class QtRosterGroup(mlxc.roster_model.RosterGroup, QtRosterNode):
    def _group(self, **kwargs):
        return QtRosterGroup(parent=self, **kwargs)

    def _group_from_etree(self, el):
        return QtRosterGroup.from_etree(el, parent=self)

    def _contact(self, **kwargs):
        return QtRosterContact(parent=self, **kwargs)

    def _contact_from_etree(self, el):
        return QtRosterContact.from_etree(el, parent=self)

    def _new_metacontact(self, *args, **kwargs):
        logger.debug("_new_metacontact(args=%r, kwargs=%r)", args, kwargs)
        self.model.beginInsertRows(
            self.model.index_for_node(self),
            len(self),
            len(self))
        result = super()._new_metacontact(*args, **kwargs)
        self.model.endInsertRows()
        return result

    def _new_group(self, label):
        self.model.beginInsertRows(
            self.model.index_for_node(self),
            len(self),
            len(self))
        result = super()._new_group(label)
        self.model.endInsertRows()
        return result

    def __repr__(self):
        return "<{} label={!r}>".format(
            type(self).__name__,
            self.label)

# class RosterTreeView(Qt.QTreeView):
#     def dragMoveEvent(self, event):
#         super().dragMoveEvent(event)
#         item = self.model()._get_entry(self.indexAt(event.pos()))
#         droppos = self.dropIndicatorPosition()
#         if droppos != self.OnItem:
#             destination = item.parent
#         else:
#             destination = item

        # mimedata = event.mimeData()
        # print(" ".join(mimedata.formats()))

class RosterMsgBox(Qt.QWidget, Ui_roster_msg_box):
    done = Qt.pyqtSignal()

    def __init__(self, text,
                 account_jid=None,
                 reconnect_callback=None,
                 parent=None):
        super().__init__(parent)
        self.setupUi(self)
        self.message.setText(text)

        self.account_jid = account_jid

        any_button_visible = False
        if account_jid is not None:
            any_button_visible = True
            self.btn_modify.setVisible(True)
            self.btn_modify.clicked.connect(self.done)
            self.btn_modify.clicked.connect(self._modify_triggered)
        else:
            self.btn_modify.setVisible(False)

        if reconnect_callback is not None:
            any_button_visible = True
            self.btn_retry.setVisible(True)
            self.btn_retry.clicked.connect(self.done)
            self.btn_retry.clicked.connect(reconnect_callback)
        else:
            self.btn_retry.setVisible(False)

        if not any_button_visible:
            self.btnbox.setVisible(False)

    def _modify_triggered(self):
        print("foo")

class RosterMsgBoxStack(Qt.QWidget, Ui_roster_msg_box_stack):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setupUi(self)

        self._messages = []
        self._current = None

        self.btn_dismiss.clicked.connect(self._dismiss)

    def _dismiss(self, *args):
        if self._current is None:
            self._update_view()
            return
        return self._dismiss_message(self._current)

    def _dismiss_message(self, msg):
        for i, (_, widget) in enumerate(self._messages):
            if widget is msg:
                break
        else:
            logger.warning("invalid message: %r", msg)
            return

        del self._messages[i]
        if msg is self._current:
            self.frame.layout().removeWidget(self._current)
        self._update_view()

    def add_message(self, title, *args, **kwargs):
        msg = RosterMsgBox(*args, parent=self, **kwargs)
        msg.setVisible(False)
        msg.done.connect(functools.partial(self._dismiss_message, msg))
        self._messages.append((title, msg))
        if len(self._messages) == 1:
            self._update_view()

    def clear_account_messages(self, account_jid):
        for _, msg in list(self._messages):
            if msg.account_jid == account_jid:
                self._dismiss_message(account_jid)

    def _update_view(self):
        if not self._messages:
            self.setVisible(False)
            return
        self.setVisible(True)
        title, widget = self._messages[0]
        self.message_title.setText(title)
        if self._current:
            self.frame.layout().removeWidget(self._current)
        self.frame.layout().insertWidget(1, widget)
        self._current = widget
        self._current.setVisible(True)
        self.message_counter.setText("({}/{})".format(
            1, len(self._messages)))


class QtClient(mlxc.client.Client):
    @classmethod
    def account_manager_factory(cls):
        from .account_manager import QtAccountManager
        return QtAccountManager()

    @classmethod
    def roster_group_factory(cls, label):
        from .roster import QtRosterGroup
        return QtRosterGroup(label)

    def __init__(self, roster_dlg):
        super().__init__()
        self._roster_dlg = roster_dlg

    def _setup_account_state(self, jid):
        state = super()._setup_account_state(jid)
        state.on_error = self._on_account_error
        return state

    def _on_account_error(self, jid, exc, title, text):
        self._roster_dlg.roster_msg_box_stack.add_message(
            str(jid),
            "{}: {}".format(title, text),
            account_jid=jid)


class Roster(Qt.QMainWindow, Ui_roster_window):
    def __init__(self):
        self.tray_icon = None
        super().__init__()

        client = QtClient(self)

        # XXX: This should be fixed.
        # import PyQt5.QtWidgets
        # PyQt5.QtWidgets.QTreeView = RosterTreeView
        self.setupUi(self)
        # PyQt5.QtWidgets.QTreeView = Qt.QTreeView

        # bind to signals

        self.action_add_contact.triggered.connect(
            self._on_add_contact)
        self.action_quit.triggered.connect(
            self._on_quit)
        self.action_account_manager.triggered.connect(
            self._on_account_manager)

        self.roster_msg_box_stack = RosterMsgBoxStack(parent=self)
        self.verticalLayout.layout().insertWidget(
            1,
            self.roster_msg_box_stack)

        # set up tray icon
        if Qt.QSystemTrayIcon.isSystemTrayAvailable():
            self.tray_icon = Qt.QSystemTrayIcon()
            self.tray_icon.setIcon(Qt.QIcon.fromTheme("edit-copy"))
            self.tray_icon.setVisible(True)
            self.tray_icon.activated.connect(self._on_tray_icon_activated)
        else:
            self.tray_icon = None

        self.client = client
        self.account_manager_dlg = account_manager.DlgAccountManager(
            self.client.accounts)

        self.roster_view.setModel(self.client.roster_root.model)

        # info, jid = self.client.accounts.new_account(
        #     "j.wielicki@sotecware.net/mlxc",
        #     "Test account")
        info, jid = self.client.accounts.new_account(
            "foo@bar.invalid",
            "Test account")
        self.client.accounts.set_account_enabled(jid, True)

        self.presence_state_selector.setModel(
            presence_state_list_model.model)
        self.presence_state_selector.currentIndexChanged.connect(
            self._on_presence_state_changed)
        self.presence_state_selector.setCurrentIndex(1)

    def _on_add_contact(self, checked):
        @asyncio.coroutine
        def test():
            print((yield from add_contact.add_contact(
                self,
                self.account_manager_dlg.accounts.model)))

        run_async_user_task(test())

    def _on_account_manager(self):
        self.account_manager_dlg.show()

    def _on_tray_icon_activated(self, reason):
        if reason == Qt.QSystemTrayIcon.Trigger:
            self.show()

    def _on_quit(self):
        # FIXME: clean shutdown here
        asyncio.get_event_loop().stop()

    @utils.asyncify
    @asyncio.coroutine
    def _on_presence_state_changed(self, index):
        if not self.client.accounts:
            return
        presence = self.presence_state_selector.model().states[index]
        print("setting presence", presence[0])
        yield from utils.block_widget_for_coro(
            self.presence_state_selector,
            self.client.set_global_presence(presence[0])
        )

    def event(self, *args):
        # print(args)
        return super().event(*args)

    def changeEvent(self, event):
        # minimize to tray if possible
        if self.tray_icon and event.type() == Qt.QEvent.WindowStateChange:
            if self.windowState() & Qt.Qt.WindowMinimized:
                self.hide()
                self.setWindowState(self.windowState() ^ Qt.Qt.WindowMinimized)
                return
        return super().changeEvent(event)

    def closeEvent(self, event):
        # minimize to tray if possible
        if self.tray_icon:
            self.hide()
            event.ignore()
            return
        return super().closeEvent(event)
