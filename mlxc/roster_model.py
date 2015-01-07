import abc
import asyncio
import collections
import collections.abc
import contextlib
import functools
import logging
import weakref

from enum import Enum

import asyncio_xmpp.jid
import asyncio_xmpp.presence

from . import events

from .utils import *

logger = logging.getLogger(__name__)

GROUP_TAG = "{{{}}}group".format(mlxc_namespaces.roster)
CONTACT_TAG = "{{{}}}contact".format(mlxc_namespaces.roster)
VIA_TAG = "{{{}}}via".format(mlxc_namespaces.roster)

class RosterAccountEventType(Enum):
    #: set all presences of this account to unavailable and hide the roster
    #: entries
    UNAVAILABLE = 0

    #: re-show the roster entries of the account
    AVAILABLE = 1

class RosterViaEventType(Enum):
    PRESENCE_CHANGED = 0
    LABEL_CHANGED = 1

class RosterAccountEvent(events.Event):
    def __init__(self, type_, account_jid):
        super().__init__(RosterAccountEventType(type_))
        self.account_jid = account_jid

class RosterViaEvent(events.Event):
    def __init__(self, type_, account_jid, peer_jid):
        super().__init__(RosterViaEventType(type_))
        self.account_jid = account_jid
        self.peer_jid = peer_jid

class RosterViaPresenceChanged(RosterViaEvent):
    def __init__(self, account_jid, peer_jid, new_presence,
                 resources={None}):
        super().__init__(
            RosterViaEventType.PRESENCE_CHANGED,
            account_jid, peer_jid)
        self.new_presence = new_presence
        self.resources = resources

class RosterViaLabelChanged(RosterViaEvent):
    def __init__(self, account_jid, peer_jid, new_label):
        super().__init__(
            RosterViaEventType.LABEL_CHANGED,
            account_jid, peer_jid)
        self.new_label = new_label

class RosterNode(events.EventHandler):
    def __init__(self, *, root=None, parent=None):
        super().__init__()
        if parent is not None:
            if root is not None:
                if root is not parent.get_root():
                    raise ValueError("parent root and argument root conflict")
            root = parent.get_root()

        if root is None:
            raise ValueError("root must not be None")

        self._root = root
        self._parent = None
        self._view = self.get_root().make_view(self)
        self.set_parent(parent)

    def _view_notify_prop_changed(self, prop, new_value):
        if self._view:
            self._view.prop_changed(prop, new_value)

    @property
    def view(self):
        return self._view

    def get_root(self):
        return self._root

    def get_parent(self):
        if self._parent is None:
            return self._parent
        return self._parent()

    def set_parent(self, value):
        old = self.get_parent()
        if value is not None and old is not None:
            raise ValueError("Attempt to set parent while another parent is"
                             " set")
        self._parent = weakref.ref(value) if value is not None else None
        if value is not None:
            self._add_to_parent(value)
        elif old is not None:
            self._remove_from_parent(old)

    def _add_to_parent(self, new_parent):
        """
        Perform all management tasks at the current :attr:`parent` which are
        required to register this object with the parent.

        At the time this function is called, the object is not yet contained in
        inside the parents container.

        If this method raises, the object (and any other object which is about
        to be inserted at the same time) will not be inserted into the parent.

        The default implementation does nothing.
        """

    def _remove_from_parent(self, old_parent):
        """
        Perform all management tasks at the current :attr:`parent` which are
        required to un-register this object from the parent.

        At the time this function is called, the object is still contained
        inside the parents container.

        If this method raises, the object (and any other object which is about
        to be removed at the same time) will not be removed from the parent.

        The default implementation does nothing.
        """

    @abc.abstractproperty
    def label(self):
        """
        A label, which is typically shown in the user interface. For some
        elements, the label may also be the identifying token.
        """

    @abc.abstractclassmethod
    def create_from_etree(cls, el, *, root=None, parent=None):
        pass

    @abc.abstractmethod
    def save_to_etree(self, parent):
        pass

class RosterNodeView:
    def __init__(self, for_object):
        super().__init__()
        self._obj = for_object

    def prop_changed(self, prop, new_value):
        """
        Notification that the given property *prop* has changed on *instance*
        and now has a *new_value*.
        """

class RosterContainerView(RosterNodeView):
    """
    This is a mix-in class to provide default implementations for the methods a
    container supporting view needs to have.
    """

    def post_insert(self, at, objs):
        pass

    def post_remove(self, at, objs):
        pass

    def pre_insert(self, at, objs):
        pass

    def pre_remove(self, sl, objs):
        pass


class RosterContainer(RosterNode, collections.abc.MutableSequence):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._children = []

    def _index_to_indices(self, index, src):
        """
        Convert and range check the arguments to the dunder methods
        ``__*item__``.

        *index* must be an integer or a :class:`slice` object. If *index* is an
        integer, *src* must be a single object, otherwise it must be an iterable
        of objects.

        If *index* is an integer, it is range-checked against the current length
        of the container.

        Return a quadruple (*start*, *stop*, *step*, *src*). *start*, *stop*,
        and *step* are values equivalent to those returned by
        :meth:`slice.indices` for the current length of the container. *src* is
        is passed without modification if *index* is a slice, otherwise it is
        wrapped into a list.

        Thus, the resulting *src* is always the list of objects to which the
        action refers.
        """

        if isinstance(index, slice):
            start, stop, step = index.indices(len(self))
            if step != 1:
                # XXX: we enforce contigous manipulation here, as the QT toolkit
                # requires this
                raise NotImplementedError("FIXME: manipulation using"
                                          " non-contigous slices not supported")
        else:
            if not (-len(self) <= index < len(self)):
                raise IndexError("list index out of range")
            index %= len(self)
            start, stop, step = index, index+1, 1
            src = [src]
        return start, stop, step, src

    def _pre_insert_single(self, obj):
        obj.set_parent(self)

    def _pre_insert_rollback_single(self, obj):
        self._pre_remove_single(obj)

    def _pre_insert(self, at, objs):
        """
        Called before new items are inserted into the backing list. *at* is the
        normalized integer index of the first object to be inserted and *objs*
        is a sequence of objects which are about to be inserted.
        """
        with contextlib.ExitStack() as stack:
            for obj in objs:
                self._pre_insert_single(obj)
                stack.callback(functools.partial(
                    self._pre_insert_rollback_single,
                    obj))
            stack.pop_all()

        if self.view:
            self.view.pre_insert(at, objs)

    def _post_insert(self, at, objs):
        """
        Called after new items are inserted into the backing list. *at* is the
        normalized integer index of the first object which was inserted and
        *objs* is a sequence of objects which have been inserted.
        """
        if self.view:
            self.view.post_insert(at, objs)

    def _pre_remove_single(self, obj):
        obj.set_parent(None)

    def _pre_remove_rollback_single(self, obj):
        self._pre_insert_single(obj)

    def _pre_remove(self, sl, objs):
        """
        Called before items are removed from the backing list. *sl* is a slice
        object representing the range of indices from which *objs* are
        taken away. *objs* is the list of objects currently at the places to
        which *sl* refers.

        .. note::

           Currently, *sl* is restricted to be contigous and forward, that is,
           step is equal to 1.

        """
        with contextlib.ExitStack() as stack:
            for obj in objs:
                self._pre_remove_single(obj)
                stack.callback(functools.partial(
                    self._pre_remove_rollback_single,
                    obj))
            stack.pop_all()

        if self.view:
            self.view.pre_remove(sl, objs)

    def _post_remove(self, sl, objs):
        """
        Called after items have been removed from the backing list. *sl* is a
        slice object representing the range of indices from which *objs* have
        been taken away. *objs* is a list of those objects which have just been
        removed and were formerly at the indicies to which *sl* refers.

        .. note::

           Currently, *sl* is restricted to be contigous and forward, that is,
           step is equal to 1.

        """

        if self.view:
            self.view.post_remove(sl, objs)

    def __contains__(self, obj):
        return obj in self._children

    def __iter__(self):
        return iter(self._children)

    def __len__(self):
        return len(self._children)

    def __getitem__(self, index):
        return self._children[index]

    def __reversed__(self):
        return reversed(self._children)

    def __setitem__(self, index, src):
        start, stop, step, src = self._index_to_indices(index, src)
        if start == stop:
            # insertion of sequence at some point
            # we require src to be iterable mulitple times, thus we copy it into
            # a list.
            src = list(src)
            self._pre_insert(start, src)
            self._children[start:stop] = src
            self._post_insert(start, src)
        else:
            # FIXME: We treat replacement as removal and insertion. Can we do
            # better? Would it bring any benefit?
            del self[index]
            self[start:start] = src

    def __delitem__(self, index):
        start, stop, step, _ = self._index_to_indices(index, None)
        objs = self._children[start:stop:step]
        self._pre_remove(index, objs)
        del self._children[start:stop:step]
        self._post_remove(index, objs)

    def __bool__(self):
        return True

    def insert(self, index, obj):
        if index < -len(self):
            index = 0
        elif index >= len(self):
            index = len(self)
        else:
            index %= len(self)
        self[index:index] = [obj]

    def extend(self, iterable):
        self[len(self):len(self)] = iterable

    def index(self, obj):
        return self._children.index(obj)

    def append(self, obj):
        self.extend([obj])

    def reverse(self):
        raise NotImplementedError("Reversal is not implemented")

    @events.catchall
    def forward_event(self, ev):
        type_ = ev.type_
        for child in self._children:
            if events.accepts_event(child, type_):
                child.dispatch_event(ev)

    def _save_children_to_etree(self, dest):
        for child in self._children:
            child.save_to_etree(dest)

    def _load_children_from_etree(self, src):
        new_children = []
        for child in src:
            if not isinstance(child.tag, str):
                continue
            try:
                cls = lookup_class_by_tag(child.tag)
            except LookupError:
                logger.warning("failed to find roster object for %r",
                               child)
                continue
            new_children.append(cls.create_from_etree(
                child,
                root=self.get_root()))
        self.extend(new_children)

class RosterGroup(RosterContainer):
    """
    A roster group is the representation of the group concept defined in XMPP.

    This implies some limitations which need to be enforced:

    * Only one pair of ``(account_jid, remote_jid)`` may occur as direct child
      in a group at the same time (children of subgroups do not count).

    """

    def __init__(self, label, **kwargs):
        self._label = label
        super().__init__(**kwargs)
        self._via_cache = {}
        self._group_cache = {}

    def register_via(self, obj):
        peer_map = self._via_cache.setdefault(obj._account_jid, {})
        if obj.peer_jid in peer_map:
            raise ValueError("duplicate via in group")
        peer_map[obj.peer_jid] = obj

    def unregister_via(self, obj):
        try:
            peer_map = self._via_cache[obj.account_jid]
        except KeyError:
            raise ValueError("attempt to unregister via not in group") \
                from None

        jid = obj.peer_jid
        old = peer_map.pop(jid)
        if old is not obj:
            peer_map[jid] = old
            raise ValueError("attempt to unregister via not in group")

    def register_subgroup(self, obj):
        if obj.label in self._group_cache:
            raise ValueError("duplicate subgroup in group")
        self._group_cache[obj.label] = obj

    def unregister_subgroup(self, obj):
        label = obj.label
        try:
            old = self._group_cache.pop(label)
        except KeyError:
            raise ValueError("attempt to unregister subgroup not in group") \
                from None

        if old is not obj:
            self._group_cache[label] = old
            raise ValueError("attempt to unregister subgroup not in group")

    def update_subgroup_registry(self, old_name):
        group = self._group_cache[old_name]
        if group.label == old_name:
            return
        if group.label in self._group_cache:
            raise ValueError("duplicate subgroup in group")

        del self._group_cache[old_name]
        self._group_cache[group.label] = group

    def _add_to_parent(self, parent):
        parent = self.get_parent()
        if not isinstance(parent, RosterGroup):
            raise TypeError("parent must be a group")
        parent.register_subgroup(self)

    def _remove_from_parent(self, parent):
        parent.unregister_subgroup(self)

    @property
    def label(self):
        return self._label

    @label.setter
    def label(self, new_value):
        if self._label == new_value:
            return
        old_name = self._label
        self._label = new_value
        parent = self.get_parent()
        if parent is not None:
            parent.update_subgroup_registry(old_name)
        self._view_notify_prop_changed(RosterGroup.label, value)

    @events.handler_for(*RosterViaEventType)
    def forward_via_events(self, ev):
        try:
            peer_map = self._via_cache[ev.account_jid]
        except KeyError:
            pass
        else:
            try:
                via = peer_map[ev.peer_jid]
            except KeyError:
                pass
            else:
                # only dispatch the event through contacts which have an
                # affected via
                via.get_parent().dispatch_event(ev)

        for child in self._children:
            if     (not isinstance(child, RosterContact) and
                    events.accepts_event(child, ev.type_)):
                child.dispatch_event(ev)

    @classmethod
    def create_from_etree(cls, el, **kwargs):
        instance = cls(label=el.get("label", None), **kwargs)
        instance._load_children_from_etree(el)
        return instance

    def load_from_etree(self, el):
        # this can fail, which is why we put it at the top
        self.label = el.get("label", None)
        self.clear()
        self._load_children_from_etree(el)

    def save_to_etree(self, parent):
        if parent is None:
            el = etree.Element(GROUP_TAG, nsmap={
                None: mlxc_namespaces.roster
            })
        else:
            el = etree.SubElement(parent, GROUP_TAG)

        if self._label:
            el.set("label", self._label)

        self._save_children_to_etree(el)

        return el

class RosterContact(RosterContainer):
    def __init__(self, label=None, **kwargs):
        super().__init__(**kwargs)
        self._label = label

    def register_via(self, obj):
        parent = self.get_parent()
        if parent is not None:
            parent.register_via(obj)

    def unregister_via(self, obj):
        parent = self.get_parent()
        if parent:
            parent.unregister_via(obj)

    def _add_to_parent(self, parent):
        if not isinstance(parent, RosterGroup):
            raise TypeError("parent must be a group")
        for child in self:
            parent.register_via(child)

    def _remove_from_parent(self, parent):
        for child in self:
            parent.unregister_via(child)

    @property
    def label(self):
        if not self._label:
            if len(self):
                return self[0].label
        return self._label or repr(self)

    @label.setter
    def label(self, value):
        self._label = value
        self._view_notify_prop_changed(RosterContact.label, value)

    @property
    def presence(self):
        if not len(self):
            logger.warning("contact without vias asked for presence")
            return asyncio_xmpp.presence.PresenceState()
        return max(child.presence for child in self._children)

    @property
    def any_account_available(self):
        """
        Return :data:`True` if at least one account used by the vias of this
        contact is currently available (that is, attached to the roster).
        """
        return any(via.account_available for via in self)

    @events.handler_for(RosterViaEventType.PRESENCE_CHANGED)
    def ev_via_presence_changed(self, ev):
        old_presence = self.presence
        super().forward_event(ev)
        new_presence = self.presence
        if old_presence != new_presence:
            self._view_notify_prop_changed(RosterContact.presence,
                                           new_presence)

    @events.handler_for(RosterViaEventType.LABEL_CHANGED)
    def ev_via_label_changed(self, ev):
        super().forward_event(ev)
        if not self._label and len(self):
            self._view_notify_prop_changed(RosterContact.label,
                                           self.label)

    @events.handler_for(*RosterAccountEventType)
    def ev_account_changed(self, ev):
        old_value = self.any_account_available
        super().forward_event(ev)
        new_value = self.any_account_available
        if old_value != new_value:
            self._view_notify_prop_changed(
                RosterContact.any_account_available,
                new_value)

    @classmethod
    def create_from_etree(cls, el, **kwargs):
        instance = cls(label=el.get("label", None), **kwargs)
        instance._load_children_from_etree(el)
        return instance

    def save_to_etree(self, parent):
        el = etree.SubElement(parent, CONTACT_TAG)
        if self._label:
            el.set("label", self._label)
        self._save_children_to_etree(el)
        return el

class RosterVia(RosterNode):
    def __init__(self, account_jid, peer_jid,
                 label=None,
                 presence=asyncio_xmpp.presence.PresenceState(),
                 account_available=False,
                 **kwargs):
        self._account_jid = account_jid
        self._peer_jid = peer_jid
        super().__init__(**kwargs)
        self._label = label
        self._presence = presence
        self._account_available = bool(account_available)

    def _set_account_available(self, new_value):
        new_value = bool(new_value)
        if new_value == self._account_available:
            return
        self._account_available = new_value
        self._view_notify_prop_changed(RosterVia.account_available,
                                       new_value)

    def _set_label(self, new_value):
        if new_value == self._label:
            return
        self._label = new_value
        self._view_notify_prop_changed(RosterVia.label,
                                       new_value)

    def _set_presence(self, new_value):
        if new_value == self._presence:
            return
        self._presence = new_value
        self._view_notify_prop_changed(RosterVia.presence,
                                       new_value)

    def _add_to_parent(self, parent):
        if not isinstance(parent, RosterContact):
            raise TypeError("parent must be a contact")
        parent.register_via(self)

    def _remove_from_parent(self, parent):
        parent.unregister_via(self)

    @property
    def label(self):
        return self._label or str(self._peer_jid)

    @label.setter
    def label(self, value):
        # FIXME: trigger change in actual XMPP roster
        self._label = value
        self._view_notify_prop_changed(RosterVia.label, value)

    @property
    def account_jid(self):
        return self._account_jid

    @property
    def peer_jid(self):
        return self._peer_jid

    @property
    def presence(self):
        return self._presence

    @property
    def account_available(self):
        return self._account_available

    @events.handler_for(RosterViaEventType.PRESENCE_CHANGED)
    def ev_via_presence_changed(self, ev):
        self._set_presence(ev.new_presence)

    @events.handler_for(RosterViaEventType.LABEL_CHANGED)
    def ev_via_label_changed(self, ev):
        self._set_label(ev.new_label)

    @events.handler_for(RosterAccountEventType.AVAILABLE)
    def ev_account_available(self, ev):
        if ev.account_jid == self.account_jid:
            self._set_account_available(True)

    @events.handler_for(RosterAccountEventType.UNAVAILABLE)
    def ev_account_unavailable(self, ev):
        if ev.account_jid == self.account_jid:
            self._set_account_available(False)
            self._set_presence(asyncio_xmpp.presence.PresenceState())

    @classmethod
    def create_from_etree(cls, el, **kwargs):
        account_jid = asyncio_xmpp.jid.JID.fromstr(el.get("account"))
        peer_jid = asyncio_xmpp.jid.JID.fromstr(el.get("peer"))
        label = el.get("peer", None)
        return cls(account_jid, peer_jid, label=label, **kwargs)

    def save_to_etree(self, parent):
        el = etree.SubElement(parent, VIA_TAG)
        if self._label:
            el.set("label", self._label)
        el.set("account", str(self._account_jid))
        el.set("peer", str(self._peer_jid))

class Roster(RosterGroup):
    def __init__(self):
        # we set root=1 to avoid having a cyclic reference to ourselves
        # also, we delete the _root attribute later, everything should be using
        # the property
        super().__init__(label=None, parent=None, root=1)
        del self._root

        self._accounts = {}

    def _initial_roster(self, node, roster):
        logger.debug("unhandled initial roster: %r", roster)

    def _presence_changed(self, node, bare_jid, resources, new_presence):
        self.dispatch_event(RosterViaPresenceChanged(
            node.account_jid,
            bare_jid,
            new_presence,
            resources=resources))

    def _session_started(self, node):
        self.dispatch_event(RosterAccountEvent(
            RosterAccountEventType.AVAILABLE,
            node.account_jid))

    def _session_ended(self, node):
        self.dispatch_event(RosterAccountEvent(
            RosterAccountEventType.UNAVAILABLE,
            node.account_jid))

    @abc.abstractmethod
    def make_view(self, for_object):
        return None

    def _add_to_parent(self):
        raise TypeError("cannot attach root to another roster node")

    def _remove_from_parent(self):
        assert False

    def get_root(self):
        return self

    def enable_account(self, account):
        logger.debug("attaching account %s", account.account_jid)

        node_tokens = [
            account.node.callbacks.add_callback(
                "session_started",
                functools.partial(self._session_started, account)
            ),
            account.node.callbacks.add_callback(
                "session_ended",
                functools.partial(self._session_ended, account)
            )
        ]

        # FIXME: inform account_roster about initial roster
        roster_tokens = [
            account.roster.callbacks.add_callback(
                "initial_roster",
                functools.partial(self._initial_roster, account)
            )
        ]

        presence_tokens = [
            account.presence.callbacks.add_callback(
                "presence_changed",
                functools.partial(self._presence_changed, account)
            )
        ]

        self._accounts[account] = (node_tokens,
                                   roster_tokens,
                                   presence_tokens)

    def disable_account(self, account):
        logger.debug("detaching account %s", account.account_jid)
        node_tokens, roster_tokens, presence_tokens = self._accounts.pop(account)
        for token in roster_tokens:
            account.roster.callbacks.remove_callback(token)
        for token in node_tokens:
            account.node.callbacks.remove_callback(token)
        for token in presence_tokens:
            account.presence.callbacks.remove_callback(token)
        self.dispatch_event(RosterAccountEvent(
            RosterAccountEventType.UNAVAILABLE,
            account.account_jid))

roster_node_classes = {
    CONTACT_TAG: RosterContact,
    VIA_TAG: RosterVia,
    GROUP_TAG: RosterGroup
}

def lookup_class_by_tag(tag):
    return roster_node_classes[tag]
