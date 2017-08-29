# battle plan:
# 1. we have a per-account roster thing, which merges storage layer roster and
#    online client roster (including presence) into one interface
# 2. we have a unified roster thing which combines bookmarks and per-account
#    roster things into one interface

# notes:
# - we might want to be able to access the conversation from an
#   AbstractRosterItem to obtain information about it e.g. number of unread
#   messages, participants, ...
# - tricky cases: a conversation node for an address exists, and then a roster
#   item is added (e.g. a bookmark or a contact)

import abc
import asyncio
import typing

from datetime import datetime

import aioxmpp.callbacks

import mlxc.client
import mlxc.conversation
import mlxc.identity
import mlxc.instrumentable_list
import mlxc.storage
import mlxc.xso


class AbstractRosterItem(metaclass=abc.ABCMeta):
    def __init__(self,
                 account: mlxc.identity.Account,
                 address: aioxmpp.JID,
                 *,
                 conversation_node:
                     typing.Optional[mlxc.conversation.ConversationNode]=None):
        super().__init__()
        self._account = account
        self._address = address
        self._conversation_node = conversation_node

    @property
    def address(self) -> aioxmpp.JID:
        return self._address

    @property
    def account(self) -> mlxc.identity.Account:
        return self._account

    # these do not belong in the roster, these belong into conversation nodes
    # persistence needs to be figured out
    #
    # @property
    # def pinned(self) -> bool:
    #     """
    #     A flag indicating whether a roster item is pinned.
    #
    #     A pinned roster item is always shown in the conversation list, even if
    #     no conversation is currently active.
    #     """
    #
    # @property
    # def closed(self) -> typing.Optional[datetime]:
    #     """
    #     Timestamp of the last closing of a conversation with the roster item.
    #
    #     Non-pinned roster items are only shown in the conversation list if
    #
    #     * they have not been closed and the last message is newer than a
    #       configurable threshold ("recent conversations"), or
    #     * they have been closed and the last message is newer than the closure
    #       and newer than the configurable threshold
    #     """

    @abc.abstractproperty
    def label(self) -> str:
        """
        The primary label of the item.

        The primary label must always be a non-empty string. It usually
        defaults to the :attr:`address` of the item.
        """

    @abc.abstractproperty
    def tags(self) -> typing.Iterable[str]:
        """
        Tags associated with the item.

        These tags must include the account tag, but no other dynamic tags.
        """

    @abc.abstractmethod
    def create_conversation(self, client: aioxmpp.Client):
        """
        Create a new conversation for this roster node.

        This uses the appropriate conversation service with `client` to create
        a new conversation.

        The conversation is not entered yet, so that events can be bound before
        the operation completes.
        """

    @property
    def conversation_address(self):
        """
        Conversation address of this roster item.

        This is usually equivalent to the item address.
        """
        return self.address


class ContactRosterItem(AbstractRosterItem):
    def __init__(self,
                 account: mlxc.identity.Account,
                 address: aioxmpp.JID,
                 label: typing.Optional[str]=None,
                 subscription: str='none',
                 tags: typing.Iterable[str]=None,
                 approved: bool=False,
                 ask: bool=False,
                 **kwargs):
        super().__init__(account, address, **kwargs)
        self._label = label
        self._subscription = subscription
        self._approved = approved
        self._ask = ask
        self._tags = set(tags or [])

    @property
    def label(self) -> str:
        return self._label or str(self._address)

    @property
    def tags(self) -> typing.Iterable[str]:
        return self._tags

    @property
    def presence(self) -> typing.Mapping[str, aioxmpp.PresenceState]:
        return {}

    @property
    def subscription(self) -> str:
        return self._subscription

    @property
    def approved(self) -> bool:
        return self._approved

    @property
    def ask(self) -> bool:
        return self._ask

    @classmethod
    def wrap(cls, account, upstream_item):
        return cls(
            account,
            upstream_item.jid,
            label=upstream_item.name,
            subscription=upstream_item.subscription,
            tags=upstream_item.groups,
            approved=upstream_item.approved,
            ask=upstream_item.ask,
        )

    @classmethod
    def from_xso(cls, account, obj):
        return cls(
            account,
            obj.address,
            label=obj.label,
            subscription=obj.subscription,
            tags=obj.tags,
            approved=obj.approved,
            ask=obj.ask,
        )

    def to_xso(self):
        obj = mlxc.xso.RosterContact()
        obj.address = self._address
        obj.label = self._label
        obj.subscription = self._subscription
        obj.ask = self._ask
        obj.approved = self._approved
        obj.tags.update(self._tags)
        return obj

    def update(self, upstream_item: aioxmpp.roster.Item):
        self._label = upstream_item.name
        self._tags = set(upstream_item.groups)
        self._subscription = upstream_item.subscription
        self._approved = upstream_item.approved
        self._ask = upstream_item.ask

    def create_conversation(
            self,
            client: aioxmpp.Client) -> aioxmpp.im.p2p.Conversation:
        svc = client.summon(aioxmpp.im.p2p.Service)
        return svc.get_conversation(self.address)


def contacts_to_json(contacts, ver=None):
    def contact_to_json(contact):
        result = {
            "subscription": contact.subscription
        }

        if contact.ask is not None:
            result["ask"] = contact.ask

        if contact.approved:
            result["approved"] = contact.approved

        if contact._label:
            result["name"] = contact.label

        tags = sorted(contact.tags)
        if tags:
            result["groups"] = tags

        return result

    return {
        "ver": ver,
        "items": {
            str(contact.address): contact_to_json(contact)
            for contact in contacts
        }
    }


class MUCRosterItem(AbstractRosterItem):
    def __init__(self,
                 account: mlxc.identity.Account,
                 address: aioxmpp.JID,
                 label: typing.Optional[str]=None,
                 nick: typing.Optional[str]=None,
                 password: typing.Optional[str]=None,
                 autojoin: bool=False,
                 **kwargs):
        super().__init__(account, address, **kwargs)
        self._label = label
        self._autojoin = autojoin
        self._nick = nick
        self._password = password

    @property
    def subject(self) -> typing.Optional[str]:
        # FIXME: access the subject from the conversation if possible
        return None

    @property
    def label(self) -> str:
        return self._label or self.subject or str(self.address)

    @property
    def tags(self) -> typing.Iterable[str]:
        return []

    @property
    def autojoin(self) -> bool:
        return self._autojoin

    @property
    def nick(self) -> typing.Optional[str]:
        return self._nick

    @property
    def password(self) -> typing.Optional[str]:
        return self._password

    def create_conversation(self, client: aioxmpp.Client):
        svc = client.summon(aioxmpp.MUCClient)
        return svc.join(self.address, self.nick or self._account.jid.localpart,
                        password=self.password)[0]

    @classmethod
    def wrap(cls,
             account: mlxc.identity.Account,
             obj: aioxmpp.bookmarks.xso.Conference):
        return cls(
            account,
            obj.jid,
            nick=obj.nick,
            password=obj.password,
            autojoin=obj.autojoin,
        )


class AbstractRosterService(
        mlxc.instrumentable_list.ModelListView[AbstractRosterItem]):
    """
    Abstract service providing roster items.

    It does not provide direct access to the items; items can only be obtained
    by observing the corresponding signals.

    .. signal:: on_item_added(item)

        Emits when a new item was added to the roster.

    .. signal:: on_item_changed(item)

        Emits when a roster item has changed.

    .. signal:: on_item_removed(item)

        Emits when a roster item has been removed.

    .. signal:: on_tag_added(tag)

        Emits when a tag is used for the first time on a roster item.

    .. signal:: on_tag_removed(tag)

        Emits when the last usage of a tag is removed.

    .. automethod:: prepare_client

    .. automethod:: shutdown_client

    .. automethod:: load

    .. automethod:: save

    .. autoattribute:: is_writable

    .. autoattribute:: account

    """

    def __init__(self,
                 account: mlxc.identity.Account,
                 writeman: mlxc.storage.WriteManager):
        super().__init__(mlxc.instrumentable_list.ModelList())
        self._writeman = writeman
        self._writeman.on_writeback.connect(
            self.save,
            self._writeman.on_writeback.WEAK,
        )
        self._account = account

    @property
    def account(self):
        return self._account

    @abc.abstractmethod
    def prepare_client(self, client: aioxmpp.Client):
        """
        Prepare the roster service for a client.

        :raises RuntimeError: if called while already prepared for a client.
        """

    @abc.abstractmethod
    def shutdown_client(self, client: aioxmpp.Client):
        """
        Shut down the connection of the roster service to the client.

        :raises RuntimeError: if called before :meth:`prepare_client` or before
        :meth:`shutdown_client`.
        """

    @abc.abstractmethod
    def load(self):
        """
        Load the cached roster items from persistent storage.

        :raises RuntimeError: if called when there are already roster items in
            the in-memory storage.
        :raises RuntimeError: if called while :attr:`is_writable` is
            :data:`True`.
        """

    @abc.abstractmethod
    def save(self):
        """
        Save the roster items to persistent cache storage.
        """

    @abc.abstractproperty
    def is_writable(self):
        """
        Return :data:`True` if the roster is writable and :data:`False`
        otherwise.

        .. note::

            This flag may change at any time due to network circumstances. It
            should not be cached and it being true is no guarantee that
            any write operations will succeed.
        """

    @abc.abstractmethod
    @asyncio.coroutine
    def set_label(self, item: AbstractRosterItem, new_label: str):
        """
        Change the label of a roster item.

        :raises RuntimeError: if called while the roster is not writable.
        """

    @abc.abstractmethod
    @asyncio.coroutine
    def update_tags(self,
                    item: AbstractRosterItem,
                    add_tags: typing.Iterable[str]=[],
                    remove_tags: typing.Iterable[str]=[]):
        """
        Add and remove tags to a roster item.

        :raises RuntimeError: if called while the roster is not writable.
        """


class ContactRosterService(AbstractRosterService):
    def __init__(self,
                 account: mlxc.identity.Account,
                 writeman: mlxc.storage.WriteManager):
        super().__init__(account, writeman)
        self.__tokens = []
        self.__addrmap = {}
        self._client = None
        self._dirty = False

    def __connect(self, signal, handler):
        self.__tokens.append(
            (signal, signal.connect(handler))
        )

    def __disconnect_all(self):
        for signal, token in self.__tokens:
            signal.disconnect(token)
        self.__tokens.clear()

    def prepare_client(self, client: aioxmpp.Client):
        roster = client.summon(aioxmpp.RosterClient)
        self.__connect(roster.on_entry_added, self._on_entry_added)
        self.__connect(roster.on_entry_removed, self._on_entry_removed)
        self.__connect(roster.on_entry_name_changed, self._on_entry_changed)
        self.__connect(roster.on_entry_subscription_state_changed,
                       self._on_entry_changed)
        self._client = client

    def shutdown_client(self, client: aioxmpp.Client):
        self.__disconnect_all()
        self._client = None

    def update_tags(self, item, add_tags, remove_tags):
        raise NotImplementedError()

    def set_label(self, item, new_label):
        raise NotImplementedError()

    @property
    def is_writable(self):
        return self._client is not None

    def load(self):
        if self._client is not None:
            raise RuntimeError(
                "load cannot be called after a client has been prepared"
            )

        if self._backend:
            raise RuntimeError(
                "load cannot be called when there are already contacts loaded"
            )

        contacts = mlxc.storage.xml.get_all(
            mlxc.storage.StorageType.CACHE,
            mlxc.storage.AccountLevel(self.account.jid),
            mlxc.xso.RosterContact,
        )
        self._backend.extend(
            ContactRosterItem.from_xso(self._account, obj)
            for obj in contacts
        )

    def save(self):
        if not self._dirty:
            return

        items = [
            contact.to_xso()
            for contact in self
        ]
        mlxc.storage.xml.put(
            mlxc.storage.StorageType.CACHE,
            mlxc.storage.AccountLevel(self.account.jid),
            items,
        )

        self._dirty = False

    def _on_entry_added(self, item):
        wrapped = ContactRosterItem.wrap(self._account, item)
        self.__addrmap[wrapped.address] = wrapped
        self._backend.append(wrapped)
        self._dirty = True
        self._writeman.request_writeback()

    def _on_entry_removed(self, item):
        wrapped = self.__addrmap.pop(item.jid)
        self._backend.remove(wrapped)
        self._dirty = True
        self._writeman.request_writeback()

    def _on_entry_changed(self, item):
        wrapped = self.__addrmap[item.jid]
        wrapped.update(item)
        index = self._backend.index(wrapped)
        self._backend.refresh_data(slice(index, index + 1), None, None)
        self._dirty = True
        self._writeman.request_writeback()


class ConferenceBookmarkService(AbstractRosterService):
    def __init__(self,
                 account: mlxc.identity.Account,
                 writeman: mlxc.storage.WriteManager):
        super().__init__(account, writeman)
        self.__tokens = []
        self.__addrmap = {}
        self._client = None

    def __connect(self, signal, handler):
        self.__tokens.append(
            (signal, signal.connect(handler))
        )

    def __disconnect_all(self):
        for signal, token in self.__tokens:
            signal.disconnect(token)
        self.__tokens.clear()

    @property
    def is_writable(self):
        return self._client is not None

    def update_tags(self, item, add_tags, remove_tags):
        raise NotImplementedError()

    def set_label(self, item, new_label):
        raise NotImplementedError()

    def prepare_client(self, client):
        bookmarks_svc = client.summon(aioxmpp.BookmarkClient)
        self.__connect(bookmarks_svc.on_bookmark_added,
                       self._on_bookmark_added)
        self.__connect(bookmarks_svc.on_bookmark_removed,
                       self._on_bookmark_removed)
        self.__connect(bookmarks_svc.on_bookmark_changed,
                       self._on_bookmark_changed)
        self._client = client

    def shutdown_client(self, client):
        self.__disconnect_all()
        self._client = None

    def load(self):
        pass

    def save(self):
        pass

    def _on_bookmark_added(self, bookmark):
        item = MUCRosterItem.wrap(self._account, bookmark)
        self.__addrmap[item.address] = item
        self._backend.append(item)
        self._writeman.request_writeback()

    def _on_bookmark_removed(self, bookmark):
        item = self.__addrmap.pop(bookmark.jid)
        self._backend.remove(item)
        self._writeman.request_writeback()

    def _on_bookmark_changed(self, old_bookmark, new_bookmark):
        pass


class RosterManager:
    def __init__(self,
                 accounts: mlxc.identity.Accounts,
                 client: mlxc.client.Client,
                 writeman: mlxc.storage.WriteManager):
        super().__init__()
        self._items = mlxc.instrumentable_list.JoinedModelListView()
        self._items_view = mlxc.instrumentable_list.ModelListView(
            self._items
        )
        self._accounts = accounts
        self._client = client
        self._writeman = writeman
        self._account_objects = {}

        self._client.on_client_prepare.connect(self._prepare_client)
        self._client.on_client_stopped.connect(self._shutdown_client)

        self._client_svc_map = {}

    def _prepare_client(self,
                        account: mlxc.identity.Account,
                        client: mlxc.client.Client):
        svcs = []
        self._client_svc_map[client] = svcs
        for class_ in [ContactRosterService, ConferenceBookmarkService]:
            instance = class_(account, self._writeman)
            instance.load()
            instance.prepare_client(client)
            self._items.append_source(instance)
            svcs.append(instance)

    def _shutdown_client(self,
                         account: mlxc.identity.Account,
                         client: mlxc.client.Client):
        svcs = self._client_svc_map.pop(client)
        for svc in svcs:
            svc.shutdown_client(client)
            self._items.remove_source(svc)

    @property
    def items(self) -> \
            mlxc.instrumentable_list.AbstractModelListView[AbstractRosterItem]:
        return self._items_view


mlxc.storage.xml.register(
    mlxc.storage.StorageLevel.ACCOUNT,
    mlxc.xso.RosterContact,
)
