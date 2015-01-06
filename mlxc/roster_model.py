import abc
import asyncio
import collections
import collections.abc
import contextlib
import logging
import weakref

import asyncio_xmpp.jid
import asyncio_xmpp.presence

from .utils import *

logger = logging.getLogger()

GROUP_TAG = "{{{}}}group".format(mlxc_namespaces.roster)
CONTACT_TAG = "{{{}}}contact".format(mlxc_namespaces.roster)
VIA_TAG = "{{{}}}via".format(mlxc_namespaces.roster)

class RosterNode(metaclass=abc.ABCMeta):
    def __init__(self, *,
                 parent=None,
                 frontend_view_type=None):
        super().__init__()
        self._parent = None
        if frontend_view_type is not None:
            self._view = frontend_view_type.make_view(self)
        else:
            self._view = None
        self.set_parent(parent)

    def _view_notify_prop_changed(self, prop, new_value):
        if self._view:
            self._view.prop_changed(self, prop, new_value)

    @property
    def view(self):
        return self._view

    def get_parent(self):
        return self._parent()

    def set_parent(self, value):
        old = self.get_parent()
        if value is not None and old is not None:
            raise ValueError("Attempt to set parent while another parent is"
                             " set")
        self._parent = weakref.ref(parent) if parent is not None else None
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

    def notify_via_label_changed(self, account_jid, peer_jid, new_label):
        """
        Notify this object and all of its possible children about the fact that
        this or another XMPP resource of the account referred to by
        *account_jid* has changed the label of the contact at *peer_jid* to
        *new_label*.

        The default implementation does nothing.
        """

class RosterNodeView:
    def prop_changed(self, instance, prop, new_value):
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


class RosterContainer(RosterNode, metaclass=collections.abc.MutableSequence):
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

        if self.view:
            self.view._pre_insert(at, objs)

        with contextlib.ExitStack() as stack:
            for obj in objs:
                self._pre_insert_single(obj)
                stack.callback(obj._pre_insert_rollback_single)
            stack.pop_all()

    def _post_insert(self, at, objs):
        """
        Called after new items are inserted into the backing list. *at* is the
        normalized integer index of the first object which was inserted and
        *objs* is a sequence of objects which have been inserted.
        """
        if self.view:
            self.view._post_insert(at, objs)

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

        if self.view:
            self.view._pre_remove(sl, objs)

        with contextlib.ExitStack() as stack:
            for obj in objs:
                self._pre_remove_single(obj)
                stack.callback(self._pre_remove_rollback_singlex)
            stack.pop_all()

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
            self.view._post_remove(sl, objs)

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
        start, stop, step, src = self.index_to_indices(index, src)
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
        start, stop, step, _ = self.index_to_indices(index, None)
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


    def notify_via_label_changed(self, account_jid, peer_jid, new_label):
        for child in self._children:
            if hasattr(child, "notify_via_label_changed"):
                child.notify_via_label_changed(account_jid, peer_jid, new_label)

    def notify_presence_changed(self, account_jid, peer_jid, new_presence):
        for child in self._children:
            if hasattr(child, "notify_presence_changed"):
                child.notify_presence_changed(account_jid, peer_jid,
                                              new_presence)

class RosterGroup(RosterContainer):
    """
    A roster group is the representation of the group concept defined in XMPP.

    This implies some limitations which need to be enforced:

    * Only one pair of ``(account_jid, remote_jid)`` may occur as direct child
      in a group at the same time (children of subgroups do not count).

    """

    def __init__(self, label, **kwargs):
        self._label = label
        super().__init__()
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

    def notify_via_label_changed(self, account_jid, peer_jid, new_label):
        try:
            peer_map = self._via_cache[account_jid]
        except KeyError:
            pass
        else:
            via = peer_map.get(peer_jid, None)
            if via is not None:
                via.notify_via_label_changed(account_jid, peer_jid, new_label)

        for group in self._group_cache.values():
            group.notify_via_label_changed(account_jid, peer_jid, new_label)


class RosterContact(RosterContainer):
    def __init__(self, label=None, **kwargs):
        super().__init__(**kwargs)
        self._label = label

    def register_via(self, obj):
        parent = self.get_parent()
        if parent is not None
            parent.register_via(obj)

    def unregister_via(self, obj):
        parent = self.get_parent()
        if parent:
            parent.unregister_via(obj)

    def add_to_parent(self, parent):
        if not isinstance(parent, RosterGroup):
            raise TypeError("parent must be a group")
        for child in self:
            parent.register_via(child)

    def remove_from_parent(self, parent):
        for child in self:
            parent.unregister_via(child)

    @property
    def label(self):
        return self._label

    @label.setter
    def label(self, value):
        self._label = value
        self._view_notify_prop_changed(RosterContact.label, value)


class RosterVia(RosterNode):
    def __init__(self, account_jid, peer_jid,
                 label=None,
                 presence=asyncio_xmpp.presence.PresenceState(),
                 **kwargs):
        self._account_jid = account_jid
        self._peer_jid = peer_jid
        super().__init__(**kwargs)
        self._label = label
        self._presence = presence

    def add_to_parent(self, parent):
        if not isinstance(parent, RosterContact):
            raise TypeError("parent must be a contact")
        parent.register_via(self)

    def remove_from_parent(self, parent):
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

    def notify_via_label_changed(self, account_jid, peer_jid, new_label):
        if    (account_jid == self.account_jid and
               peer_jid == self.peer_jid):
            self._label = new_label
            self._view_notify_prop_changed(RosterVia.label, value)

    def notify_presence_changed(self, account_jid, peer_jid, new_presence):
        if self._presence != new_presence:
            self._presence = new_presence
            self._view_notify_prop_changed(RosterVia.presence, new_presence)
