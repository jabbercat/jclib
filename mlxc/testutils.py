import unittest.mock

import aioxmpp.callbacks

import mlxc.client
import mlxc.roster


class ClientMock(unittest.mock.Mock):
    def __init__(self, **kwargs):
        super().__init__(["account_state"], **kwargs)
        self.accounts = mlxc.client.AccountManager()
        self.config_manager = unittest.mock.MagicMock()
        self.config_manager.on_writeback = aioxmpp.callbacks.AdHocSignal()
        self.roster = mlxc.roster.Tree()
        self.on_account_enabling = aioxmpp.callbacks.AdHocSignal()
        self.on_account_disabling = aioxmpp.callbacks.AdHocSignal()
        self.on_loaded = aioxmpp.callbacks.AdHocSignal()
