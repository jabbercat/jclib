import unittest

import mlxc.xdginfo


class TestRESOURCE(unittest.TestCase):
    def test_value(self):
        self.assertEqual(
            mlxc.xdginfo.RESOURCE,
            ("zombofant.net", "mlxc")
        )
