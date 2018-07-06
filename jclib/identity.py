import base64
import random
import typing

import aioxmpp.callbacks
import aioxmpp.xml

from aioxmpp import JID

import jclib.config
import jclib.instrumentable_list
import jclib.utils
import jclib.xso


def generate_resource():
    rng = random.SystemRandom()
    return "jabbercat-{}".format(
        base64.urlsafe_b64encode(
            rng.getrandbits(24).to_bytes(
                3, 'little'
            )
        ).decode(
            'ascii'
        )
    )


class Account:
    def __init__(self, jid, colour):
        super().__init__()
        self._jid = jid.bare()
        self.resource = jid.resource
        self.enabled = True
        self.allow_unencrypted = False
        self.stashed_xml = []
        self.colour = colour
        self.client = None

    def autofill_resource(self):
        if self.resource is None:
            self.resource = generate_resource()

    @property
    def full_jid(self):
        self.autofill_resource()
        return self._jid.replace(resource=self.resource)

    @property
    def jid(self):
        return self._jid

    def to_xso(self):
        result = jclib.xso.AccountSettings(self._jid.replace(
            resource=self.resource
        ))
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
        result.autofill_resource()
        return result


class Accounts(jclib.config.SimpleConfigurable,
               jclib.instrumentable_list.ModelListView):
    UID = jclib.utils.jclib_uid
    FILENAME = "accounts.xml"

    on_account_enabled = aioxmpp.callbacks.Signal()
    on_account_disabled = aioxmpp.callbacks.Signal()

    on_account_added = aioxmpp.callbacks.Signal()
    on_account_removed = aioxmpp.callbacks.Signal()

    def __init__(self):
        super().__init__(jclib.instrumentable_list.ModelList())
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
        result.autofill_resource()
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
        xso = jclib.xso.AccountsSettings()
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
            jclib.xso.AccountsSettings
        )
        self._do_load_xso(xso)
