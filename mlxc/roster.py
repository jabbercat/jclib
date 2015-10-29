import aioxmpp.roster

import mlxc.instrumentable_list
import mlxc.visitor


class Node:
    View = None

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._view = None
        self._parent = None

    @property
    def parent(self):
        return self._parent

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

    def _remove_from_parent(self):
        if self._parent is None:
            raise RuntimeError("parent is not set")
        self._parent = None

    @classmethod
    def attach_view(cls, view_cls):
        if "View" in cls.__dict__ and cls.View is not None:
            raise ValueError("only a single view can be attached to a "
                             "node class")
        cls.View = view_cls


class Container(mlxc.instrumentable_list.ModelList):
    def __init__(self, *args, **kwargs):
        self.on_register_item.connect(self._set_item_parent)
        self.on_unregister_item.connect(self._unset_item_parent)
        super().__init__(*args, **kwargs)

    def __bool__(self):
        return True

    def _set_item_parent(self, item):
        item._add_to_parent(self)

    def _unset_item_parent(self, item):
        item._remove_from_parent()

    def _begin_insert_rows(self, start, end):
        if self.begin_insert_rows is not None:
            self.begin_insert_rows(self, start, end)

    def _begin_move_rows(self, srcindex1, srcindex2, destindex):
        if self.begin_move_rows is not None:
            self.begin_move_rows(self, srcindex1, srcindex2, self, destindex)

    def _begin_remove_rows(self, start, end):
        if self.begin_remove_rows is not None:
            self.begin_remove_rows(self, start, end)

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
    def __init__(self, account_jid, peer_jid):
        super().__init__()
        self._account_jid = account_jid
        self._peer_jid = peer_jid

    @property
    def account_jid(self):
        return self._account_jid

    @property
    def peer_jid(self):
        return self._peer_jid

    def parent_supported(self, parent):
        if isinstance(parent, Contact):
            return True
        return super().parent_supported(parent)


class Contact(Container, Node):
    def parent_supported(self, parent):
        if isinstance(parent, Group):
            return True
        return super().parent_supported(parent)


class Group(Container, Node):
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
    pass


class Tree:
    def __init__(self):
        super().__init__()
        self._root = TreeRoot()

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


class Plugin(mlxc.plugin.Base):
    def __init__(self, client):
        super().__init__(client)
        self._connectors = {}
        self._group_map = {}

    @property
    def group_map(self):
        return self._group_map

    def _on_account_enabling(self, account, state):
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
        root = self.client.roster.root
        for group_name in item.groups:
            via = Via(account.jid, item.jid)
            contact = Contact(initial=[via])
            self._autocreate_group(group_name).append(contact)

    def _on_entry_name_changed(self, item):
        pass

    def _on_entry_added_to_group(self, account, item, group_name):
        via = Via(account.jid, item.jid)
        contact = Contact(initial=[via])
        self._autocreate_group(group_name).append(contact)

    def _on_entry_removed_from_group(self, account, item, group_name):
        pass

    def _on_entry_removed(self, item):
        pass
