import abc
import asyncio
import logging
import weakref

import asyncio_xmpp.node
import asyncio_xmpp.security_layer
import asyncio_xmpp.presence
import asyncio_xmpp.plugins.roster

import mlxc.roster_model

from .utils import *

logger = logging.getLogger(__name__)

class AccountState:
    def __init__(self, account_jid, node, global_roster_root):
        self.account_jid = account_jid
        self.global_roster_root = global_roster_root
        self.node = node
        self.task = logged_async(node.manage())
        self.proster = asyncio_xmpp.plugins.roster.Client(
            self.node)
        self.proster.callbacks.add_callback(
            "initial_roster",
            self._initial_roster)

    def _initial_roster(self, mapping):
        for item in mapping.values():
            if item.groups:
                for group in item.groups:
                    grp = self.global_roster_root.get_group(group.name)
                    grp.append_via(self.account_jid, item.jid, item.name)
            else:
                self.global_roster_root.append_via(
                    self.account_jid, item.jid, item.name)

class Client:
    @classmethod
    def account_manager_factory(cls):
        import mlxc.account
        return mlxc.account.AccountManager()

    def node_factory(self, jid, initial_presence):
        return asyncio_xmpp.node.PresenceManagedClient(
            jid,
            asyncio_xmpp.security_layer.tls_with_password_based_authentication(
                self.accounts.password_provider,
                certificate_verifier_factory=asyncio_xmpp.security_layer._NullVerifier),
            initial_presence)

    def account_factory(self, node):
        return AccountState(node.client_jid, node, self.roster_root)

    @classmethod
    def roster_group_factory(cls, label):
        return mlxc.roster_model.RosterGroup(label)

    def __init__(self):
        self.accounts = self.account_manager_factory()
        self.nodes = {}
        self.roster_root = self.roster_group_factory("")
        self.accounts._on_account_enabled = self._on_account_enabled
        self.accounts._on_account_disabled = self._on_account_disabled
        self._global_presence = asyncio_xmpp.presence.PresenceState()

    def _on_account_enabled(self, jid):
        if jid in self.nodes:
            logger.warning("inconsistent state: %s got enabled, but is already"
                           " tracked",
                           jid)
            return
        node = self.node_factory(jid, self._global_presence)
        state = self.account_factory(node)
        logger.debug("account enabled: %s", jid)
        self.nodes[jid] = state

    def _on_account_disabled(self, jid):
        try:
            state = self.nodes.pop(jid)
        except KeyError:
            logger.warning("inconsistent state: %s got disabled, but was not"
                           " tracked",
                           jid)
            return
        if state.task is not None:
            # this will disconnect
            state.task.cancel()
        logger.debug("account disabled: %s", jid)

    @asyncio.coroutine
    def set_global_presence(self, new_presence):
        logger.debug("setting global presence to: %r", new_presence)
        futures = []
        for state in self.nodes.values():
            futures.append(
                state.node.set_presence(new_presence)
            )
        self._global_presence = new_presence
        yield from asyncio.gather(*futures)
