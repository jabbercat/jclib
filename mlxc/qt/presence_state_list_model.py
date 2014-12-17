import collections

import asyncio_xmpp.presence

from . import Qt

PresenceState = collections.namedtuple(
    "PresenceState",
    [
        "presence",
        "display_name"
    ]
)

class PresenceStateListModel(Qt.QAbstractListModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.states = [
            PresenceState(asyncio_xmpp.presence.PresenceState(True),
                          "Available"),
            PresenceState(asyncio_xmpp.presence.PresenceState(False),
                          "Offline")
        ]

    def rowCount(self, parent):
        if parent.isValid():
            return 0
        return len(self.states)

    def data(self, index, role):
        try:
            item = self.states[index.row()]
        except IndexError:
            return None

        if role == Qt.Qt.DisplayRole:
            return item[1]
        return None

    def flags(self, index):
        return Qt.Qt.ItemIsEnabled | Qt.Qt.ItemIsSelectable


model = PresenceStateListModel()
