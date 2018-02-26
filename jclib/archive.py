import abc
import functools
import logging
import typing
import uuid

from datetime import datetime

import aioxmpp
import aioxmpp.callbacks
import aioxmpp.im.conversation

import jclib.client
import jclib.identity


MessageID = bytes


class AbstractArchiveTransaction(metaclass=abc.ABCMeta):
    @abc.abstractmethod
    def create_message(self, stanza) -> MessageID:
        pass

    @abc.abstractmethod
    def set_marker(self, stanza, conversation_jid, member_uid, message_id):
        pass

    @abc.abstractmethod
    def update_message(self, stanza, message_id: MessageID):
        pass

    @abc.abstractmethod
    def get_message(self, message_id: MessageID):
        pass

    @abc.abstractmethod
    def delete_messages(self,
                        conversation_jid,
                        message_ids: typing.Iterable[MessageID]):
        """
        Irreversibly delete these message IDs from the database.

        The messages are not deleted from disk storage until the transaction
        completes.

        The associated events are also deleted.
        """

    @abc.abstractmethod
    def find_messages(self,
                      *,
                      conversation_jid: typing.Optional[aioxmpp.JID] = None,
                      since_id: typing.Optional[MessageID] = None,
                      until_id: typing.Optional[MessageID] = None,
                      include_since: bool = False,
                      include_until: bool = True,
                      max_messages: int = None) -> typing.Iterable[MessageID]:
        pass

    @abc.abstractmethod
    def find_next(self,
                  timestamp: datetime,
                  conversation_jid: typing.Optional[aioxmpp.JID] = None,
                  ) -> typing.Optional[MessageID]:
        """
        Find the first message after the given timestamp.
        """

    @abc.abstractmethod
    def find_previous(self,
                      timestamp: datetime,
                      conversation_jid: typing.Optional[aioxmpp.JID] = None,
                      ) -> typing.Optional[MessageID]:
        """
        Find the last message before the given timestamp.
        """

    @abc.abstractmethod
    def __enter__(self):
        """
        Start transaction.
        """

    @abc.abstractmethod
    def __exit__(self, *exc_info):
        """
        End transaction.
        """


class AbstractArchive(metaclass=abc.ABCMeta):
    @abc.abstractmethod
    def transaction(self, allow_writes=False) -> AbstractArchiveTransaction:
        """
        Create a new transaction.
        """


class InMemoryArchive:
    pass


class AccountMessageReceiver:
    def __init__(
            self,
            account: jclib.identity.Account,
            main: "MessageManager"):
        super().__init__()
        self._account = account
        self._main = main
        self._client = None
        self.__tokens = []

    def __connect(self, signal, handler):
        self.__tokens.append(
            (signal, signal.connect(handler))
        )

    def __disconnect_all(self):
        for signal, token in self.__tokens:
            signal.disconnect(token)
        self.__tokens.clear()

    def prepare_client(self, client):
        conversation_svc = client.summon(
            aioxmpp.im.service.ConversationService
        )
        self.__connect(
            conversation_svc.on_message,
            functools.partial(
                self._main.handle_live_message,
                self._account.jid,
            )
        )
        self._client = client

    def shutdown_client(self, client):
        self.__disconnect_all()
        self._client = None


def get_member_display_name(
        member: aioxmpp.im.conversation.AbstractConversationMember):
    if hasattr(member, "nick"):  # XEP-0045
        return member.nick
    return str((member.direct_jid or member.conversation_jid).bare())


def get_member_colour_input(
        member: aioxmpp.im.conversation.AbstractConversationMember):
    if hasattr(member, "nick"):
        return member.nick
    if member.direct_jid:
        return str(member.direct_jid.bare())
    return member.conversation_jid


def get_member_from_jid(
        member: aioxmpp.im.conversation.AbstractConversationMember):
    if member.direct_jid:
        return member.direct_jid
    return member.conversation_jid


class InMemoryConversationState:
    def __init__(self):
        self.messages = []
        self.read_markers = {}
        self.unread_count = 0


class MessageManager:
    """
    Messages are either kept in-memory (if the conversations privacy settings
    require that) or stored on-disk (for all other conversations).

    .. signal:: on_message(conversation_jid, member, message, message_uid)

    .. signal:: on_message_correction(conversation_jid, message_uid, new_message)

    .. signal:: on_marker(conversation_jid, member, up_to_message_id, type_)

    .. signal:: on_flag(conversation_jid, member, message_id, type_)
    """

    on_message = aioxmpp.callbacks.Signal()
    on_marker = aioxmpp.callbacks.Signal()
    on_flag = aioxmpp.callbacks.Signal()
    on_message_correction = aioxmpp.callbacks.Signal()
    on_unread_count_changed = aioxmpp.callbacks.Signal()

    def __init__(self,
                 accounts: jclib.identity.Accounts,
                 client: jclib.client.Client):
        super().__init__()
        self.logger = logging.getLogger(
            ".".join([__name__, type(self).__qualname__])
        )
        self._accounts = accounts
        self._client = client
        self._client_svcs = {}

        self._client.on_client_prepare.connect(self._prepare_client)
        self._client.on_client_stopped.connect(self._shutdown_client)

        # (account_jid, conversation_jid) -> [message_uid]
        self._in_memory_archive_conv_index = {}
        # (account_jid, conversation_jid, message_id) -> message_uid
        self._in_memory_archive_message_id_index = {}
        self._in_memory_archive_data = {}

    def _prepare_client(self,
                        account: jclib.identity.Account,
                        client: jclib.client.Client):
        self.logger.debug(
            "preparing message receiver for client for account %s",
            account.jid,
        )
        receiver = AccountMessageReceiver(
            account,
            self,
        )
        self._client_svcs[client] = receiver
        receiver.prepare_client(client)

    def _shutdown_client(self,
                         account: jclib.identity.Account,
                         client: jclib.client.Client):
        receiver = self._client_svcs.pop(client)
        receiver.shutdown_client(client)

    def _autocreate_in_memory_conversation_state(
            self,
            account: aioxmpp.JID,
            conversation: aioxmpp.JID) -> InMemoryConversationState:
        key = account, conversation
        try:
            return self._in_memory_archive_conv_index[key]
        except KeyError:
            state = InMemoryConversationState()
            self._in_memory_archive_conv_index[key] = state
            return state

    def handle_live_message(
            self,
            account: aioxmpp.JID,
            conversation: aioxmpp.im.conversation.AbstractConversation,
            message: aioxmpp.Message,
            member: aioxmpp.im.conversation.AbstractConversationMember,
            source: aioxmpp.im.dispatcher.MessageSource,
            tracker: aioxmpp.tracking.MessageTracker = None,
            *,
            delay_timestamp: datetime = None,
            **kwargs
            ):
        self.logger.debug(
            "handling live message for %s: conversation=%s, message=%s",
            account, conversation.jid, message,
        )
        if hasattr(conversation, "muc_state"):
            self.logger.debug("conversation is in state %s",
                              conversation.muc_state)

        timestamp = delay_timestamp or datetime.utcnow()

        display_name = get_member_display_name(member)
        color_input = get_member_colour_input(member)
        from_jid = get_member_from_jid(member)

        if message.xep0333_marker is not None:
            marker = message.xep0333_marker
            self.logger.debug(
                "received %s marker for message id %s",
                marker.TAG,
                marker.id_,
            )

            if not isinstance(marker, aioxmpp.misc.DisplayedMarker):
                self.logger.debug(
                    "%s-type markers are not handled yet",
                    marker,
                )
                return

            try:
                marked_message_uid = self._in_memory_archive_message_id_index[
                    account, conversation.jid, marker.id_,
                ]
            except KeyError:
                self.logger.debug(
                    "we don’t know this message id :("
                )
                return

            self.logger.debug(
                "marking message_uid %s",
                marked_message_uid,
            )

            argv = (
                timestamp,
                member.is_self,
                from_jid,
                display_name,
                color_input,
                marked_message_uid,
            )

            state = self._autocreate_in_memory_conversation_state(
                account, conversation.jid
            )
            state.read_markers[account, conversation.jid] = argv

            if member.is_self:
                self.set_read_up_to(account.jid,
                                    conversation.jid,
                                    marked_message_uid)

            self.on_marker(
                account,
                conversation.jid,
                *argv,
            )

        elif message.body:
            message_uid = uuid.uuid4()

            argv = (
                timestamp,
                message_uid,
                member.is_self,
                from_jid,
                display_name,
                color_input,
                message,
            )

            self._in_memory_archive_data[message_uid] = argv

            self._in_memory_archive_message_id_index[
                # FIXME: prefer origin-id here
                account, conversation.jid, message.id_,
            ] = message_uid

            state = self._autocreate_in_memory_conversation_state(
                account, conversation.jid
            )
            state.messages.append(message_uid)
            old_unread_count = state.unread_count
            state.unread_count += 1

            self.on_message(
                account,
                conversation.jid,
                *argv
            )

            if old_unread_count != state.unread_count:
                self.on_unread_count_changed(
                    account,
                    conversation.jid,
                    state.unread_count,
                )

    def get_last_messages(
            self,
            account: aioxmpp.JID,
            conversation: aioxmpp.JID,
            max_count: int,
            min_age: typing.Optional[datetime] = None,
            max_age: typing.Optional[datetime] = None) -> typing.Iterable:
        self.logger.debug(
            "get_last_messages(%r, %r, max_count=%d, min_age=%r, max_age=%r)",
            account, conversation, max_count, min_age, max_age,
        )
        try:
            state = self._in_memory_archive_conv_index[account, conversation]
        except KeyError:
            self.logger.info(
                "nothing in archive for account=%r, conversation=%r",
                account, conversation,
            )
            return []

        max_count = max(0, max_count)

        for i, message_uid in enumerate(reversed(state.messages)):
            msg = self._in_memory_archive_data[message_uid]
            ts = msg[0]
            if max_count <= 0 and ts <= min_age:
                self.logger.debug("at limit already and %r <= %r",
                                  ts, min_age)
                break
            if ts < max_age:
                self.logger.debug("too old: %r < %r",
                                  ts, max_age)
                break
            max_count -= 1
        else:
            self.logger.debug("taking whole archive \o/; i = %r", i)
            i += 1
        assert 0 <= i <= len(state.messages)

        self.logger.debug("i=%d, range: %d:%d", i,
                          len(state.messages)-i,
                          len(state.messages))

        return [self._in_memory_archive_data[message_uid]
                for message_uid in state.messages[len(state.messages)-i:]]

    def get_unread_count(
            self,
            account: aioxmpp.JID,
            conversation: aioxmpp.JID):
        try:
            state = self._in_memory_archive_conv_index[account, conversation]
        except KeyError:
            self.logger.info(
                "nothing in archive for account=%r, conversation=%r",
                account, conversation,
            )
            return 0
        return state.unread_count

    def set_read_up_to(
            self,
            account: aioxmpp.JID,
            conversation: aioxmpp.JID,
            message_uid):
        try:
            state = self._in_memory_archive_conv_index[account, conversation]
        except KeyError:
            self.logger.info(
                "nothing in archive for account=%r, conversation=%r",
                account, conversation,
            )
            return

        old_unread_count = state.unread_count

        state.unread_count = min(
            state.unread_count,
            self.get_number_of_messages_since(account, conversation,
                                              message_uid)
        )

        if old_unread_count != state.unread_count:
            self.on_unread_count_changed(
                account,
                conversation,
                state.unread_count,
            )

    def get_number_of_messages_since(
            self,
            account: aioxmpp.JID,
            conversation: aioxmpp.JID,
            since_message_uid,
            max_count: int = 1000) -> int:
        self.logger.debug(
            "get_number_of_messages_since(%r, %r, %r, max_count=%d)",
            account, conversation, since_message_uid, max_count
        )
        try:
            state = self._in_memory_archive_conv_index[account, conversation]
        except KeyError:
            self.logger.info(
                "nothing in archive for account=%r, conversation=%r",
                account, conversation,
            )
            return 0

        for i, message_uid in enumerate(reversed(state.messages)):
            if message_uid == since_message_uid:
                return i
            if i >= max_count - 1:
                return i

        return i
