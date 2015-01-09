import asyncio
import collections
import contextlib
import functools
import logging

import keyring  # python3-keyring

import asyncio_xmpp.node
import asyncio_xmpp.jid
import asyncio_xmpp.stringprep

from . import utils
from .utils import *

logger = logging.getLogger(__name__)

ACCOUNTS_TAG = "{{{}}}accounts".format(mlxc_namespaces.accounts)
ACCOUNT_TAG = "{{{}}}account".format(mlxc_namespaces.accounts)

_AccountSettings = collections.namedtuple(
    "AccountSettings",
    [
        "jid",
        "resource",
        "override_host",
        "override_port",
        "enabled",
        "require_encryption"
    ])

class PasswordStoreIsUnsafe(RuntimeError):
    pass

class AccountSettings(_AccountSettings):
    def __new__(cls, jid,
                resource=None,
                override_host=None,
                override_port=5222,
                enabled=False,
                require_encryption=True):
        return _AccountSettings.__new__(
            cls,
            jid=jid,
            resource=resource,
            override_host=override_host,
            override_port=override_port,
            enabled=enabled,
            require_encryption=require_encryption)

    def __str__(self):
        jid = self.jid
        if self.resource:
            jid = self.jid.replace(resource=self.resource)
        return str(jid)

    def replace(self, **kwargs):
        resource = kwargs.pop("resource", self.resource) or None
        if resource:
            resource = asyncio_xmpp.stringprep.resourceprep(resource)
        kwargs["resource"] = resource
        return super()._replace(**kwargs)

    def to_etree(self, parent):
        el = etree.SubElement(parent, ACCOUNT_TAG)
        el.set("jid", str(self.jid.replace(resource=self.resource)))
        el.set("enabled", booltostr(self.enabled))
        if self.override_host:
            override_addr = etree.SubElement(el, "{{{}}}override-addr".format(
                mlxc_namespaces.accounts))
            override_addr.set("host", self.override_host)
            override_addr.set("port", str(self.override_port))
        if self.require_encryption:
            etree.SubElement(el, "{{{}}}require-encryption".format(
                mlxc_namespaces.accounts))
        return el

    @classmethod
    def from_etree(cls, el, **kwargs):
        require_encryption = el.find("{{{}}}require-encryption".format(
            mlxc_namespaces.accounts))
        override_addr = el.find("{{{}}}override-addr".format(
            mlxc_namespaces.accounts))
        if override_addr is not None:
            override_host = override_addr.get("host")
            try:
                override_port = int(override_addr.get("port", "5222"))
                if not 0 < override_port <= 65535:
                    override_port = None
            except ValueError:
                override_port = None
                override_host = None
        else:
            override_host = None
            override_port = None

        jid = asyncio_xmpp.jid.JID.fromstr(el.get("jid"))

        return cls(
            jid=jid.bare,
            resource=jid.resource,
            enabled=booltostr(el.get("enabled", "false")),
            override_host=override_host,
            override_port=override_port or 5222,
            require_encryption=bool(require_encryption))

class AccountManager:
    KEYRING_SERVICE_NAME = "net.zombofant.mlxc"
    KEYRING_JID_FORMAT = "jid:{bare!s}"
    KEYRING_IS_SAFE = keyring.get_keyring().priority >= 1

    def __init__(self, loop=None):
        self._loop = asyncio.get_event_loop()
        self._jids = {}
        self._jidlist = []
        self._on_account_enabled = None
        self._on_account_disabled = None

    def _account_enabled(self, jid):
        if self._on_account_enabled:
            self._on_account_enabled(jid)

    def _account_disabled(self, jid, *, reason=None):
        if self._on_account_disabled:
            self._on_account_disabled(jid)

    def _get_keyring_account_name(self, jid):
        return self.KEYRING_JID_FORMAT.format(
            bare=jid.bare,
            full=str(jid))

    def _require_jid_unique(self, jid):
        if jid in self._jids:
            raise ValueError("JID is already in use by a different account")

    def _register_account(self, info):
        self._require_jid_unique(info.jid)
        self._jids[info.jid] = info
        self._jidlist.append(info.jid)
        return info, info.jid

    @staticmethod
    def _parse_jid(jid):
        return asyncio_xmpp.jid.JID.fromstr(jid).bare

    def new_account(self, jid, name=None):
        jid = asyncio_xmpp.jid.JID.fromstr(jid)
        bare_jid = jid.bare

        info = AccountSettings(bare_jid,
                               resource=jid.resource,
                               enabled=False)
        return self._register_account(info)

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
            info = self._jids[jid]
            if info.enabled:
                self._account_disabled(jid)
            del self._jids[jid]
        del self._jidlist[index]

    def index(self, jid):
        return self._jidlist.index(jid)

    def remove(self, jid):
        del self[self.index(jid)]

    def update_account(self, jid, **kwargs):
        self._jids[jid] = self._jids[jid].replace(**kwargs)

    def clear(self):
        del self[:]

    def set_account_enabled(self, jid, enabled, *, reason=None):
        info = self.get_info(jid)
        if info.enabled == enabled:
            return
        self.update_account(jid, enabled=enabled)
        if enabled:
            self._account_enabled(jid)
        else:
            self._account_disabled(jid, reason=reason)

    @asyncio.coroutine
    def save(self, dest, *, loop=None, **kwargs):
        root = etree.Element(
            ACCOUNTS_TAG,
            nsmap={None: mlxc_namespaces.accounts})
        for acc in self._jids.values():
            acc.to_etree(root)
        tree = root.getroottree()
        yield from utils.save_etree(dest, tree, loop=loop, **kwargs)

    def from_etree(self, root):
        if root.tag != ACCOUNTS_TAG:
            raise ValueError("root node has invalid tag")
        self.clear()
        any_error = False
        for account_el in root.iterchildren(ACCOUNT_TAG):
            try:
                account = AccountSettings.from_etree(account_el)
            except ValueError:
                any_error = True
                logger.warning("failed to load account", exc_info=True)
                continue
            self._register_account(account)
            logger.debug("account loaded: %s", account.jid)

        if any_error:
            logger.error("not all accounts loaded successfully. see previous"
                         " warnings for details")

        for jid, info in self._jids.items():
            if info.enabled:
                self._account_enabled(jid)

    @asyncio.coroutine
    def load(self, source, *, loop=None, **kwargs):
        tree = yield from utils.load_etree(source, loop=loop, **kwargs)
        self.from_etree(tree.getroot())
