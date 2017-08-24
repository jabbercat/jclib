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
