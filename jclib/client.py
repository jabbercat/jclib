import asyncio
import concurrent.futures
import functools
import logging

import keyring

import aioxmpp

from . import identity, utils, instrumentable_list, tasks


class PasswordStoreIsUnsafe(RuntimeError):
    pass


def dbus_aware_keyring_wrapper(method, *args):
    try:
        import dbus
    except ImportError:
        # nothing to do!
        pass
    else:
        import dbus.mainloop.glib
        dbus.set_default_main_loop(dbus.mainloop.glib.DBusGMainLoop())
    return method(*args)


class RosterGroups(aioxmpp.service.Service):
    ORDER_AFTER = [aioxmpp.RosterClient]

    def __init__(self, client, **kwargs):
        super().__init__(client, **kwargs)
        self.groups = instrumentable_list.ModelList()

    @aioxmpp.service.depsignal(aioxmpp.RosterClient, "on_group_added")
    def handle_group_added(self, group):
        self.groups.append(group)

    @aioxmpp.service.depsignal(aioxmpp.RosterClient, "on_group_removed")
    def handle_group_removed(self, group):
        self.groups.remove(group)


class Client:
    on_client_prepare = aioxmpp.callbacks.Signal()
    on_client_stopped = aioxmpp.callbacks.Signal()

    def __init__(self, accounts: identity.Accounts, *, use_keyring=None):
        super().__init__()
        self._accounts = accounts
        self._custom_executor = concurrent.futures.ThreadPoolExecutor(
            max_workers=1,
        )
        self.logger = logging.getLogger(
            type(self).__module__ + type(self).__qualname__
        )
        accounts.on_account_enabled.connect(self.on_account_enabled)
        accounts.on_account_disabled.connect(self.on_account_disabled)
        self.loop = asyncio.get_event_loop()
        self.keyring = (use_keyring
                        if use_keyring is not None
                        else keyring.get_keyring())
        self.keyring_is_safe = self.keyring.priority >= 1
        self.clients = {}

    def client_by_account(self, account: identity.Account) -> aioxmpp.Client:
        return self.clients[account]

    @asyncio.coroutine
    def get_stored_password(self, jid):
        if self.keyring.priority < 1:
            raise PasswordStoreIsUnsafe()

        return (yield from self.loop.run_in_executor(
            self._custom_executor,
            dbus_aware_keyring_wrapper,
            keyring.get_password,
            utils.KEYRING_SERVICE_NAME,
            utils.KEYRING_JID_FORMAT.format(
                bare=jid.bare()
            )
        ))

    @asyncio.coroutine
    def set_stored_password(self, jid, password):
        if self.keyring.priority < 1:
            raise PasswordStoreIsUnsafe()

        if password is None:
            try:
                yield from self.loop.run_in_executor(
                    self._custom_executor,
                    dbus_aware_keyring_wrapper,
                    keyring.delete_password,
                    utils.KEYRING_SERVICE_NAME,
                    utils.KEYRING_JID_FORMAT.format(
                        bare=jid.bare()
                    ),
                )
            except keyring.errors.PasswordDeleteError:
                pass
        else:
            yield from self.loop.run_in_executor(
                self._custom_executor,
                dbus_aware_keyring_wrapper,
                keyring.set_password,
                utils.KEYRING_SERVICE_NAME,
                utils.KEYRING_JID_FORMAT.format(
                    bare=jid.bare()
                ),
                password
            )

    @asyncio.coroutine
    def get_password(self, jid, nattempt):
        if nattempt == 0:
            result = yield from self.get_stored_password(jid)
            if result is not None:
                return result
        return None

    @asyncio.coroutine
    def _client_suspended(self, client):
        tasks.manager.update_text("Reconnecting {}".format(
            client.local_jid.bare()
        ))
        fut = asyncio.Future()
        client.on_stream_established.connect(
            fut,
            client.on_stream_established.AUTO_FUTURE
        )
        client.on_failure.connect(
            fut,
            client.on_failure.AUTO_FUTURE,
        )
        yield from fut

    @asyncio.coroutine
    def _client_connecting(self, client):
        tasks.manager.update_text("Connecting to {}".format(
            client.local_jid.bare()
        ))
        fut = asyncio.Future()
        client.on_stream_established.connect(
            fut,
            client.on_stream_established.AUTO_FUTURE
        )
        client.on_stream_suspended.connect(
            fut,
            client.on_stream_suspended.AUTO_FUTURE
        )
        client.on_failure.connect(
            fut,
            client.on_failure.AUTO_FUTURE,
        )
        yield from fut

    def _new_client(self, account: identity.Account):
        assert account.client is None

        result = aioxmpp.PresenceManagedClient(
            account.jid,
            aioxmpp.make_security_layer(
                self.get_password,
            )
        )
        disco = result.summon(aioxmpp.DiscoServer)
        disco.register_identity("client", "pc")
        disco.unregister_identity("client", "bot")
        result.summon(aioxmpp.MUCClient)
        result.summon(aioxmpp.AdHocClient)
        result.summon(aioxmpp.PresenceClient)
        result.summon(aioxmpp.RosterClient)
        result.summon(RosterGroups)
        result.summon(aioxmpp.im.p2p.Service)
        account.client = result
        self.on_client_prepare(account, result)
        tasks.manager.start(self._client_connecting(result))
        return result

    def on_account_enabled(self, account: identity.Account):
        client = self._new_client(account)
        client.on_stream_established.connect(
            functools.partial(self.on_stream_established,
                              account)
        )
        client.on_stream_destroyed.connect(
            functools.partial(self.on_stream_destroyed,
                              account)
        )
        client.on_stream_suspended.connect(
            functools.partial(self.on_stream_suspended,
                              account)
        )
        client.on_failure.connect(
            functools.partial(self.on_stopped,
                              account)
        )
        client.on_stopped.connect(
            functools.partial(self.on_stopped,
                              account)
        )
        self.clients[account] = client
        client.presence = aioxmpp.PresenceState(True)

    def on_stream_established(self, account):
        self.logger.info("stream established for account %r", account)

    def on_stream_suspended(self, account):
        self.logger.info("stream suspended for account %r", account)
        client = account.client
        tasks.manager.start(self._client_suspended(client))

    def on_stream_destroyed(self, account):
        self.logger.info("stream destroyed for account %r", account)

    def on_stopped(self, account, exc=None):
        self.logger.info("client stopped for account %r", account)
        client = self.clients.pop(account)
        account.client = None
        if exc is not None:
            self.logger.warning("client stopped with error, disabling account")
            self._accounts.set_account_enabled(account, False)
        self.on_client_stopped(account, client)

    def on_account_disabled(self, account: identity.Account):
        client = self.clients[account]
        client.presence = aioxmpp.PresenceState(False)

    @asyncio.coroutine
    def shutdown(self):
        futs = [asyncio.Future() for _ in self.clients]
        if not futs:
            # otherwise, wait complains down the road
            return

        for fut, client in zip(futs, self.clients.values()):
            client.on_stopped.connect(fut, client.on_stopped.AUTO_FUTURE)
            client.on_failure.connect(fut, client.on_failure.AUTO_FUTURE)
            client.stop()

        yield from asyncio.wait(futs, return_when=asyncio.ALL_COMPLETED)
