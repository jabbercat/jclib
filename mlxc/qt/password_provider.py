from . import Qt
from .ui import Ui_dlg_password_prompt

class DlgPasswordPrompt(Qt.QDialog, Ui_dlg_add_contact):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setupUi(self)

    def accept(self):
        if not self.password.text():
            Qt.QMessageBox(
                Qt.QMessageBox.Warning,
                "Invalid input",
                "Password must not be empty.",
                parent=self)
            return
        return super().accept()
