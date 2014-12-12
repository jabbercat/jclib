import asyncio

import asyncio_xmpp.jid

import PyQt4.Qt as Qt

from .ui import dlg_add_contact

class JIDValidator(Qt.QValidator):
    def validate(self, *args):
        s, _ = args
        try:
            jid = asyncio_xmpp.jid.JID.fromstr(s)
        except ValueError:
            return (Qt.QValidator.Intermediate, )+args
        else:
            if not jid.localpart or jid.resource:
                return (Qt.QValidator.Intermediate, )+args  # intermediate
        return (Qt.QValidator.Acceptable, )+args  # valid

class DlgAddContact(Qt.QDialog, dlg_add_contact.Ui_dlg_add_contact):
    def __init__(self, parent):
        super().__init__(parent)
        self.setupUi(self)
        test = Qt.QIntValidator(1, 1000)
        print(test.validate("foo", 1))
        self.contact_jid.setValidator(JIDValidator())

    def accept(self):
        if self.contact_jid.validator().validate(self.contact_jid.text(), 0)[0] != 2:
            return
        return super().accept()

@asyncio.coroutine
def add_contact(parent):
    fut = asyncio.Future()
    def finished(arg):
        fut.set_result(arg)

    dlg = DlgAddContact(parent)
    dlg.finished.connect(finished)
    dlg.show()
    return (yield from fut)
