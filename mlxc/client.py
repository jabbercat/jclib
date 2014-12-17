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
    def __init__(self, account_jid, node, global_roster_root, on_error=None):
        self.account_jid = account_jid
        self.global_roster_root = global_roster_root
        self.node = node
        self.task = asyncio.async(node.manage())
        self.task.add_done_callback(self._on_manage_terminated)
        self.proster = asyncio_xmpp.plugins.roster.Client(
            self.node)
        self.proster.callbacks.add_callback(
            "initial_roster",
            self._initial_roster)
        self.on_error = on_error

    def _on_manage_terminated(self, task):
        try:
            task.result()
        except asyncio_xmpp.errors.AuthenticationFailure as err:
            self._report_error(
                err,
                title="Authentication failed")
        except asyncio_xmpp.errors.StreamNegotiationFailure as err:
            self._report_error(
                err,
                title="Stream negotiation failed")
        except OSError as err:
            self._report_error(
                err,
                title="Connection failed")
        except asyncio.CancelledError:
            pass
        except Exception as err:
            self._report_error(err)
            return  # don’t restart on unknown error
        else:
            logger.error("manage() exited unexpectedly, without error")
        self.task = asyncio.async(self.node.manage(
            set_presence=asyncio_xmpp.presence.PresenceState()))
        self.task.add_done_callback(self._on_manage_terminated)

    def _report_error(self, err, title=None):
        title = title or type(err).__name__
        text = str(err)
        if self.on_error:
            self.on_error(self.account_jid, err, title, text)
        else:
            logger.error("unhandled error from account: %r", err)

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

    def _setup_account_state(self, jid):
        node = self.node_factory(jid, self._global_presence)
        state = self.account_factory(node)
        return state

    def _on_account_enabled(self, jid):
        if jid in self.nodes:
            logger.warning("inconsistent state: %s got enabled, but is already"
                           " tracked",
                           jid)
            return
        logger.debug("account enabled: %s", jid)
        self.nodes[jid] = self._setup_account_state(jid)

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
