import asyncio

import asyncio_xmpp.jid

from . import Qt
from .main import run_async_user_task

from .ui import roster

from . import add_contact, account_manager, presence_state_list_model, utils

import mlxc.account

class Roster(Qt.QMainWindow, roster.Ui_roster_window):
    def __init__(self, client):
        self.tray_icon = None
        super().__init__()
        self.setupUi(self)

        # bind to signals

        self.action_add_contact.triggered.connect(
            self._on_add_contact)
        self.action_quit.triggered.connect(
            self._on_quit)
        self.action_account_manager.triggered.connect(
            self._on_account_manager)

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

        self.account_manager_dlg.accounts.new_account(
            "test@sotecware.net/mlxc",
            "Test account")

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

    def _on_presence_state_changed(self, index):
        if not self.client.accounts:
            return
        presence = self.presence_state_selector.model().states[index]
        utils.block_widget_for_coro(
            self.presence_state_selector,
            self.client.set_global_presence(*presence[:2])
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
