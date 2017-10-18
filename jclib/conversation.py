import abc
import asyncio
import functools
import typing

import aioxmpp.callbacks
import aioxmpp.muc
import aioxmpp.im.conversation
import aioxmpp.im.service

import jclib.client
import jclib.identity
import jclib.instrumentable_list
import jclib.tasks


def _connect_and_store_token(tokens, signal, handler):
    tokens.append(
        (signal, signal.connect(handler))
    )


class ConversationNode(metaclass=abc.ABCMeta):
    on_ready = aioxmpp.callbacks.Signal()
    on_stale = aioxmpp.callbacks.Signal()

    def __init__(self,
                 account: jclib.identity.Account,
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

    @classmethod
    def for_conversation(
            cls,
            account: jclib.identity.Account,
            conversation: aioxmpp.im.conversation.AbstractConversation):
        """
        Create a conversation node for the given :mod:`aioxmpp` conversation
        object.

        :raises TypeError: if the class of `conversation` is not supported.
        """
        if isinstance(conversation, aioxmpp.im.p2p.Conversation):
            return P2PConversationNode(account, conversation.jid,
                                       conversation=conversation)
        if isinstance(conversation, aioxmpp.muc.Room):
            return MUCConversationNode(account, conversation.jid,
                                       None,
                                       conversation=conversation)
        raise TypeError("unknown conversation class: {!r}".format(
            conversation
        ))


class P2PConversationNode(ConversationNode):
    def __init__(self,
                 account: jclib.identity.Account,
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
                 account: jclib.identity.Account,
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


class ConversationManager(jclib.instrumentable_list.ModelListView):
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

       The :class:`jclib.instrumentable_list.ModelTree` holding the identities
       and their conversations.

    """

    on_conversation_added = aioxmpp.callbacks.Signal()

    def __init__(self,
                 accounts: jclib.identity.Accounts,
                 client: jclib.client.Client, **kwargs):
        super().__init__(jclib.instrumentable_list.ModelList(), **kwargs)

        client.on_client_prepare.connect(
            self.handle_client_prepare,
        )
        client.on_client_stopped.connect(
            self.handle_client_stopped,
        )

        self.client = client

        self.__clientmap = {}
        self.__convaddrmap = {}

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

        self.__clientmap[client] = (account, tokens)

    def handle_client_stopped(self, account, client):
        """
        Must be called after a client registered with prepare was stopped.
        """
        _, tokens = self.__clientmap.pop(client)
        for signal, token in tokens:
            signal.disconnect(token)

    def _spontaneous_p2p_conversation(
            self,
            account: jclib.identity.Account,
            conversation: aioxmpp.im.p2p.Conversation):
        wrapper = P2PConversationNode(account,
                                      conversation.jid,
                                      conversation=conversation)
        self._backend.append(wrapper)
        self.on_conversation_added(wrapper)
        self.__convaddrmap[account, conversation.jid] = wrapper

    def _require_conversation(self, conv):
        jclib.tasks.manager.update_text(
            "Starting {}".format(conv.label)
        )
        yield from conv.require_conversation()

    @asyncio.coroutine
    def _join_conversation(self, conv):
        jclib.tasks.manager.update_text(
            "Starting {}".format(conv.label),
        )
        yield from aioxmpp.callbacks.first_signal(
            conv.on_enter,
            conv.on_failure,
        )

    def start_soon(self, conv):
        if conv.conversation is None:
            jclib.tasks.manager.start(self._require_conversation(conv))

    def adopt_conversation(self, account, conversation):
        key = account, conversation.jid
        try:
            node = self.__convaddrmap[key]
        except KeyError:
            node = ConversationNode.for_conversation(account, conversation)
            self._backend.append(node)
            self.on_conversation_added(node)
            jclib.tasks.manager.start(self._join_conversation(conversation))
            self.__convaddrmap[key] = node
        return node

    def open_muc_conversation(self,
                              account: jclib.identity.Account,
                              address: aioxmpp.JID,
                              nick: str,
                              password: typing.Optional[str]=None):
        muc_client = self.client.client_by_account(account).summon(
            aioxmpp.MUCClient
        )

        room, _ = muc_client.join(address, nick, password=password)
        self.adopt_conversation(account, room)
