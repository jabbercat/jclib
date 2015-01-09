import asyncio
import functools
import logging

import asyncio_xmpp.jid

from . import Qt

from .ui import Ui_roster_window, Ui_roster_msg_box, Ui_roster_msg_box_stack

from . import add_contact, account_manager, presence_state_list_model, utils

from mlxc.utils import *

import mlxc.account
import mlxc.client
import mlxc.roster_model

logger = logging.getLogger(__name__)

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
                 modify_callback=None,
                 reconnect_callback=None,
                 parent=None):
        super().__init__(parent)
        self.setupUi(self)
        self.message.setText(text)

        self.account_jid = account_jid

        any_button_visible = False
        if modify_callback is not None:
            any_button_visible = True
            self.btn_modify.setVisible(True)
            self.btn_modify.clicked.connect(self.done)
            self.btn_modify.clicked.connect(modify_callback)
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

class RosterMsgBoxStack(Qt.QWidget, Ui_roster_msg_box_stack):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setupUi(self)

        self._messages = []
        self._current = None

        self.btn_dismiss.clicked.connect(self._dismiss)
        self._update_view()

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
            if hasattr(msg, "account_jid") and msg.account_jid == account_jid:
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
    def roster_factory(cls):
        from .roster_model import QtRoster
        return QtRoster()

    def __init__(self):
        super().__init__()
        self.on_account_error = None

    def _setup_account_state(self, jid):
        state = super()._setup_account_state(jid)
        state.on_error = self._handle_account_error
        return state

    def _handle_account_error(self, jid, exc, title, text):
        if self.on_account_error:
            self.on_account_error(jid, exc, title, text)


class SortFilterRosterModel(Qt.QSortFilterProxyModel):
    def __init__(self, backing_model, parent=None):
        super().__init__(parent=parent)
        self.setSourceModel(backing_model)
        self.setDynamicSortFilter(True)

        self._show_offline_contacts = True

    @property
    def show_offline_contacts(self):
        return self._show_offline_contacts

    @show_offline_contacts.setter
    def show_offline_contacts(self, value):
        if self._show_offline_contacts == value:
            return
        self._show_offline_contacts = value
        self.invalidateFilter()

    def filterAcceptsRow(self, source_row, source_parent):
        if self._show_offline_contacts and self._show_empty_groups:
            return

        model = self.sourceModel()
        parent = model.get_entry(source_parent)
        item = parent[source_row]
        if not self._show_offline_contacts:
            if hasattr(item, "presence"):
                if not item.presence:
                    return False

        return True


class Roster(Qt.QMainWindow, Ui_roster_window):
    def __init__(self, client):
        self.tray_icon = None
        super().__init__()

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
        self.client.on_account_error = self._on_account_error
        self.account_manager_dlg = account_manager.DlgAccountManager(
            self.client.accounts)

        self.filter_model = SortFilterRosterModel(
            self.client.roster_root.model)

        self.roster_view.setModel(self.filter_model)
        self.roster_view.setSelectionBehavior(self.roster_view.SelectRows)
        self.roster_view.header().setStretchLastSection(False)
        self.roster_view.header().setSectionResizeMode(
            0,
            self.roster_view.header().Stretch)
        self.roster_view.header().setSectionResizeMode(
            1,
            self.roster_view.header().Fixed)
        self.roster_view.setColumnWidth(
            1,
            round(1.5*self.roster_view.fontMetrics().boundingRect("M").width())
        )
        self.roster_view.setContextMenuPolicy(
            Qt.Qt.CustomContextMenu)
        self.roster_view.customContextMenuRequested.connect(
            self._on_roster_view_context_menu_request)

        self.presence_state_selector.setModel(
            presence_state_list_model.model)
        self.presence_state_selector.currentIndexChanged.connect(
            self._on_presence_state_changed)
        self.presence_state_selector.setCurrentIndex(1)

    def _on_roster_view_context_menu_request(self, pos):
        index = self.filter_model.mapToSource(
            self.roster_view.indexAt(pos))
        view = self.client.roster_root.model.get_entry_view(index)
        if view is None:
            return

        global_pos = self.roster_view.mapToGlobal(pos)
        view.context_menu(self, global_pos)

    @utils.asyncify
    @asyncio.coroutine
    def _modify_account(self, account_jid, *args):
        self.account_manager_dlg.show()
        yield from self.account_manager_dlg.modify_jid(account_jid)

    def _on_account_error(self, jid, exc, title, text):
        self.roster_msg_box_stack.add_message(
            str(jid),
            "{}: {}".format(title, text),
            account_jid=jid,
            modify_callback=functools.partial(self._modify_account, jid)
        )

    def _on_add_contact(self, checked):
        @asyncio.coroutine
        def test():
            print((yield from add_contact.add_contact(
                self,
                self.account_manager_dlg.accounts.model)))

        logged_async(test())

    def _on_account_manager(self):
        self.account_manager_dlg.show()

    def _on_tray_icon_activated(self, reason):
        if reason == Qt.QSystemTrayIcon.Trigger:
            self.show()

    def _on_quit(self):
        from . import main
        main.MLXCQt.get_instance().quit()

    @utils.asyncify
    @asyncio.coroutine
    def _on_presence_state_changed(self, index):
        if not self.client.accounts:
            return
        presence = self.presence_state_selector.model().states[index]
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
