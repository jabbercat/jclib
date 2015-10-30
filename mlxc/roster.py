import asyncio
import logging

import aioxmpp.roster

import mlxc.instrumentable_list
import mlxc.plugin
import mlxc.visitor


logger = logging.getLogger(__name__)


class Node:
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
    def __init__(self, account_jid, roster_item):
        super().__init__()
        self._account_jid = account_jid
        self._roster_item = roster_item

    @property
    def account_jid(self):
        return self._account_jid

    @property
    def roster_item(self):
        return self._roster_item

    @property
    def label(self):
        if self._roster_item.name is not None:
            return self._roster_item.name
        return str(self._roster_item.jid)

    def parent_supported(self, parent):
        if isinstance(parent, Contact):
            return True
        return super().parent_supported(parent)


class Contact(Container):
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


class Group(Container):
    def __init__(self, label, **kwargs):
        super().__init__(**kwargs)
        self.label = label

    def parent_supported(self, parent):
        if isinstance(parent, Group):
            return True
        elif isinstance(parent, TreeRoot):
            return True
        return super().parent_supported(parent)


class TreeRoot(Container):
    @property
    def root(self):
        return self

    def _add_to_parent(self, parent):
        raise TypeError("cannot add TreeRoot to any parent")


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
            self.visit(item)

    @mlxc.visitor.for_class(Node)
    def visit_node(self, node):
        pass


class _RosterConnector:
    def __init__(self, plugin, account, state):
        self.account = account
        self.plugin = plugin
        self.service = state.summon(aioxmpp.roster.Service)

        self._tokens = []

        def connect(signal, slot):
            self._tokens.append((
                signal,
                signal.connect(slot)
            ))

        connect(self.service.on_entry_added,
                self._on_entry_added)
        connect(self.service.on_entry_name_changed,
                self._on_entry_name_changed)
        connect(self.service.on_entry_added_to_group,
                self._on_entry_added_to_group)
        connect(self.service.on_entry_removed_from_group,
                self._on_entry_removed_from_group)
        connect(self.service.on_entry_removed,
                self._on_entry_removed)

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

    def close(self):
        for signal, token in self._tokens:
            signal.disconnect(token)


class _EraseVia(TreeVisitor):
    def __init__(self, roster_item):
        super().__init__()
        self._roster_item = roster_item

    @mlxc.visitor.for_class(Via)
    def visit_via(self, via):
        if via.roster_item is self._roster_item:
            if len(via.parent) == 1:
                del via.parent.parent[via.parent.index_at_parent]
            else:
                del via.parent[via.index_at_parent]


class Plugin(mlxc.plugin.Base):
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

    def _on_account_enabling(self, account, state):
        logger.debug("account enabled: %s", account)
        self._connectors[account] = _RosterConnector(self, account, state)

    def _on_account_disabling(self, account, state, reason=None):
        try:
            connector = self._connectors.pop(account)
        except KeyError:
            return
        connector.close()

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
            contact = Contact(initial=[via])
            self._autocreate_group(group_name).append(contact)

    def _on_entry_name_changed(self, item):
        pass

    def _on_entry_added_to_group(self, account, item, group_name):
        via = Via(account.jid, item)
        contact = Contact(initial=[via])
        self._autocreate_group(group_name).append(contact)

    def _on_entry_removed_from_group(self, account, item, group_name):
        _EraseVia(item).visit(self._group_map[group_name])

    def _on_entry_removed(self, account, item):
        _EraseVia(item).visit(self.client.roster.root)
