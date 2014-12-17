import asyncio

from . import Qt
from .ui import Ui_dlg_password_prompt

class DlgPasswordPrompt(Qt.QDialog, Ui_dlg_password_prompt):
    def __init__(self, jid, password=None, saved=False, parent=None):
        super().__init__(parent)
        self.setupUi(self)
        self.label.setText(self.label.text().format(jid=jid))
        self.password.setText(password or "")
        self.save_password.setChecked(saved)

    @asyncio.coroutine
    def run_async(self):
        fut = asyncio.Future()
        slot = fut.set_result
        self.finished.connect(slot)
        self.show()
        result = yield from fut
        self.finished.disconnect(slot)
        if not result:
            return None, False, False

        return self.password.text(), True, self.save_password.checkState() == Qt.Qt.Checked
