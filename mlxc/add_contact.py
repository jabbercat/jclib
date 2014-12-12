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
            return (1, )+args  # intermediate
        return (2, )+args  # valid

class DlgAddContact(Qt.QDialog, dlg_add_contact.Ui_dlg_add_contact):
    def __init__(self):
        super().__init__()
        self.setupUi(self)
        test = Qt.QIntValidator(1, 1000)
        print(test.validate("foo", 1))
        self.contact_jid.setValidator(JIDValidator())

@asyncio.coroutine
def add_contact():
    fut = asyncio.Future()
    def finished(arg):
        fut.set_result(arg)

    dlg = DlgAddContact()
    dlg.finished.connect(finished)
    dlg.show()
    return (yield from fut)
