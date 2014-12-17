import abc
import asyncio
import collections
import weakref

from .utils import *

GROUP_TAG = "{{{}}}group".format(mlxc_namespaces.roster)
CONTACT_TAG = "{{{}}}contact".format(mlxc_namespaces.roster)
VIA_TAG = "{{{}}}via".format(mlxc_namespaces.roster)

class RosterNode(metaclass=abc.ABCMeta):
    def __init__(self, *, parent=None):
        super().__init__()
        self._parent = weakref.ref(parent) if parent is not None else None

    @abc.abstractclassmethod
    def from_etree(cls, el, **kwargs):
        pass

    @property
    def parent(self):
        if self._parent is None:
            return None
        return self._parent()

    @abc.abstractproperty
    def label(self):
        pass

    @abc.abstractmethod
    def set_account_enabled(self, account_jid, enabled=True):
        pass

    @abc.abstractmethod
    def to_etree(self, parent):
        pass

class RosterContainer(RosterNode):
    def _convert_index_to_slice(self, index):
        if index < 0:
            if not (-len(self) <= index <= -1):
                raise IndexError("list index out of range")
            index = index % len(self)
        elif not (0 <= index < len(self)):
            raise IndexError("list index out of range")
        return slice(index, index+1)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._children = []

    def __len__(self):
        return len(self._children)

    def __getitem__(self, index):
        return self._children[index]

    def __contains__(self, obj):
        return obj in self._children

    def __iter__(self):
        return iter(self._children)

    def __reversed__(self):
        return reversed(self._children)

    def __repr__(self):
        return "<{}.{} object at 0x{:x}: len={}>".format(
            type(self).__module__,
            type(self).__qualname__,
            id(self),
            len(self))

    def index(self, child):
        return self._children.index(child)

    def set_account_enabled(self, account_jid, enabled=True):
        for child in self.children:
            child.set_account_enabled(account_jid, enabled=enabled)

    def _children_to_etree(self, dest):
        for child in self:
            child.to_etree(dest)

class RosterContact(RosterContainer, RosterNode):
    def _via_from_etree(self, el):
        return RosterVia.from_etree(el, parent=self)

    def _via(self, **kwargs):
        return RosterVia(parent=self, **kwargs)

    def __init__(self, label, **kwargs):
        super().__init__(**kwargs)
        self._label = label

    @classmethod
    def from_etree(cls, el, **kwargs):
        instance = cls(label=el.get("label"), **kwargs)
        for via_el in el.iterchildren(VIA_TAG):
            instance._children.append(self._via_from_etree(via_el))
        return instance

    @property
    def label(self):
        result = self._label
        if self:
            result = self[0].label
        return result or repr(self)

    @property
    def enabled(self):
        return any(child.enabled for child in self)

    def _new_via(self, account_jid, peer_jid, label):
        via = self._via(account_jid=account_jid,
                        peer_jid=peer_jid,
                        label=label)
        self._children.append(via)
        return via

    def to_etree(self, parent):
        el = etree.SubElement(parent, CONTACT_TAG)
        if self._label:
            el.set("label", self._label)
        self._children_to_etree(el)
        return el

class RosterVia(RosterNode):
    def __init__(self, account_jid, peer_jid, label, **kwargs):
        super().__init__(**kwargs)
        self._label = label
        self.account_jid = account_jid
        self.peer_jid = peer_jid
        self.enabled = False

    @classmethod
    def from_etree(cls, el, **kwargs):
        return cls(
            account_jid=asyncio_xmpp.jid.JID.fromstr(
                el.get("account")),
            peer_jid=asyncio_xmpp.jid.JID.fromstr(
                el.get("peer")),
            label=el.get("label"),
            **kwargs)

    @property
    def label(self):
        return self._label or str(self.peer_jid)

    @label.setter
    def label(self, value):
        self._label = value

    @label.deleter
    def label(self):
        self._label = None

    def set_account_enabled(self, account_jid, enabled=True):
        if self.account_jid == account_jid:
            self.enabled = enabled

    def to_etree(self, parent):
        el = etree.SubElement(
            parent,
            VIA_TAG,
            account=str(self.account_jid),
            peer=str(self.peer_jid)
        )
        if self._label:
            el.set("label", self._label)
        return el

class RosterGroup(RosterContainer, RosterNode):
    label = None

    def _group(self, **kwargs):
        return RosterGroup(parent=self, **kwargs)

    def _contact(self, **kwargs):
        return RosterContact(parent=self, **kwargs)

    def _contact_from_etree(self, el):
        return RosterContact.from_etree(el, parent=self)

    def _group_from_etree(self, el):
        return RosterGroup.from_etree(el, parent=self)

    def __init__(self, label, **kwargs):
        super().__init__(**kwargs)
        self.label = label
        #: map (account_jid, peer_jid) => via
        self._via_cache = collections.defaultdict(weakref.WeakValueDictionary)
        self._group_cache = {}

    def _register_via(self, via):
        self._via_cache[via.account_jid][via.peer_jid] = via

    def __delitem__(self, index):
        sl = self._convert_index_to_slice(index)
        items = self[index]
        for item in items:
            if isinstance(item, RosterContact):
                for via in item:
                    account_cache = self._via_cache[via.account_jid]
                    del account_cache[via.peer_jid]
                    if not account_cache:
                        del self._via_cache[via.account_jid]
            elif isinstance(item, RosterGroup):
                del self._group_cache[item.label]
            item._parent = None
        del self._children[index]

    def _new_metacontact(self, label):
        mc = self._contact(label=label)
        self._children.append(mc)
        return mc

    def _new_group(self, label):
        group = self._group(label=label)
        self._children.append(group)
        return group

    def has_via(self, account_jid, peer_jid):
        return (account_jid in self._via_cache and
                peer_jid in self._via_cache[account_jid])

    def append_via(self,
                   account_jid, peer_jid, label,
                   to_metacontact=None):
        if peer_jid in self._via_cache[account_jid]:
            raise ValueError("Duplicate account/peer jid pair in group")
        if to_metacontact is not None:
            if to_metacontact.parent is not self:
                raise ValueError("Metacontact is not in group")
        else:
            to_metacontact = self._new_metacontact(label)
        return to_metacontact._new_via(account_jid, peer_jid, label=label)

    def get_group(self, label):
        try:
            return self._group_cache[label]
        except KeyError:
            grp = self._new_group(label)
            self._group_cache[label] = grp
            return grp

    def remove(self, item):
        index = self._children.index(item)
        del self[index]

    @classmethod
    def from_etree(cls, el, **kwargs):
        instance = cls(label=el.get("label"), **kwargs)
        for item in el.iterchildren():
            if item.tag == CONTACT_TAG:
                child = self._contact_from_etree(el)
                if not child:
                    continue
                for via in child._children:
                    self._register_via(via)
            elif item.tag == GROUP_TAG:
                child = self._group_from_etree(el)
            else:
                continue
            self._children.append(child)
        return instance

    def to_etree(self, parent):
        if parent is None:
            el = etree.Element(GROUP_TAG)
        else:
            el = etree.SubElement(parent, GROUP_TAG)
        if self.label:
            el.set("label", self.label)
        self._children_to_etree(el)
        return el

    def _dump_tree(self, obj, depth, indent="  ", file=None):
        use_indent = indent * depth
        print(use_indent, repr(obj), sep="", file=file)
        if hasattr(obj, "__iter__"):
            for child in obj:
                self._dump_tree(child, depth+1, indent=indent, file=file)

    def dump_tree(self, file=None):
        import sys
        if file is None:
            file = sys.stdout

        self._dump_tree(obj, 0, file=file)

class RosterModel:
    def roster_group_factory(self):
        return RosterGroup()

    def roster_group_from_etree(self, tree):
        return RosterGroup.from_etree(tree)

    def __init__(self):
        self._root_group = self.roster_group_factory()

    @asyncio.coroutine
    def load(source, *, loop=None):
        loop = loop or asyncio.get_event_loop()
        # XXX: This might blow up heavily. I remotely recall threading issues
        # with lxml; these might have been special-cased for wsgi though.
        tree = yield from loop.run_in_executor(
            None,
            functools.partial(lxml.etree.parse, source)
        )
        root = tree.getroot()
        if root.tag != GROUP_TAG:
            raise ValueError("root node has invalid tag")
        self._root_group = self.roster_group_from_etree(root)

    @asyncio.coroutine
    def save(dest, *, loop=None, **kwargs):
        loop = loop or asyncio.get_event_loop()
        tree = self._root_group.to_etree(None)
        yield from loop.run_in_executor(
            None,
            functools.partial(lxml.etree.write, tree, **kwargs)
        )
