import asyncio
import collections.abc
import functools
import json
import logging
import xml.sax.handler

import keyring

import aioxmpp.stringprep

import aioxmpp.callbacks as callbacks
import aioxmpp.node as node
import aioxmpp.security_layer as security_layer
import aioxmpp.stanza as stanza
import aioxmpp.structs as structs
import aioxmpp.xso as xso

import mlxc.utils as utils
import mlxc.instrumentable_list as instrumentable_list

from mlxc.utils import mlxc_namespaces


logger = logging.getLogger(__name__)


class PasswordStoreIsUnsafe(RuntimeError):
    pass


class ConnectionOverride(xso.XSO):
    TAG = (mlxc_namespaces.account, "override-host")

    host = xso.Text()

    port = xso.Attr(
        "port",
        type_=xso.Integer()
    )


class AccountSettings(xso.XSO):
    TAG = (mlxc_namespaces.account, "account")

    _jid = xso.Attr(
        "jid",
        type_=xso.JID(),
        required=True,
    )

    _enabled = xso.Attr(
        "enabled",
        type_=xso.Bool(),
        default=False
    )

    resource = xso.Attr(
        "resource",
        required=False,
        type_=xso.String(prepfunc=aioxmpp.stringprep.resourceprep)
    )

    override_peer = xso.Child([ConnectionOverride])

    allow_unencrypted = xso.Attr(
        "allow-unencrypted",
        type_=xso.Bool(),
        default=False,
    )

    def __init__(self, jid, enabled=False):
        super().__init__()
        self._jid = jid.bare()
        self.resource = jid.resource
        self._enabled = enabled

    @property
    def jid(self):
        return self._jid

    @property
    def enabled(self):
        return self._enabled


class SinglePresenceStateStatus(xso.AbstractTextChild):
    TAG = (mlxc_namespaces.presence, "status")


class SinglePresenceState(xso.XSO):
    TAG = (mlxc_namespaces.presence, "single-presence")

    _available = xso.Attr(
        "available",
        type_=xso.Bool(),
        default=None
    )
    _show = xso.Attr(
        "show",
        type_=stanza.Presence.show.type_
    )
    status = xso.ChildList(
        [aioxmpp.stanza.Status]
    )
    jid = xso.Attr(
        "jid",
        type_=xso.JID(),
        default=None
    )

    def __init__(self, presence=None, status=None):
        super().__init__()
        self.presence = presence
        if isinstance(status, str):
            self.status.append(aioxmpp.stanza.Status(status))
        elif isinstance(status, collections.abc.Iterable):
            self.status[:] = status

    @property
    def presence(self):
        if self._available is None:
            return None
        return structs.PresenceState(self._available, self._show)

    @presence.setter
    def presence(self, value):
        if value is not None:
            self._available = value.available
            self._show = value.show
        else:
            self._available = None
            self._show = None

    def __eq__(self, other):
        try:
            return (self.presence == other.presence and
                    self.status == other.status)
        except AttributeError:
            return NotImplemented


def _state_jid_key(state):
    return state.jid


class ComplexPresenceState(xso.XSO):
    TAG = (mlxc_namespaces.presence, "complex-presence")

    name = xso.Attr(
        "name",
        required=True
    )

    states = xso.ChildMap(
        [SinglePresenceState],
        key=_state_jid_key
    )


class FundamentalPresenceState:
    def __init__(self, state=structs.PresenceState()):
        super().__init__()
        self.states = {
            None: [SinglePresenceState(state)]
        }


class _ComplexPresenceList(xso.XSO):
    TAG = (mlxc_namespaces.presence, "presences")

    DECLARE_NS = {
        None: mlxc_namespaces.presence
    }

    items = xso.ChildList([ComplexPresenceState])

    def __init__(self, items=[]):
        super().__init__()
        self.items[:] = items


class _AccountList(xso.XSO):
    TAG = (mlxc_namespaces.account, "accounts")

    DECLARE_NS = {
        None: mlxc_namespaces.account
    }

    items = xso.ChildList([AccountSettings])


class AccountManager:
    KEYRING_SERVICE_NAME = "net.zombofant.mlxc"
    KEYRING_JID_FORMAT = "xmpp:{bare!s}"

    on_account_enabled = callbacks.Signal()
    on_account_disabled = callbacks.Signal()
    on_account_refresh = callbacks.Signal()

    def __init__(self, *, loop=None, use_keyring=None):
        super().__init__()
        self.keyring = (use_keyring
                        if use_keyring is not None
                        else keyring.get_keyring())
        self.keyring_is_safe = self.keyring.priority >= 1
        self.loop = (loop
                     if loop is not None
                     else asyncio.get_event_loop())

        self._accountmap = {}
        self._jidlist = instrumentable_list.ModelList()

    def _require_unique_jid(self, bare_jid):
        assert bare_jid.resource is None
        if bare_jid in self._accountmap:
            raise ValueError("duplicate jid")

    @asyncio.coroutine
    def get_stored_password(self, jid):
        if self.keyring.priority < 1:
            raise PasswordStoreIsUnsafe()

        return (yield from self.loop.run_in_executor(
            None,
            keyring.get_password,
            self.KEYRING_SERVICE_NAME,
            self.KEYRING_JID_FORMAT.format(
                bare=jid.bare
            )
        ))

    @asyncio.coroutine
    def set_stored_password(self, jid, password):
        if self.keyring.priority < 1:
            raise PasswordStoreIsUnsafe()

        if password is None:
            try:
                yield from self.loop.run_in_executor(
                    None,
                    keyring.delete_password,
                    self.KEYRING_SERVICE_NAME,
                    self.KEYRING_JID_FORMAT.format(
                        bare=jid.bare
                    ),
                )
            except keyring.errors.PasswordDeleteError:
                pass
        else:
            yield from self.loop.run_in_executor(
                None,
                keyring.set_password,
                self.KEYRING_SERVICE_NAME,
                self.KEYRING_JID_FORMAT.format(
                    bare=jid.bare
                ),
                password
            )

    def __iter__(self):
        return iter(self._accountmap[jid]
                    for jid in self._jidlist)

    def __len__(self):
        return len(self._jidlist)

    def __delitem__(self, index):
        if not isinstance(index, slice):
            jids = [self._jidlist[index]]
        else:
            jids = self._jidlist[index]

        for jid in jids:
            self.set_account_enabled(jid, False)

        for jid in jids:
            del self._accountmap[jid]
        del self._jidlist[index]

    def __getitem__(self, index):
        if not isinstance(index, slice):
            return self._accountmap[self._jidlist[index]]
        else:
            return [self._accountmap[jid]
                    for jid in self._jidlist[index]]

    def jid_index(self, jid):
        jid = jid.bare()
        return self._jidlist.index(jid)

    def jid_account(self, jid):
        return self._accountmap[jid.bare()]

    def account_index(self, account):
        for i, jid in enumerate(self._jidlist):
            if self._accountmap[jid] == account:
                return i
        raise ValueError("{!r} not in list".format(account))

    def new_account(self, jid):
        bare_jid = jid.bare()
        self._require_unique_jid(bare_jid)
        acc = AccountSettings(jid)
        self._accountmap[bare_jid] = acc
        self._jidlist.append(bare_jid)
        return acc

    def set_account_enabled(self, jid, enable, *, reason=None):
        jid = jid.bare()
        acc = self._accountmap[jid]
        if not acc.enabled and enable:
            acc._enabled = enable
            self.on_account_enabled(acc)
        elif acc.enabled and not enable:
            acc._enabled = enable
            self.on_account_disabled(acc, reason=reason)

    def refresh_account(self, jid):
        acc = self._accountmap[jid.bare()]
        self.on_account_refresh(acc)

    def clear(self):
        del self[:]

    def remove_jid(self, jid):
        jid = jid.bare()
        del self[self.jid_index(jid)]

    def remove_account(self, account):
        del self[self.account_index(account)]

    def save(self, dest):
        accounts = _AccountList()
        accounts.items.extend(self)
        utils.write_xso(dest, accounts)

    def _load_accounts(self, accounts):
        self.clear()
        for account in accounts.items:
            if not account.jid.is_bare:
                account.resource = account.jid.resource
                account._jid = account.jid.bare()

            if account.jid in self._accountmap:
                continue
            self._accountmap[account.jid] = account
            self._jidlist.append(account.jid)

        for account in self:
            if account.enabled:
                self.on_account_enabled(account)

    def load(self, src):
        utils.read_xso(src, {
            _AccountList: self._load_accounts
        })

    @asyncio.coroutine
    def password_provider(self, jid, nattempt):
        try:
            result = yield from self.get_stored_password(jid.bare())
        except PasswordStoreIsUnsafe:
            raise KeyError(jid)
        if result is None:
            raise KeyError(jid)
        return result


class Client:
    """
    The :class:`Client` keeps track of all the information a client needs. It
    is a huge composite which glues together the pieces which make an XMPP
    client an XMPP client (roster, account management, you name it).

    `config_manager` must be a :class:`~mlxc.config.ConfigManager` compatible
    class. It is used to load the state (accounts, roster, …) and offered at
    :attr:`config_manager` to plug-ins.

    .. attribute:: AccountManager

       This class attribute defines the :class:`AccountManager` class to
       use. This defaults to :class:`AccountManager`, but can be overriden by
       subclasses to drop in their own account manager.

    .. attribute:: accounts

       Each instance has an instance of :attr:`AccountManager` bound at this
       attribute.

    .. attribute:: config_manager

       The :class:`~mlxc.config.ConfigManager` instance passed as
       `config_manager`.

    The :class:`Client` tracks all enabled accounts (enabled as in
    :meth:`AccountManager.set_account_enabled`). For all enabled accounts,
    there exists a :class:`aioxmpp.node.PresenceManagedClient` instance.

    An *enabled* account can either be active (*started*) or inactive
    (*stopped*, we all love systemd terminology here; even disabled accounts
    can still be *started* though, for example if it has been disabled but has
    not stopped yet).

    Normally, all enabled accounts are started, as long as an ``available``
    global presence is set. The only exception is if the account fatally fails
    to connect (even reconnect attempts count as *started*). An example for
    such a fatal failure could be a TLS negotiation problem or a mundane
    authentication failure.

    A account which is not *started* can be started by setting its presence to
    an ``available`` value. This can be done using the global presence setting
    or by setting the presence on the account specifically. Note that global
    presence will only affect the account if its current presence is equal to
    the current global presence.

    """

    AccountManager = AccountManager

    def __init__(self, config_manager):
        super().__init__()
        self.config_manager = config_manager
        self.config_manager.on_writeback.connect(self.save_state)

        self.accounts = self.AccountManager()
        self.accounts.on_account_enabled.connect(
            self._on_account_enabled
        )
        self.accounts.on_account_disabled.connect(
            self._on_account_disabled
        )

        self.pin_store = aioxmpp.security_layer.PublicKeyPinStore()

        self.presence_states = instrumentable_list.ModelList()

        self._states = {}

        self._current_presence = FundamentalPresenceState(
            aioxmpp.structs.PresenceState(False)
        )

    def _single_presence_for_jid(self, jid):
        try:
            return self._current_presence.states[jid][0]
        except (KeyError, IndexError):
            return self._current_presence.states[None][0]

    def _on_account_enabled(self, account):
        node = aioxmpp.node.PresenceManagedClient(
            account.jid.replace(resource=account.resource),
            security_layer.tls_with_password_based_authentication(
                self.accounts.password_provider,
                certificate_verifier_factory=functools.partial(
                    self._make_certificate_verifier,
                    account
                )
            )
        )
        node.presence = self._single_presence_for_jid(account.jid).presence

        self._states[account] = node

    def _on_account_disabled(self, account, reason):
        del self._states[account]

    def _make_certificate_verifier(self, account):
        return aioxmpp.security_layer.PinningPKIXCertificateVerifier(
            self.pin_store.query,
            functools.partial(self._decide_on_certificate, account)
        )

    @asyncio.coroutine
    def _decide_on_certificate(self, account, verifier):
        logger.warning("no implementation to decide on certificate, "
                       "returning False")
        return False

    def account_state(self, account):
        return self._states[account]

    @property
    def current_presence(self):
        return self._current_presence

    def apply_presence_state(self, new_presence):
        self._current_presence = new_presence
        for account, state in self._states.items():
            single_presence = self._single_presence_for_jid(account.jid)
            state.set_presence(single_presence.presence,
                               single_presence.status)

    def stop_all(self):
        for node in self._states.values():
            node.stop()

    @asyncio.coroutine
    def stop_and_wait_for_all(self):
        nodes = [
            node
            for node in self._states.values()
            if node.running
        ]

        futures = [
            asyncio.Future()
            for node in nodes
        ]

        for future, node in zip(futures, nodes):
            node.on_stopped.connect(
                future,
                callbacks.AdHocSignal.AUTO_FUTURE
            )
            node.on_failure.connect(
                future,
                callbacks.AdHocSignal.AUTO_FUTURE
            )
            node.stop()

        yield from asyncio.gather(
            *futures,
            return_exceptions=True)

    def _load_accounts(self):
        try:
            accounts_file = self.config_manager.open_single(
                utils.mlxc_uid,
                "accounts.xml")
        except OSError:
            self.accounts.clear()
        else:
            with accounts_file:
                self.accounts.load(accounts_file)

    def _import_presence_states(self, presences_xso):
        self.presence_states[:] = presences_xso.items

    def _load_presence_states(self):
        try:
            f = self.config_manager.open_single(
                utils.mlxc_uid,
                "presence.xml")
        except OSError:
            self.presence_states.clear()
        else:
            with f:
                utils.read_xso(f, {
                    _ComplexPresenceList: self._import_presence_states
                })

    def _load_pin_store(self):
        try:
            with self.config_manager.open_single(
                    utils.mlxc_uid,
                    "pinstore.json",
                    mode="r",
                    encoding="utf-8") as f:
                data = json.load(f)
        except OSError:
            self.pin_store.import_from_json({}, override=True)
        except Exception:
            self.pin_store.import_from_json({}, override=True)
            raise
        else:
            self.pin_store.import_from_json(data, override=True)

    def load_state(self):
        try:
            self._load_accounts()
        except Exception as exc:
            logger.error("failed to load accounts", exc_info=True)

        try:
            self._load_pin_store()
        except Exception as exc:
            logger.error("failed to load certificate pin store",
                         exc_info=True)

        try:
            self._load_presence_states()
        except Exception as exc:
            logger.error("failed to load custom presence states",
                         exc_info=True)

    def save_state(self):
        with self.config_manager.open_single(
                utils.mlxc_uid,
                "accounts.xml",
                mode="wb") as f:
            self.accounts.save(f)

        data = self.pin_store.export_to_json()
        with self.config_manager.open_single(
                utils.mlxc_uid,
                "pinstore.json",
                mode="w",
                encoding="utf-8") as f:
            json.dump(data, f)

        xso = _ComplexPresenceList(self.presence_states)
        with self.config_manager.open_single(
                utils.mlxc_uid,
                "presence.xml",
                mode="wb") as f:
            utils.write_xso(f, xso)
