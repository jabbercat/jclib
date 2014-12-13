import asyncio
import functools

import collections
import contextlib

import keyring  # python3-keyring

import asyncio_xmpp.node
import asyncio_xmpp.jid

_AccountInfo = collections.namedtuple(
    "AccountInfo",
    [
        "jid",
        "name"
    ])


_AccountInfo.replace = _AccountInfo._replace

class PasswordStoreIsUnsafe(RuntimeError):
    pass

class AccountInfo(_AccountInfo):
    def __str__(self):
        if not self.name:
            return str(self.jid)
        return "{} ({})".format(self.name, self.jid)

class AccountManager:
    KEYRING_SERVICE_NAME = "net.zombofant.mlxc"
    KEYRING_JID_FORMAT = "jid:{bare!s}"
    KEYRING_IS_SAFE = keyring.get_keyring().priority >= 1

    def __init__(self, loop=None):
        self._loop = asyncio.get_event_loop()
        self._jids = {}
        self._jidlist = []

    def _get_keyring_account_name(self, jid):
        return self.KEYRING_JID_FORMAT.format(
            bare=jid.bare,
            full=str(jid))

    def _require_jid_unique(self, jid):
        if jid in self._jids:
            raise ValueError("JID is already in use by a different account")

    def new_account(self, jid, name=None):
        jid = asyncio_xmpp.jid.JID.fromstr(jid)
        self._require_jid_unique(jid)

        self._jids[jid] = AccountInfo(jid, name)
        self._jidlist.append(jid)

    def get_info(self, jid):
        return self._jids[jid]

    @asyncio.coroutine
    def get_stored_password(self, jid):
        if keyring.get_keyring().priority < 1:
            raise PasswordStoreIsUnsafe()
        return (yield from self._loop.run_in_executor(
            None,
            keyring.get_password,
            self.KEYRING_SERVICE_NAME,
            self._get_keyring_account_name(jid)
        ))

    @asyncio.coroutine
    def set_stored_password(self, jid, password):
        if keyring.get_keyring().priority < 1:
            raise PasswordStoreIsUnsafe()
        service = self.KEYRING_SERVICE_NAME
        account = self._get_keyring_account_name(jid)
        if password is None:
            func = functools.partial(
                keyring.delete_password,
                service,
                account)
        else:
            func = functools.partial(
                keyring.set_password,
                service,
                account,
                password)
        try:
            yield from self._loop.run_in_executor(
                None,
                func)
        except keyring.errors.PasswordDeleteError:
            pass

    @asyncio.coroutine
    def password_provider(self, jid, nattempt):
        try:
            result = yield from self.get_stored_password(jid)
        except PasswordStoreIsUnsafe:
            raise KeyError(jid)
        if result is None:
            raise KeyError(jid)
        return result

    def __iter__(self):
        return (
            self._jids[jid]
            for jid in self._jidlist
        )

    def __len__(self):
        return len(self._jidlist)

    def __contains__(self, jid):
        return jid in self._jids

    def __getitem__(self, index):
        if isinstance(index, slice):
            return [
                self._jids[jid]
                for jid in self._jidlist[index]
            ]
        else:
            jid = self._jidlist[index]
            return self._jids[jid]

    def __delitem__(self, index):
        if isinstance(index, slice):
            jids = self._jidlist[index]
        else:
            jids = [self._jidlist[index]]
        for jid in jids:
            del self._jids[jid]
        del self._jidlist[index]

    def index(self, jid):
        return self._jidlist.index(jid)

    def remove(self, jid):
        del self[self.index(jid)]

    def update_account(self, jid, **kwargs):
        self._jids[jid] = self._jids[jid].replace(**kwargs)
