import unittest.mock

import mlxc.client
import mlxc.roster


class ClientMock(unittest.mock.Mock):
    def __init__(self):
        super().__init__([])
        self.accounts = mlxc.client.AccountManager()
        self.roster = mlxc.roster.Tree()
