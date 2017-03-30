import typing

import aioxmpp.callbacks
import aioxmpp.xml

from aioxmpp import JID

import mlxc.config
import mlxc.instrumentable_list
import mlxc.utils
import mlxc.xso


class Account(mlxc.instrumentable_list.ModelTreeNodeHolder):
    def __init__(self, node, jid, colour):
        super().__init__()
        self.__node = node
        self.__node.object_ = self
        self._jid = jid
        self.enabled = True
        self.allow_unencrypted = False
        self.stashed_xml = []
        self.colour = colour

    @property
    def _node(self):
        return self.__node

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
    def from_xso(cls, object_, node):
        colour = tuple(map(int, object_.colour.split()))
        result = cls(node, object_.jid, colour)
        result.enabled = not object_.disabled
        result.allow_unencrypted = bool(object_.allow_unencrypted)
        result.stashed_xml = list(object_._)
        return result


class Identity(mlxc.instrumentable_list.ModelTreeNodeHolder):
    def __init__(self, node, name, **kwargs):
        super().__init__()
        self.name = name
        self.accounts = node
        self.accounts.object_ = self
        self.enabled = True
        self.custom_presences = []
        self.stashed_xml = []

    @property
    def _node(self):
        return self.accounts

    def to_xso(self):
        result = mlxc.xso.IdentitySettings()
        result.name = self.name
        result.accounts[:] = [
            account.to_xso() for account in self.accounts
        ]
        result.disabled = not self.enabled
        result._[:] = self.stashed_xml
        return result

    @classmethod
    def from_xso(cls, object_, node):
        result = cls(node, object_.name)

        for acc_settings in object_.accounts:
            acc_node = mlxc.instrumentable_list.ModelTreeNode(
                node._tree
            )
            result.accounts.append(
                Account.from_xso(acc_settings, acc_node)
            )

        result.custom_presences[:] = object_.custom_presences
        result.stashed_xml[:] = object_._
        result.enabled = not object_.disabled

        return result


class Identities(mlxc.config.SimpleConfigurable,
                 mlxc.instrumentable_list.ModelTreeNodeHolder):
    UID = mlxc.utils.mlxc_uid
    FILENAME = "identities.xml"

    on_account_enabled = aioxmpp.callbacks.Signal()
    on_account_disabled = aioxmpp.callbacks.Signal()

    on_account_online = aioxmpp.callbacks.Signal()
    on_account_offline = aioxmpp.callbacks.Signal()
    on_account_unstable = aioxmpp.callbacks.Signal()

    on_account_added = aioxmpp.callbacks.Signal()
    on_account_removed = aioxmpp.callbacks.Signal()

    on_identity_added = aioxmpp.callbacks.Signal()
    on_identity_removed = aioxmpp.callbacks.Signal()
    on_identity_enabled = aioxmpp.callbacks.Signal()
    on_identity_disabled = aioxmpp.callbacks.Signal()

    def __init__(self):
        super().__init__()
        self._tree = mlxc.instrumentable_list.ModelTree()
        self._jidmap = {}
        self.identities = self._tree.root
        self.identities.object_ = self

    @property
    def _node(self):
        return self.identities

    def _require_unique_jid(self, jid: JID) -> JID:
        jid = jid.bare()
        if jid in self._jidmap:
            raise ValueError("duplicate account JID")
        return jid

    def new_account(self, identity: Identity, jid: JID,
                    colour: typing.Tuple[int, int, int]) -> Account:
        bare_jid = self._require_unique_jid(jid)
        node = mlxc.instrumentable_list.ModelTreeNode(self._tree)
        result = Account(node, bare_jid, colour)
        result.resource = jid.resource
        identity.accounts.append(result)
        self._jidmap[bare_jid] = (identity, result)
        self.on_account_added(result)
        self.on_account_enabled(result)
        return result

    def new_identity(self, name: str) -> Identity:
        node = mlxc.instrumentable_list.ModelTreeNode(self._tree)
        result = Identity(node, name)
        self.identities.append(result)
        self.on_identity_added(result)
        self.on_identity_enabled(result)
        return result

    def lookup_jid(self, jid: JID) -> (Identity, Account):
        return self._jidmap[jid.bare()]

    def lookup_account_identity(self, account: Account) -> Identity:
        return self.lookup_jid(account.jid)[0]

    def remove_account(self, account: Account):
        self.on_account_disabled(account)
        self.on_account_removed(account)
        identity, _ = self._jidmap.pop(account.jid)
        identity.accounts.remove(account)

    def remove_identity(self, identity: Identity):
        for acc in identity.accounts:
            self.on_account_disabled(acc)
            self.on_account_removed(acc)
            self._jidmap.pop(acc.jid)
        self.on_identity_disabled(identity)
        self.on_identity_removed(identity)
        self.identities.remove(identity)

    def set_account_enabled(self, account: Account, enabled: bool):
        if bool(account.enabled) == bool(enabled):
            return
        account.enabled = enabled
        identity = self.lookup_account_identity(account)
        if enabled and identity.enabled:
            self.on_account_enabled(account)
        elif not enabled and identity.enabled:
            self.on_account_disabled(account)
        account._node.refresh_self(None)

    def set_identity_enabled(self, identity: Identity, enabled: bool):
        if bool(identity.enabled) == bool(enabled):
            return
        identity.enabled = enabled
        if enabled:
            self.on_identity_enabled(identity)
        for account in identity.accounts:
            if account.enabled and not enabled:
                self.on_account_disabled(account)
            elif account.enabled and enabled:
                self.on_account_enabled(account)
        if not enabled:
            self.on_identity_disabled(identity)
        identity._node.refresh_self(None)
        identity._node.refresh_data(slice(0, len(identity.accounts)), None)

    def set_identity_presence(self, identity: Identity, presence):
        pass

    def _do_save_xso(self):
        xso = mlxc.xso.IdentitiesSettings()
        xso.identities[:] = [
            identity.to_xso() for identity in self.identities
        ]
        return xso

    def _do_save(self, f):
        xso = self._do_save_xso()
        aioxmpp.xml.write_single_xso(xso, f)

    def _do_load_xso(self, xso):
        for identity_xso in xso.identities:
            node = mlxc.instrumentable_list.ModelTreeNode(self._tree)
            identity = Identity.from_xso(identity_xso, node)
            self.identities.append(identity)
            self.on_identity_added(identity)
            if identity.enabled:
                self.on_identity_enabled(identity)
            for account in identity.accounts:
                self._jidmap[account.jid] = (identity, account)
                self.on_account_added(account)
                if account.enabled and identity.enabled:
                    self.on_account_enabled(account)


    def _do_load(self, f):
        assert not self.identities
        xso = aioxmpp.xml.read_single_xso(
            f,
            mlxc.xso.IdentitiesSettings
        )
        self._do_load_xso(xso)
