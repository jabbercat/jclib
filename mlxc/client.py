import asyncio
import xml.sax.handler

import keyring

import aioxmpp.stringprep

import aioxmpp.callbacks as callbacks
import aioxmpp.xso as xso

from mlxc.utils import mlxc_namespaces


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

    def __init__(self, jid):
        super().__init__()
        self._jid = jid.bare()
        self.resource = jid.resource

    @property
    def jid(self):
        return self._jid

    @property
    def enabled(self):
        return self._enabled


class _AccountList(xso.XSO):
    TAG = (mlxc_namespaces.account, "accounts")

    items = xso.ChildList([AccountSettings])


class AccountManager:
    KEYRING_SERVICE_NAME = "net.zombofant.mlxc"
    KEYRING_JID_FORMAT = "jid:{bare!s}"

    on_account_enabled = callbacks.Signal()
    on_account_disabled = callbacks.Signal()
    on_account_refresh = callbacks.Signal()

    def __init__(self, *, loop=None, use_keyring=None):
        super().__init__()
        self.keyring = (use_keyring
                        if use_keyring is not None
                        else keyring.get_keyring())
        self.loop = (loop
                     if loop is not None
                     else asyncio.get_event_loop())

        self._accountmap = {}
        self._jidlist = []

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
            self.on_account_enabled(jid)
        elif acc.enabled and not enable:
            acc._enabled = enable
            self.on_account_disabled(jid, reason=reason)

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
        writer = aioxmpp.xml.XMPPXMLGenerator(
            out=dest,
            short_empty_elements=True
        )

        writer.startDocument()
        writer.startElementNS(
            (mlxc_namespaces.account, "accounts"),
            None,
            {}
        )

        accounts = _AccountList()
        accounts.items.extend(self)
        accounts.unparse_to_sax(writer)

        writer.endElementNS(
            (mlxc_namespaces.account, "accounts"),
            None,
        )
        writer.endDocument()
        writer.flush()

    def _load_accounts(self, accounts):
        self.clear()
        for account in accounts.items:
            if account.jid in self._accountmap:
                continue
            self._jidlist.append(account.jid)
            self._accountmap[account.jid] = account

    def load(self, src):
        xso_parser = xso.XSOParser()
        xso_parser.add_class(_AccountList, self._load_accounts)
        driver = xso.SAXDriver(xso_parser)
        xml.sax.parse(src, driver)
