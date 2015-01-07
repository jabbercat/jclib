import abc
import asyncio
import functools
import logging
import os.path
import weakref

import xdg.BaseDirectory

import asyncio_xmpp.node
import asyncio_xmpp.security_layer
import asyncio_xmpp.presence
import asyncio_xmpp.plugins.roster

import mlxc.roster_model
import mlxc.xdg

from . import utils
from .utils import *

logger = logging.getLogger(__name__)

class AccountState:
    def __init__(self, account_jid, node, on_error=None):
        self.account_jid = account_jid
        self.node = node
        self.roster = asyncio_xmpp.plugins.roster.RosterClient(node)
        self.presence = asyncio_xmpp.plugins.roster.PresenceClient(node)
        self.task = asyncio.async(node.manage())
        self.task.add_done_callback(self._on_manage_terminated)
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
            logger.error("manage() let CancelledError bubble up")
        except Exception as err:
            self._report_error(err)
            return  # don’t restart on unknown error
        else:
            # don’t restart after shutdown
            return
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

class Client:
    XML_WRITER_OPTIONS = dict(
        pretty_print=True,
        encoding="utf-8"
    )

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
    def roster_factory(cls):
        return mlxc.roster_model.Roster()

    def __init__(self):
        self.accounts = self.account_manager_factory()
        self.nodes = {}
        self.roster_root = self.roster_factory()
        self.accounts._on_account_enabled = self._on_account_enabled
        self.accounts._on_account_disabled = self._on_account_disabled
        self._global_presence = asyncio_xmpp.presence.PresenceState()

    def _setup_account_state(self, jid):
        node = self.node_factory(jid, self._global_presence)
        state = self.account_factory(node)
        self.roster_root.enable_account(state)
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
        self.roster_root.disable_account(state)
        logger.debug("account disabled: %s", jid)

    def _save_config_path(self, name):
        return os.path.join(
            xdg.BaseDirectory.save_config_path(*mlxc.xdg.XDG_RESOURCE),
            name)

    @asyncio.coroutine
    def _load_config(self, name, parser):
        exc = None
        for path in xdg.BaseDirectory.load_config_paths(*mlxc.xdg.XDG_RESOURCE):
            try:
                return (yield from parser(os.path.join(path, name)))
            except OSError as err:
                if exc is None:
                    exc = err
        if exc is not None:
            raise exc
        return None

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

    @asyncio.coroutine
    def save(self):
        try:
            yield from self.save_accounts()
        except:
            logger.exception("failed to save accounts")
        try:
            yield from self.save_roster()
        except:
            logger.exception("failed to save roster")

    @asyncio.coroutine
    def save_accounts(self):
        yield from self.accounts.save(
            self._save_config_path("accounts.xml"),
            **self.XML_WRITER_OPTIONS
        )

    @asyncio.coroutine
    def save_roster(self):
        tree = self.roster_root.save_to_etree(None).getroottree()
        yield from utils.save_etree(
            self._save_config_path("roster.xml"),
            tree,
            **self.XML_WRITER_OPTIONS
        )

    @asyncio.coroutine
    def load(self):
        try:
            yield from self.load_accounts()
        except:
            logger.exception("failed to load accounts")
        try:
            yield from self.load_roster()
        except:
            logger.exception("failed to load roster")

    @asyncio.coroutine
    def load_accounts(self):
        try:
            tree = yield from self._load_config(
                "accounts.xml",
                utils.load_etree)
        except OSError:
            tree = None
        if tree is None:
            logger.error("failed to load accounts (no or errornous directory"
                         " structure)")
            return

        self.accounts.from_etree(tree.getroot())

    @asyncio.coroutine
    def load_roster(self):
        try:
            tree = yield from self._load_config(
                "roster.xml",
                utils.load_etree)
        except OSError:
            tree = None
        if tree is None:
            logger.error("failed to load roster (no or errornous directory"
                         " structure)")
            return

        self.roster_root.load_from_etree(tree.getroot())
