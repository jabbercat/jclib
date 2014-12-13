import collections

from . import Qt

PresenceState = collections.namedtuple(
    "PresenceState",
    [
        "typeattr",
        "additional_tag",
        "display_name"
    ]
)

class PresenceStateListModel(Qt.QAbstractListModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.states = [
            PresenceState(None, None, "Available"),
            PresenceState("unavailable", None, "Offline")
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
            return item[2]
        return None

    def flags(self, index):
        return Qt.Qt.ItemIsEnabled | Qt.Qt.ItemIsSelectable


model = PresenceStateListModel()
