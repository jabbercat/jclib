import typing

import aioxmpp.callbacks
import aioxmpp.xml

from aioxmpp import JID

import mlxc.config
import mlxc.instrumentable_list
import mlxc.utils
import mlxc.xso


class Account:
    def __init__(self, jid, colour):
        super().__init__()
        self._jid = jid
        self.enabled = True
        self.allow_unencrypted = False
        self.stashed_xml = []
        self.colour = colour
        self.client = None

    @property
    def jid(self):
        return self._jid

    def to_xso(self):
        result = mlxc.xso.AccountSettings(self._jid)
        result.disabled = not self.enabled
        result.allow_unencrypted = self.allow_unencrypted
        result.colour = " ".join(map(str, self.colour))
        result._[:] = self.stashed_xml
        return result

    @classmethod
    def from_xso(cls, object_):
        colour = tuple(map(int, object_.colour.split()))
        result = cls(object_.jid, colour)
        result.enabled = not object_.disabled
        result.allow_unencrypted = bool(object_.allow_unencrypted)
        result.stashed_xml = list(object_._)
        return result


class Accounts(mlxc.config.SimpleConfigurable,
               mlxc.instrumentable_list.ModelListView):
    UID = mlxc.utils.mlxc_uid
    FILENAME = "accounts.xml"

    on_account_enabled = aioxmpp.callbacks.Signal()
    on_account_disabled = aioxmpp.callbacks.Signal()

    on_account_added = aioxmpp.callbacks.Signal()
    on_account_removed = aioxmpp.callbacks.Signal()

    def __init__(self):
        super().__init__(mlxc.instrumentable_list.ModelList())
        self._jidmap = {}

    def _require_unique_jid(self, jid: JID) -> JID:
        jid = jid.bare()
        if jid in self._jidmap:
            raise ValueError("duplicate account JID")
        return jid

    def new_account(self, jid: JID,
                    colour: typing.Tuple[int, int, int]) -> Account:
        bare_jid = self._require_unique_jid(jid)
        result = Account(bare_jid, colour)
        result.resource = jid.resource
        self._backend.append(result)
        self._jidmap[bare_jid] = result
        self.on_account_added(result)
        self.on_account_enabled(result)
        return result

    def lookup_jid(self, jid: JID) -> Account:
        return self._jidmap[jid.bare()]

    def remove_account(self, account: Account):
        self.on_account_disabled(account)
        self.on_account_removed(account)
        account = self._jidmap.pop(account.jid)
        self._backend.remove(account)

    def set_account_enabled(self, account: Account, enabled: bool):
        if bool(account.enabled) == bool(enabled):
            return
        account.enabled = enabled
        if enabled:
            self.on_account_enabled(account)
        else:
            self.on_account_disabled(account)
        index = self._backend.index(account)
        self._backend.refresh_data(slice(index, index + 1), None)

    def _do_save_xso(self):
        xso = mlxc.xso.AccountsSettings()
        xso.accounts[:] = [
            account.to_xso() for account in self._backend
        ]
        return xso

    def _do_save(self, f):
        xso = self._do_save_xso()
        aioxmpp.xml.write_single_xso(xso, f)

    def _do_load_xso(self, xso):
        for account_xso in xso.accounts:
            account = Account.from_xso(account_xso)
            self._backend.append(account)
            self.on_account_added(account)
            self._jidmap[account.jid] = account
            if account.enabled:
                self.on_account_enabled(account)

    def _do_load(self, f):
        assert not self._backend
        xso = aioxmpp.xml.read_single_xso(
            f,
            mlxc.xso.AccountsSettings
        )
        self._do_load_xso(xso)
