import asyncio
import logging

import asyncio_xmpp.node
import asyncio_xmpp.security_layer

logger = logging.getLogger(__name__)

class Client:
    @classmethod
    def account_manager_factory(cls):
        import mlxc.account
        return mlxc.account.AccountManager()

    def __init__(self):
        self.accounts = self.account_manager_factory()
        self.nodes = {}

    @asyncio.coroutine
    def set_global_presence(self, type_, additional_tag):
        if type_ == "unavailable":
            yield from self._go_offline()
        elif type_ is None:
            yield from self._go_online()

    def _auto_node(self, jid):
        try:
            return self.nodes[jid]
        except KeyError:
            self.nodes[jid] = asyncio_xmpp.node.Client(
                jid,
                asyncio_xmpp.security_layer.tls_with_password_based_authentication(
                    self.accounts.password_provider,
                    certificate_verifier_factory=asyncio_xmpp.security_layer._NullVerifier)
            )
            return self._auto_node(jid)

    def _connection_task_terminated(self, task):
        try:
            logger.warning("connection task terminated: %s",
                        task.result())
        except asyncio.CancelledError:
            pass
        except:
            logger.exception("connection task terminated:",)

    @asyncio.coroutine
    def _go_online(self):
        futuremap = {}
        for account in self.accounts:
            node = self._auto_node(account.jid)
            future = asyncio.async(node.connect())
            futuremap[future] = node

        if not futuremap:
            return

        done, pending = yield from asyncio.wait(futuremap.keys())
        for future in done:
            try:
                future.result()
            except:
                logger.exception("a connection failed to establish:")
                continue
            node = futuremap[future]
            # send initial presence
            node.enqueue_stanza(node.make_presence())
            task = asyncio.async(node.stay_connected())
            task.add_done_callback(self._connection_task_terminated)

    @asyncio.coroutine
    def _go_offline(self):
        futures = []
        for node in self.nodes.values():
            futures.append(asyncio.async(node.disconnect()))
        self.nodes.clear()
        if not futures:
            return
        yield from asyncio.wait(futures)
