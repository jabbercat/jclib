import aioxmpp.stringprep
import aioxmpp.xso as xso

from .utils import mlxc_namespaces


class AccountSettings(xso.XSO):
    TAG = (mlxc_namespaces.account, "account")

    jid = xso.Attr(
        "jid",
        type_=xso.JID(),
    )

    disabled = xso.Attr(
        "disabled",
        type_=xso.Bool(),
        default=False,
    )

    allow_unencrypted = xso.Attr(
        "allow-unencrypted",
        type_=xso.Bool(),
        default=False,
    )

    colour = xso.Attr(
        "colour",
        type_=xso.String(),
    )

    _ = xso.Collector()

    def __init__(self, jid):
        super().__init__()
        self.jid = jid


class RosterItemTag(xso.XSO):
    TAG = (mlxc_namespaces.roster, "tag")

    label = xso.Text()


class RosterItemTagType(xso.AbstractElementType):
    def pack(self, v):
        obj = RosterItemTag()
        obj.label = v
        return obj

    def unpack(self, obj):
        return obj.label

    def get_xso_types(self):
        return [RosterItemTag]


class RosterItemBase(xso.XSO):
    address = xso.Attr(
        "address",
        type_=xso.JID(),
    )

    label = xso.Attr(
        "label",
        default=None,
    )

    pinned = xso.Attr(
        "pinned",
        type_=xso.Bool(),
        default=False,
    )

    closed = xso.Attr(
        "closed",
        type_=xso.DateTime(),
        default=None,
    )

    tags = xso.ChildValueList(
        RosterItemTagType(),
        container_type=set,
    )

    muted = xso.Attr(
        "muted",
        type_=xso.Bool(),
        default=False,
    )


class RosterContact(RosterItemBase):
    TAG = (mlxc_namespaces.roster, "contact")

    subscription = xso.Attr(
        "subscription",
        default="none",
    )

    approved = xso.Attr(
        "approved",
        type_=xso.Bool(),
        default=False,
    )

    ask = xso.Attr(
        "ask",
        type_=xso.Bool(),
        default=False,
    )


class RosterContacts(xso.XSO):
    TAG = (mlxc_namespaces.roster, "contacts")

    contacts = xso.ChildList([RosterContact])


class RosterMUC(RosterItemBase):
    TAG = (mlxc_namespaces.roster, "muc")

    autojoin = xso.Attr(
        "autojoin",
        type_=xso.Bool(),
        default=False,
    )

    nickname = xso.Attr(
        "nickname",
    )


class _AbstractPresence(xso.XSO):
    available = xso.Attr(
        "available",
        type_=xso.Bool(),
        default=True,
    )

    show = aioxmpp.Presence.show.xq_descriptor

    status = aioxmpp.Presence.status.xq_descriptor

    priority = aioxmpp.Presence.priority.xq_descriptor

    _ = xso.Collector()


class SinglePresenceState(_AbstractPresence):
    TAG = (mlxc_namespaces.presence, "presence")

    jid = xso.Attr(
        "jid",
        type_=xso.JID()
    )


class ComplexPresenceState(_AbstractPresence):
    TAG = (mlxc_namespaces.presence, "complex-presence")

    name = xso.Attr(
        "name",
    )

    jid_specific = xso.ChildList([
        SinglePresenceState,
    ])


class AccountsSettings(xso.XSO):
    TAG = (mlxc_namespaces.identity, "accounts")

    accounts = xso.ChildList([AccountSettings])
