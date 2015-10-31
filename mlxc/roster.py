import abc
import asyncio
import json
import logging

import aioxmpp.presence
import aioxmpp.roster
import aioxmpp.roster.xso
import aioxmpp.utils
import aioxmpp.xso

import mlxc.instrumentable_list
import mlxc.plugin
import mlxc.visitor
import mlxc.utils

logger = logging.getLogger(__name__)


class Node(metaclass=abc.ABCMeta):
    View = None

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._view = None
        self._parent = None
        self._root = None
        self._index_at_parent = None

    @property
    def parent(self):
        return self._parent

    @property
    def root(self):
        return self._root

    @property
    def index_at_parent(self):
        return self._index_at_parent

    @property
    def view(self):
        if self._view is not None:
            return self._view
        if self.View is not None:
            self._view = self.View(self)
            return self._view
        raise AttributeError("no view class attached")

    @view.deleter
    def view(self):
        self._view = None

    def parent_supported(self, parent):
        return False

    def _add_to_parent(self, new_parent):
        if self._parent is not None:
            raise RuntimeError("parent already set")
        self._parent = new_parent
        self._root_changed()

    def _root_changed(self):
        if self.parent is None:
            self._root = None
        else:
            self._root = self.parent.root

    def _remove_from_parent(self):
        if self._parent is None:
            raise RuntimeError("parent is not set")
        self._parent = None
        self._root_changed()

    @classmethod
    def attach_view(cls, view_cls):
        if "View" in cls.__dict__ and cls.View is not None:
            raise ValueError("only a single view can be attached to a "
                             "node class")
        cls.View = view_cls

    @abc.abstractmethod
    def to_xso(self):
        pass


class Container(mlxc.instrumentable_list.ModelList, Node):
    def __init__(self, *args, **kwargs):
        self.on_register_item.connect(self._set_item_parent)
        self.on_unregister_item.connect(self._unset_item_parent)
        self._change_state = None
        super().__init__(*args, **kwargs)
        self.reindex()

    def __bool__(self):
        return True

    def reindex(self):
        for i, item in enumerate(self):
            item._index_at_parent = i

    def _set_item_parent(self, item):
        item._add_to_parent(self)

    def _unset_item_parent(self, item):
        item._remove_from_parent()

    def _root_changed(self):
        super()._root_changed()
        if self.root is None:
            self.begin_insert_rows = None
            self.begin_move_rows = None
            self.begin_remove_rows = None
            self.end_insert_rows = None
            self.end_move_rows = None
            self.end_remove_rows = None
        else:
            self.begin_insert_rows = self.root.begin_insert_rows
            self.begin_move_rows = self.root.begin_move_rows
            self.begin_remove_rows = self.root.begin_remove_rows
            self.end_insert_rows = self.root.end_insert_rows
            self.end_move_rows = self.root.end_move_rows
            self.end_remove_rows = self.root.end_remove_rows
        for item in self:
            item._root_changed()

    def _begin_insert_rows(self, start, end):
        if self.begin_insert_rows is not None:
            self.begin_insert_rows(self, start, end)
        self._change_state = (start, end)
        added = (end - start) + 1
        for item in self[start:]:
            item._index_at_parent += added

    def _end_insert_rows(self):
        start, end = self._change_state
        self._change_state = None
        for i, item in enumerate(self[start:end+1]):
            item._index_at_parent = start+i
        super()._end_insert_rows()

    def _begin_move_rows(self, srcindex1, srcindex2, destindex):
        if self.begin_move_rows is not None:
            self.begin_move_rows(self, srcindex1, srcindex2, self, destindex)

    def _end_move_rows(self):
        super()._end_move_rows()
        self.reindex()

    def _begin_remove_rows(self, start, end):
        if self.begin_remove_rows is not None:
            self.begin_remove_rows(self, start, end)

    def _end_remove_rows(self):
        super()._end_remove_rows()
        self.reindex()

    def inject(self, index, iterable):
        items = list(iterable)
        self._register_items(items)
        self._storage[index:index] = items

    def eject(self, start, end):
        result = self._storage[start:end]
        self._unregister_items(result)
        del self._storage[start:end]
        return result


class Via(Node):
    class XSORepr(aioxmpp.roster.xso.Item):
        TAG = (mlxc.utils.mlxc_namespaces.roster, "via")

        account_jid = aioxmpp.xso.Attr(
            (None, "account"),
            type_=aioxmpp.xso.JID(),
        )

        def __init__(self, via):
            super().__init__(
                via.peer_jid,
                name=via.name,
                groups=(),
                subscription=via.subscription,
                approved=via.approved,
                ask=via.ask)
            self.account_jid = via.account_jid

        def to_object(self):
            result = Via(self.account_jid, self.jid)
            result._name = self.name
            result._subscription = self.subscription
            result._approved = self.approved
            result._ask = self.ask
            return result


    def __init__(self, account_jid, peer_info):
        super().__init__()
        self._account_jid = account_jid
        if isinstance(peer_info, aioxmpp.roster.Item):
            self._roster_item = peer_info
        else:
            self._roster_item = None
            self._peer_jid = peer_info
            self._name = None
            self._subscription = "none"
            self._approved = False
            self._ask = None

    @property
    def account_jid(self):
        return self._account_jid

    @property
    def roster_item(self):
        return self._roster_item

    @roster_item.setter
    def roster_item(self, new_value):
        if new_value is None and self._roster_item is not None:
            self._peer_jid = self._roster_item.jid
            self._name = self._roster_item.name
            self._subscription = self._roster_item.subscription
            self._approved = self._roster_item.approved
            self._ask = self._roster_item.ask
        self._roster_item = new_value

    @property
    def peer_jid(self):
        if self._roster_item is not None:
            return self._roster_item.jid
        return self._peer_jid

    @property
    def label(self):
        return self.name or str(self.peer_jid)

    @property
    def subscription(self):
        if self._roster_item is not None:
            return self._roster_item.subscription
        return self._subscription

    @property
    def ask(self):
        if self._roster_item is not None:
            return self._roster_item.ask
        return self._ask

    @property
    def name(self):
        if self._roster_item is not None:
            return self._roster_item.name
        return self._name

    @property
    def approved(self):
        if self._roster_item is not None:
            return self._roster_item.approved
        return self._approved

    def parent_supported(self, parent):
        if isinstance(parent, (MetaContact, Group)):
            return True
        return super().parent_supported(parent)

    def to_xso(self):
        return self.XSORepr(self)


class MetaContact(Container):
    class XSORepr(aioxmpp.xso.XSO):
        TAG = (mlxc.utils.mlxc_namespaces.roster, "meta")

        label = aioxmpp.xso.Attr(
            "label",
            default=None
        )

        children = aioxmpp.xso.ChildList([Via.XSORepr])

        def to_object(self):
            result = MetaContact()
            result.label = self.label
            children = [child.to_object() for child in self.children]
            result[:] = children
            return result

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._label = None

    @property
    def label(self):
        if self._label is not None:
            return self._label
        if len(self) > 0:
            return self[0].label

    @label.setter
    def label(self, label):
        self._label = label

    def parent_supported(self, parent):
        if isinstance(parent, Group):
            return True
        return super().parent_supported(parent)

    def to_xso(self):
        xso = self.XSORepr()
        xso.label = self.label
        xso.children.extend(child.to_xso() for child in self)
        return xso


class Group(Container):
    class XSORepr(aioxmpp.xso.XSO):
        TAG = (mlxc.utils.mlxc_namespaces.roster, "group")

        label = aioxmpp.xso.Attr(
            "label"
        )

        children = aioxmpp.xso.ChildList([
            MetaContact.XSORepr,
            Via.XSORepr
        ])

        def to_object(self):
            result = Group(self.label)
            result[:] = [child.to_object() for child in self.children]
            return result


    def __init__(self, label, **kwargs):
        super().__init__(**kwargs)
        self.label = label

    def parent_supported(self, parent):
        if isinstance(parent, Group):
            return True
        elif isinstance(parent, TreeRoot):
            return True
        return super().parent_supported(parent)

    def to_xso(self):
        xso = self.XSORepr()
        xso.label = self.label
        xso.children.extend(child.to_xso() for child in self)
        return xso


Group.XSORepr.register_child(Group.XSORepr.children, Group.XSORepr)


class TreeRoot(Container):
    class XSORepr(aioxmpp.xso.XSO):
        TAG = (mlxc.utils.mlxc_namespaces.roster, "tree")

        DECLARE_NS = {
            None: mlxc.utils.mlxc_namespaces.roster,
            "xmpp": aioxmpp.utils.namespaces.rfc6121_roster
        }

        children = aioxmpp.xso.ChildList([
            Group.XSORepr
        ])

        def to_object(self):
            root = TreeRoot()
            root[:] = [child.to_object() for child in self.children]
            return root


    @property
    def root(self):
        return self

    def _add_to_parent(self, parent):
        raise TypeError("cannot add TreeRoot to any parent")

    def to_xso(self):
        xso = self.XSORepr()
        xso.children.extend(child.to_xso() for child in self)
        return xso

    def load_from_xso(self, xso):
        self[:] = [child.to_object() for child in xso.children]


class Tree:
    begin_insert_rows = None
    begin_move_rows = None
    begin_remove_rows = None
    end_insert_rows = None
    end_move_rows = None
    end_remove_rows = None

    def __init__(self):
        super().__init__()
        self._root = TreeRoot()
        self._root.begin_insert_rows = self._begin_insert_rows
        self._root.begin_move_rows = self._begin_move_rows
        self._root.begin_remove_rows = self._begin_remove_rows
        self._root.end_insert_rows = self._end_insert_rows
        self._root.end_move_rows = self._end_move_rows
        self._root.end_remove_rows = self._end_remove_rows

    def _begin_insert_rows(self, parent, index1, index2):
        if self.begin_insert_rows is not None:
            self.begin_insert_rows(parent, index1, index2)

    def _begin_move_rows(self, srcparent, srcindex1, srcindex2,
                         destparent, destindex):
        if self.begin_move_rows is not None:
            self.begin_move_rows(srcparent, srcindex1, srcindex2,
                                 destparent, destindex)

    def _begin_remove_rows(self, parent, index1, index2):
        if self.begin_remove_rows is not None:
            self.begin_remove_rows(parent, index1, index2)

    def _end_insert_rows(self):
        if self.end_insert_rows is not None:
            self.end_insert_rows()

    def _end_move_rows(self):
        if self.end_move_rows is not None:
            self.end_move_rows()

    def _end_remove_rows(self):
        if self.end_remove_rows is not None:
            self.end_remove_rows()

    @property
    def root(self):
        return self._root


class TreeVisitor(mlxc.visitor.Visitor):
    @mlxc.visitor.for_class(Container)
    def visit_container(self, cont):
        for item in cont:
            self._visit(item)

    @mlxc.visitor.for_class(Node)
    def visit_node(self, node):
        pass


class _RosterConnector:
    def __init__(self, plugin, account, state):
        self.account = account
        self.plugin = plugin

        self._tokens = []

        def connect(signal, slot):
            self._tokens.append((
                signal,
                signal.connect(slot)
            ))

        service = state.summon(aioxmpp.roster.Service)
        connect(service.on_entry_added,
                self._on_entry_added)
        connect(service.on_entry_name_changed,
                self._on_entry_name_changed)
        connect(service.on_entry_added_to_group,
                self._on_entry_added_to_group)
        connect(service.on_entry_removed_from_group,
                self._on_entry_removed_from_group)
        connect(service.on_entry_removed,
                self._on_entry_removed)
        self.roster_service = service

        service = state.summon(aioxmpp.presence.Service)
        connect(service.on_available,
                self._on_resource_available)
        connect(service.on_changed,
                self._on_resource_presence_changed)
        connect(service.on_unavailable,
                self._on_resource_unavailable)

    def _on_entry_added(self, item):
        self.plugin._on_entry_added(self.account, item)

    def _on_entry_name_changed(self, item):
        self.plugin._on_entry_name_changed(self.account, item)

    def _on_entry_added_to_group(self, item, group_name):
        self.plugin._on_entry_added_to_group(
            self.account, item, group_name)

    def _on_entry_removed_from_group(self, item, group_name):
        self.plugin._on_entry_removed_from_group(
            self.account, item, group_name)

    def _on_entry_removed(self, item):
        self.plugin._on_entry_removed(self.account, item)

    def _on_resource_available(self, full_jid, stanza):
        self.plugin._on_resource_available(
            self.account,
            full_jid,
            stanza)

    def _on_resource_presence_changed(self, full_jid, stanza):
        self.plugin._on_resource_presence_changed(
            self.account,
            full_jid,
            stanza)

    def _on_resource_unavailable(self, full_jid, stanza):
        self.plugin._on_resource_unavailable(
            self.account,
            full_jid,
            stanza)

    def close(self):
        for signal, token in self._tokens:
            signal.disconnect(token)


class _EraseVia(TreeVisitor):
    def __init__(self, roster_item, *, deep=True):
        super().__init__()
        self._roster_item = roster_item
        self.deep = deep

    def visit(self, node):
        self._visit_root = node
        super().visit(node)

    @mlxc.visitor.for_class(Group)
    def visit_group(self, group):
        if not self.deep and group is not self._visit_root:
            return
        super().visit_container(group)

    @mlxc.visitor.for_class(Via)
    def visit_via(self, via):
        if via.roster_item is self._roster_item:
            if len(via.parent) == 1 and isinstance(via.parent, MetaContact):
                del via.parent.parent[via.parent.index_at_parent]
            else:
                del via.parent[via.index_at_parent]


class _RecoverXMPPRoster(TreeVisitor):
    def __init__(self, account_jid):
        super().__init__()
        self._account_jid = account_jid

    def visit(self, root):
        self._data = {}
        super().visit(root)
        return self._data

    @mlxc.visitor.for_class(Group)
    def visit_group(self, group):
        self._last_group = group
        super().visit_container(group)

    @mlxc.visitor.for_class(Via)
    def visit_via(self, via):
        if via.account_jid != self._account_jid:
            return

        data = self._data.setdefault(str(via.peer_jid), {})
        data["subscription"] = via.subscription
        data["ask"] = via.ask
        data["approved"] = via.approved
        data["name"] = via.name
        data.setdefault("groups", set()).add(self._last_group.label)


class _SetupMaps(TreeVisitor):
    def __init__(self, plugin):
        super().__init__()
        self._plugin = plugin

    @mlxc.visitor.for_class(Group)
    def visit_group(self, group):
        self._plugin._group_map[group.label] = group
        super().visit_container(group)


class Plugin(mlxc.plugin.Base):
    UID = "urn:uuid:7fdad690-1e8e-40cc-aaef-27924db9083e"

    def __init__(self, client):
        super().__init__(client)
        self._connectors = {}
        self._group_map = {}
        logger.debug("initialized roster plugin for %r", client)
        self._tokens = [
            (client.on_account_enabling,
             client.on_account_enabling.connect(self._on_account_enabling)),
            (client.on_account_disabling,
             client.on_account_disabling.connect(self._on_account_disabling)),
            (client.on_loaded,
             client.on_loaded.connect(self._on_loaded)),
            (client.config_manager.on_writeback,
             client.config_manager.on_writeback.connect(self._on_writeback)),
        ]

        for account in client.accounts:
            if account.enabled:
                self._on_account_enabling(account, client.account_state(account))

    @property
    def group_map(self):
        return self._group_map

    @asyncio.coroutine
    def _close(self):
        for signal, token in self._tokens:
            signal.disconnect(token)

    def _account_roster_filename(self, jid):
        return mlxc.config.escape_dirname(
            "xmpp:{}.json".format(jid)
        )

    def load_roster_state(self, jid, roster_service):
        try:
            f = self.client.config_manager.open_single(
                self.UID,
                self._account_roster_filename(jid),
                mode="r",
            )
        except OSError:
            pass
        else:
            with f:
                roster = json.load(f)
            roster_service.import_from_json(roster)

    def dump_roster_state(self, jid, roster_service):
        roster = roster_service.export_as_json()

        f = self.client.config_manager.open_single(
            self.UID,
            self._account_roster_filename(jid),
            mode="w",

        )
        with f:
            json.dump(roster, f)

    def _on_account_enabling(self, account, state):
        logger.debug("account enabled: %s", account)
        connector = _RosterConnector(self, account, state)
        self.load_roster_state(account.jid, connector.roster_service)
        self._connectors[account] = connector

    def _on_account_disabling(self, account, state, reason=None):
        try:
            connector = self._connectors.pop(account)
        except KeyError:
            return
        self.dump_roster_state(account.jid, connector.roster_service)
        connector.close()

    def _on_loaded(self):
        pass

    def _on_writeback(self):
        for account, connector in self._connectors.items():
            self.dump_roster_state(account.jid, connector.roster_service)

    def _autocreate_group(self, group_name):
        try:
            return self._group_map[group_name]
        except KeyError:
            pass

        group = Group(group_name)
        self._group_map[group_name] = group
        self.client.roster.root.append(group)
        return group

    def _on_entry_added(self, account, item):
        logger.debug("roster entry added at %s: %r", account, item)
        root = self.client.roster.root
        for group_name in item.groups:
            via = Via(account.jid, item)
            self._autocreate_group(group_name).append(via)

    def _on_entry_name_changed(self, item):
        pass

    def _on_entry_added_to_group(self, account, item, group_name):
        via = Via(account.jid, item)
        self._autocreate_group(group_name).append(via)

    def _on_entry_removed_from_group(self, account, item, group_name):
        _EraseVia(item, deep=False).visit(self._group_map[group_name])

    def _on_entry_removed(self, account, item):
        _EraseVia(item, deep=True).visit(self.client.roster.root)

    def _on_resource_available(self, account, full_jid, stanza):
        pass

    def _on_resource_presence_changed(self, account, full_jid, stanza):
        pass

    def _on_resource_unavailable(self, account, full_jid, stanza):
        pass
