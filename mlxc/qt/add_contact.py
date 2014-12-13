import asyncio

from . import Qt
from .ui import dlg_add_contact
from . import validators

class DlgAddContact(Qt.QDialog, dlg_add_contact.Ui_dlg_add_contact):
    def __init__(self, parent, accounts):
        super().__init__(parent)
        self.setupUi(self)
        self.contact_jid.setValidator(validators.JIDValidator())
        self.local_account.setModel(accounts)

    def accept(self):
        if self.contact_jid.validator().validate(self.contact_jid.text(), 0)[0] != 2:
            return
        return super().accept()

@asyncio.coroutine
def add_contact(parent, accounts):
    fut = asyncio.Future()
    def finished(arg):
        fut.set_result(arg)

    dlg = DlgAddContact(parent, accounts)
    dlg.finished.connect(finished)
    dlg.show()
    return (yield from fut)
