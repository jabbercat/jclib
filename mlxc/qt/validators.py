import asyncio_xmpp.jid

from . import Qt

class JIDValidator(Qt.QValidator):
    def __init__(self, allow_full_jid=True, require_localpart=True):
        super().__init__()
        self.allow_full_jid = allow_full_jid
        self.require_localpart = require_localpart

    def validate(self, *args):
        s, _ = args
        try:
            jid = asyncio_xmpp.jid.JID.fromstr(s)
        except ValueError:
            return (Qt.QValidator.Intermediate, )+args
        else:
            if not self.allow_full_jid and jid.resource:
                return (Qt.QValidator.Intermediate, )+args
            if self.require_localpart and not jid.localpart:
                return (Qt.QValidator.Intermediate, )+args
        return (Qt.QValidator.Acceptable, )+args  # valid
