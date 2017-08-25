import abc
import asyncio
import functools
import typing

import aioxmpp.callbacks
import aioxmpp.muc
import aioxmpp.im.conversation
import aioxmpp.im.service

import mlxc.client
import mlxc.identity
import mlxc.instrumentable_list
import mlxc.tasks


def _connect_and_store_token(tokens, signal, handler):
    tokens.append(
        (signal, signal.connect(handler))
    )


class ConversationNode(metaclass=abc.ABCMeta):
    on_ready = aioxmpp.callbacks.Signal()
    on_stale = aioxmpp.callbacks.Signal()

    def __init__(self,
                 account: mlxc.identity.Account,
                 *,
                 conversation: typing.Optional[
                     aioxmpp.im.conversation.AbstractConversation]=None):
        super().__init__()
        self.account = account
        self.conversation = conversation

    @property
    def _node(self):
        return self.children

    @abc.abstractmethod
    @asyncio.coroutine
    def _start_conversation(
            self,
            client: aioxmpp.Client) \
            -> aioxmpp.im.conversation.AbstractConversation:
        """
        Start the aioxmpp conversation for this node.

        This is only called by the :meth:`require_conversation` iff the client
        is online and no conversation is currently associated.
        """

    @asyncio.coroutine
    def require_conversation(
            self) -> aioxmpp.im.conversation.AbstractConversation:
        client = self.account.client
        if client is None:
            if self.conversation is not None:
                self.conversation = None
                self.on_stale()
            raise ConnectionError("account {} is not connected".format(
                self.account
            ))

        if self.conversation is None:
            self.conversation = (yield from self._start_conversation(client))
            self.on_ready()

        return self.conversation

    @abc.abstractproperty
    def label(self) -> str:
        """
        Label of the conversation.
        """


class P2PConversationNode(ConversationNode):
    def __init__(self,
                 account: mlxc.identity.Account,
                 peer_jid: aioxmpp.JID,
                 *,
                 conversation: typing.Optional[
                     aioxmpp.im.conversation.AbstractConversation]=None):
        super().__init__(account, conversation=conversation)
        self.peer_jid = peer_jid

    @property
    def label(self) -> str:
        return str(self.peer_jid)

    @asyncio.coroutine
    def _start_conversation(
            self,
            client: aioxmpp.Client) -> aioxmpp.im.p2p.Conversation:
        p2p_svc = client.summon(aioxmpp.im.p2p.Service)
        return (yield from p2p_svc.get_conversation(self.peer_jid))


class MUCConversationNode(ConversationNode):
    def __init__(self,
                 account: mlxc.identity.Account,
                 muc_jid: aioxmpp.JID,
                 nickname: str,
                 *,
                 conversation: typing.Optional[
                     aioxmpp.im.conversation.AbstractConversation]=None):
        super().__init__(account, conversation=conversation)
        self.muc_jid = muc_jid
        self.nickname = nickname

    @property
    def label(self):
        return str(self.muc_jid)

    @asyncio.coroutine
    def _start_conversation(
            self,
            client) -> aioxmpp.muc.Room:
        muc_svc = client.summon(aioxmpp.MUCClient)
        room, _ = muc_svc.join(self.muc_jid, self.nickname)
        return room


class ConversationManager(mlxc.instrumentable_list.ModelListView):
    """
    Manage the tree holding the conversations.

    There is a first level node for each identity. Below those, there are nodes
    for each conversation in which an account in those identities participates.

    It serves as a combination of the
    :class:`aioxmpp.im.service.ConversationService` services of each client.

    .. signal:: on_conversation_added(wrapper)

       A new conversation was added.

       :param wrapper: The tree node for the conversation.
       :type wrapper: :class:`ConversationNode`

    .. attribute:: tree

       The :class:`mlxc.instrumentable_list.ModelTree` holding the identities
       and their conversations.

    """

    on_conversation_added = aioxmpp.callbacks.Signal()

    def __init__(self,
                 accounts: mlxc.identity.Accounts,
                 client: mlxc.client.Client, **kwargs):
        super().__init__(mlxc.instrumentable_list.ModelList(), **kwargs)

        client.on_client_prepare.connect(
            self.handle_client_prepare,
        )
        client.on_client_stopped.connect(
            self.handle_client_stopped,
        )

        self.__clientmap = {}

    def handle_client_prepare(self, account, client):
        """
        Must be called during client prepare for each client to track.
        """
        p2p_svc = client.summon(aioxmpp.im.p2p.Service)
        tokens = []
        _connect_and_store_token(
            tokens,
            p2p_svc.on_spontaneous_conversation,
            functools.partial(
                self._spontaneous_p2p_conversation,
                account,
            )
        )

        bookmark_svc = client.summon(aioxmpp.BookmarkClient)
        _connect_and_store_token(
            tokens,
            bookmark_svc.on_bookmark_added,
            functools.partial(
                self._bookmark_added,
                account,
            )
        )

        _connect_and_store_token(
            tokens,
            bookmark_svc.on_bookmark_changed,
            functools.partial(
                self._bookmark_changed,
                account,
            )
        )

        _connect_and_store_token(
            tokens,
            bookmark_svc.on_bookmark_removed,
            functools.partial(
                self._bookmark_removed,
                account,
            )
        )

        self.__clientmap[client] = (account, tokens)

    def handle_client_stopped(self, account, client):
        """
        Must be called after a client registered with prepare was stopped.
        """
        _, tokens = self.__clientmap.pop(client)
        for signal, token in tokens:
            signal.disconnect(token)

    def _bookmark_added(
            self,
            account: mlxc.identity.Account,
            bookmark: aioxmpp.xso.XSO):
        if not isinstance(bookmark, aioxmpp.bookmarks.Conference):
            return
        self.open_muc_conversation(
            account,
            bookmark.jid,
            bookmark.nick,
            autostart=bookmark.autojoin,
        )

    def _bookmark_changed(
            self,
            account: mlxc.identity.Account,
            old_bookmark: aioxmpp.xso.XSO,
            new_bookmark: aioxmpp.xso.XSO):
        if not isinstance(old_bookmark, aioxmpp.bookmarks.Conference):
            return

    def _bookmark_removed(
            self,
            account: mlxc.identity.Account,
            bookmark: aioxmpp.xso.XSO):
        if not isinstance(bookmark, aioxmpp.bookmarks.Conference):
            return

    def _spontaneous_p2p_conversation(
            self,
            account: mlxc.identity.Account,
            conversation: aioxmpp.im.p2p.Conversation):
        wrapper = P2PConversationNode(account,
                                      conversation.jid,
                                      conversation=conversation)
        self._backend.append(wrapper)
        self.on_conversation_added(wrapper)

    def _require_conversation(self, conv):
        mlxc.tasks.manager.update_text(
            "Starting {}".format(conv.label)
        )
        yield from conv.require_conversation()

    def start_soon(self, conv):
        if conv.conversation is None:
            mlxc.tasks.manager.start(self._require_conversation(conv))

    def open_onetoone_conversation(self, account, peer_jid, *,
                                   autostart=True):
        wrapper = P2PConversationNode(account, peer_jid)
        self._backend.append(wrapper)
        self.on_conversation_added(wrapper)

        if autostart:
            self.start_soon(wrapper)

    def open_muc_conversation(self, account, muc_jid, nickname, *,
                              autostart=True):
        wrapper = MUCConversationNode(account, muc_jid, nickname)
        self._backend.append(wrapper)
        self.on_conversation_added(wrapper)

        if autostart:
            self.start_soon(wrapper)
