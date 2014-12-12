import asyncio

import PyQt4.Qt as Qt

from .ui import roster

from . import add_contact

class Roster(Qt.QMainWindow, roster.Ui_roster_window):
    def __init__(self):
        super().__init__()
        self.setupUi(self)
        print(dir(self.action_add_contact))
        self.action_add_contact.triggered.connect(
            self._on_add_contact)

    def _on_add_contact(self, checked):
        @asyncio.coroutine
        def test():
            print((yield from add_contact.add_contact()))

        asyncio.async(test())

    def event(self, *args):
        # print(args)
        return super().event(*args)

    def closeEvent(self, *args):
        pass
