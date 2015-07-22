import asyncio

import keyring

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

    jid = xso.Attr(
        "jid",
        type_=xso.JID(),
        required=True,
    )

    enabled = xso.Attr(
        "enabled",
        type_=xso.Bool(),
        default=False
    )

    override_peer = xso.Child([ConnectionOverride])

    allow_unencrypted = xso.Attr(
        "allow-unencrypted",
        type_=xso.Bool(),
        default=False,
    )


class AccountManager:
    KEYRING_SERVICE_NAME = "net.zombofant.mlxc"
    KEYRING_JID_FORMAT = "jid:{bare!s}"

    def __init__(self, *, loop=None, use_keyring=None):
        super().__init__()
        self.keyring = (use_keyring
                        if use_keyring is not None
                        else keyring.get_keyring())
        self.loop = (loop
                     if loop is not None
                     else asyncio.get_event_loop())

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
