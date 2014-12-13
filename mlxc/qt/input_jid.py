import asyncio_xmpp.jid

from . import Qt
from .ui import Ui_dlg_input_jid
from . import validators

class InputJIDDialog(Qt.QDialog, Ui_dlg_input_jid):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setupUi(self)
        self.validator = validators.JIDValidator()
        self.jidedit.setValidator(self.validator)

    def accept(self):
        if     (self.validator.validate(self.jidedit.text(), 0)[0] !=
                self.validator.Acceptable):
            Qt.QMessageBox(
                Qt.QMessageBox.Warning,
                "Invalid input",
                "{!r} is not a valid Jabber ID".format(self.jidedit.text()),
                parent=self).exec()
            return

        return super().accept()

    def exec(self, label=None, title=None):
        if label is not None:
            self.label.show()
            self.label.setText(label)
        else:
            self.label.hide()
        self.setWindowTitle(title or "")
        if super().exec():
            return asyncio_xmpp.jid.JID.fromstr(self.jidedit.text())
        return None
