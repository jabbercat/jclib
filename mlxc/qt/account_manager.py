import asyncio

import keyring

from . import Qt
from .ui import Ui_dlg_account_manager
from . import input_jid, utils

import mlxc.account

class AccountListModel(Qt.QAbstractTableModel):
    def __init__(self, manager, parent=None):
        super().__init__(parent)
        self.manager = manager

    def rowCount(self, parent):
        if parent.isValid():
            return 0
        return len(self.manager)

    def columnCount(self, parent):
        if parent.isValid():
            return 0
        return 2

    def data(self, index, role):
        if role == Qt.Qt.DisplayRole:
            try:
                info = self.manager[index.row()]
            except IndexError:
                return None
            return {
                0: info.name or str(info.jid),
                1: str(info.jid),
            }.get(index.column())
        elif role == Qt.Qt.ToolTipRole:
            try:
                return str(self.manager[index.row()].client_jid)
            except IndexError:
                return None
        else:
            return None

    def headerData(self, section, orientation, role):
        if role != Qt.Qt.DisplayRole:
            return
        return {
            0: "Account name",
            1: "JID",
        }.get(section)

    def flags(self, index):
        return Qt.Qt.ItemIsEnabled | Qt.Qt.ItemIsSelectable

class QtAccountManager(mlxc.account.AccountManager):
    def __init__(self):
        super().__init__()
        self.model = AccountListModel(self)

    def new_account(self, jid, *args):
        super().new_account(jid, *args)
        self.model.beginInsertRows(Qt.QModelIndex(), len(self), len(self))
        self.model.endInsertRows()

    def __delitem__(self, index):
        if isinstance(index, slice):
            if index.step is None or index.step == 1:
                start, stop, _ = index.indices(len(self))
                if start == stop:
                    return
                self.model.beginRemoveRows(Qt.QModelIndex(), start, stop-1)
            else:
                # non-consecutive indicies
                for index in range(index.indicies(len(self))):
                    del self[index]
        else:
            # use the slice mechanism
            del self[index:index+1]
            return
        super().__delitem__(index)
        self.model.endRemoveRows()

    def update_account(self, jid, **kwargs):
        index = self.index(jid)
        super().update_account(jid, **kwargs)
        self.model.dataChanged.emit(
            self.model.index(index, 0),
            self.model.index(index, 1)
        )

    @asyncio.coroutine
    def password_provider(self, jid, nattempt):
        if nattempt == 0:
            try:
                return (yield from super().password_provider(jid, nattempt))
            except KeyError:
                pass
        password, ok = Qt.QInputDialog.getText(
            None,
            "Password required",
            "A password is required to log into {!s}".format(jid),
            mode=Qt.QLineEdit.Password)
        if not ok:
            return None
        return password


class DlgAccountManager(Qt.QDialog, Ui_dlg_account_manager):
    def __init__(self, accounts, parent=None):
       super().__init__(parent)
       self.setupUi(self)
       self.setModal(False)
       self.accounts = accounts
       self.account_list.setModel(self.accounts.model)
       self.account_list.setSelectionBehavior(Qt.QTableView.SelectRows);
       self.account_list.setSelectionMode(Qt.QTableView.SingleSelection);
       self.account_list.doubleClicked.connect(self.modify)

       self.btn_manage_accounts.addAction(self.action_new_account)
       self.btn_manage_accounts.addAction(self.action_delete_account)

       self.acc_name.textChanged.connect(self._modified)
       self.acc_password.textChanged.connect(self._modified)
       self.acc_save_password.toggled.connect(self._modified)
       self.acc_save_password.toggled.connect(self._on_save_password_toggled)
       self.acc_buttons.clicked.connect(self._on_acc_button_clicked)
       self.acc_buttons.button(self.acc_buttons.Apply).setAutoDefault(False)
       self.acc_buttons.button(self.acc_buttons.Reset).setAutoDefault(False)

       self.action_new_account.triggered.connect(self._on_new_account)
       self.action_delete_account.triggered.connect(self._on_delete_account)

       self.acc_password_warning.setVisible(
           not self.accounts.KEYRING_IS_SAFE)

       self._current_jid = None
       self._current_account = None
       self.reset_current()

    def _modified(self, *args):
        self._modified = True

    def _on_acc_button_clicked(self, btn):
        role = self.acc_buttons.buttonRole(btn)
        if role == Qt.QDialogButtonBox.ApplyRole:
            self.save_current()
        elif role == Qt.QDialogButtonBox.ResetRole:
            self.reset_current()
        else:
            print("unhandled role: {}".format(role))

    def _on_new_account(self, *args):
        input_dlg = input_jid.InputJIDDialog(self)
        new_jid = input_dlg.exec(label="Jabber ID for the new account:",
                                 title="Create new account")
        if new_jid is not None:
            try:
                self.accounts.new_account(new_jid)
            except ValueError as err:
                Qt.QMessageBox(
                    Qt.QMessageBox.Critical,
                    "JID already in use",
                    "The JID {!r} is already in use by a different account".format(
                        str(new_jid)),
                    parent=self).show()

    def _on_delete_account(self, *args):
        pass

    def _on_save_password_toggled(self, checked):
        self.acc_password.setEnabled(checked)

    def modify(self, index):
        if index.isValid():
            new_info = self.accounts[index.row()]
        else:
            new_info = None
        if     ((new_info is not None and new_info.jid == self._current_jid) or
                (new_info is None and self._current_jid is None)):
            return

        if self._current_jid is not None and self._modified:
            result = Qt.QMessageBox(
                Qt.QMessageBox.Warning,
                "Save changes?",
                "The account {} was modified. Save changes?".format(
                    self._current_account),
                buttons=Qt.QMessageBox.Save | Qt.QMessageBox.Discard,
                parent=self).exec()
            if result == Qt.QMessageBox.Save:
                self.save_current()

        if new_info is not None:
            self._current_jid = new_info.jid
            self._current_account = new_info
        else:
            self._current_jid = None
            self._current_account = None
        self.reset_current()

    def reset_current(self):
        if self._current_account is not None:
            self.acc_name.setText(self._current_account.name or "")
            try:
                password = utils.block_widget_for_coro(
                    self,
                    self.accounts.get_stored_password(self._current_jid)
                )
                self.acc_password.setText(password or "")
                self.acc_save_password.setChecked(bool(password))
            except mlxc.account.PasswordStoreIsUnsafe:
                self.acc_save_password.setChecked(False)
                self.acc_save_password.setEnabled(False)
            self.editor_widget.setEnabled(True)
        else:
            self.acc_name.setText("")
            self.acc_password.setText("")
            self.acc_save_password.setChecked(False)
            self.editor_widget.setEnabled(False)
        self._modified = False

    def save_current(self):
        if self._current_jid is None:
            return
        self.accounts.update_account(
            self._current_jid,
            name=self.acc_name.text()
        )
        password = (self.acc_password.text() or None
                    if self.acc_save_password.checkState() == Qt.Qt.Checked
                    else None)
        try:
            utils.block_widget_for_coro(
                self,
                self.accounts.set_stored_password(
                    self._current_jid,
                    password)
            )
        except mlxc.account.PasswordStoreIsUnsafe:
            pass

        self._modified = False

    def done(self, r):
        self.modify(Qt.QModelIndex())
        return super().done(r)

    def show(self):
        super().show()
        self.raise_()
