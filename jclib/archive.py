import abc
import functools
import logging
import typing

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

        # (account_jid, conversation_jid) -> [(timestamp, member, message)]
        self._in_memory_archive = {}

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

    def _get_display_name(
            self,
            member: aioxmpp.im.conversation.AbstractConversationMember) -> str:
        if hasattr(member, "nick"):  # XEP-0045
            return member.nick
        return (member.direct_jid or member.conversation_jid).bare()

    def handle_live_message(
            self,
            account: aioxmpp.JID,
            conversation: aioxmpp.JID,
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
            account, conversation, message,
        )

        timestamp = delay_timestamp or datetime.utcnow()

        display_name = self._get_display_name(member)

        is_self = False
        from_jid = None
        if member is not None:
            if member.direct_jid:
                from_jid = member.direct_jid.bare()
            else:
                from_jid = member.conversation_jid
            color_input = str(
                (member.direct_jid or member.conversation_jid).bare()
            )
            if member.is_self:
                from_ = "me"
                is_self = True
            else:
                from_ = str(
                    (member.direct_jid or member.conversation_jid).bare()
                )

            if hasattr(member, "nick"):
                from_ = member.nick
                color_input = member.nick

        else:
            from_ = str(message.from_)
            color_input = None

        argv = (
            timestamp,
            is_self,
            from_jid,
            from_,
            color_input,
            message.body.any()
        )

        data = self._in_memory_archive.setdefault((account, conversation), [])
        data.append(argv)

        self.on_message(
            account,
            conversation,
            *argv
        )

    def get_last_messages(
            self,
            account: aioxmpp.JID,
            conversation: aioxmpp.JID,
            max_count: int,
            min_age: typing.Optional[datetime] = None,
            max_age: typing.Optional[datetime] = None) -> typing.Iterable:
        try:
            data = self._in_memory_archive[account, conversation]
        except KeyError:
            return

        max_count = max(0, max_count)

        for i, msg in enumerate(reversed(data)):
            ts = msg[0]
            if max_count <= 0 and ts <= min_age:
                break
            if ts > max_age:
                break
        else:
            i += 1
        assert 0 <= i <= len(data)

        return data[len(data)-i:]
