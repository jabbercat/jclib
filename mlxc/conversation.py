import asyncio
import functools

import aioxmpp.callbacks
import aioxmpp.im.service

import mlxc.instrumentable_list


def _connect_and_store_token(tokens, signal, handler):
    tokens.append(
        (signal, signal.connect(handler))
    )


class ConversationNode(mlxc.instrumentable_list.ModelTreeNodeHolder):
    def __init__(self, node, conversation):
        super().__init__()
        self.children = node
        self.children.object_ = self
        self.conversation = conversation

    @property
    def _node(self):
        return self.children


class ConversationIdentity(mlxc.instrumentable_list.ModelTreeNodeHolder):
    def __init__(self, node, identity):
        super().__init__()
        self.identity = identity
        self.conversations = node
        self.conversations.object_ = self

    @property
    def _node(self):
        return self.conversations


class ConversationManager:
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

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.tree = mlxc.instrumentable_list.ModelTree()

        self.__identitymap = {}
        self.__clientmap = {}

    def handle_identity_added(self, identity):
        """
        Must be called when a new identity is added.
        """
        node = mlxc.instrumentable_list.ModelTreeNode(self.tree)
        wrapper = ConversationIdentity(node, identity)
        self.__identitymap[identity] = wrapper
        self.tree.root.append(wrapper)

    def handle_identity_removed(self, identity):
        """
        Must be called when an identity is removed.
        """
        wrapper = self.__identitymap[identity]
        self.tree.root.remove(wrapper)

    def handle_client_prepare(self, account, client):
        """
        Must be called during client prepare for each client to track.
        """
        identity = account.parent.object_
        convs = client.summon(aioxmpp.im.service.ConversationService)
        tokens = []
        _connect_and_store_token(
            tokens,
            convs.on_conversation_added,
            functools.partial(
                self._conversation_added,
                identity,
            )
        )
        self.__clientmap[client] = (account, identity, tokens)

    def handle_client_stopped(self, account, client):
        """
        Must be called after a client registered with prepare was stopped.
        """
        _, _, tokens = self.__clientmap.pop(client)
        for signal, token in tokens:
            signal.disconnect(token)

    def _conversation_added(self, identity, conversation):
        parent = self.__identitymap[identity]
        node = mlxc.instrumentable_list.ModelTreeNode(self.tree)
        wrapper = ConversationNode(node, conversation)
        parent.conversations.append(wrapper)
        self.on_conversation_added(wrapper)

    @asyncio.coroutine
    def start_onetoone_conversation(self, client, peer_jid):
        """
        Start a new conversation with a peer using a client.

        :param client: Connected client.
        :type client: :class:`aioxmpp.Client`
        :param peer_jid: Bare JID of the peer to converse with.
        :type peer_jid: :class:`aioxmpp.JID`
        :return: The conversation node in the tree.
        :rtype: :class:`ConversationNode`
        """
