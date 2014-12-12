import asyncio

import PyQt4.Qt as Qt

from .ui import roster

from . import add_contact

class Roster(Qt.QMainWindow, roster.Ui_roster_window):
    def __init__(self):
        self.tray_icon = None
        super().__init__()
        self.setupUi(self)

        # bind to signals

        self.action_add_contact.triggered.connect(
            self._on_add_contact)
        self.action_quit.triggered.connect(
            self._on_quit)

        # set up tray icon
        if Qt.QSystemTrayIcon.isSystemTrayAvailable():
            self.tray_icon = Qt.QSystemTrayIcon()
            self.tray_icon.setIcon(Qt.QIcon.fromTheme("edit-copy"))
            self.tray_icon.setVisible(True)
            self.tray_icon.activated.connect(self._on_tray_icon_activated)
        else:
            self.tray_icon = None

    def _on_add_contact(self, checked):
        @asyncio.coroutine
        def test():
            print((yield from add_contact.add_contact(self)))

        asyncio.async(test())

    def _on_tray_icon_activated(self, reason):
        if reason == Qt.QSystemTrayIcon.Trigger:
            self.show()

    def _on_quit(self):
        # FIXME: clean shutdown here
        asyncio.get_event_loop().stop()

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
