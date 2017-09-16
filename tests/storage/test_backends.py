import pathlib
import itertools
import unittest
import unittest.mock

import jclib.storage.backends as backends


class TestXDGBackend(unittest.TestCase):
    def setUp(self):
        self.appname = unittest.mock.MagicMock()
        self.b = backends.XDGBackend(self.appname)
        self.mock = unittest.mock.Mock()

        self.mock.xdg_data_dirs = [
            self.mock.xdg_data_dir1,
            self.mock.xdg_data_dir2,
        ]

        self.mock.xdg_config_dirs = [
            self.mock.xdg_config_dir1,
            self.mock.xdg_config_dir2,
        ]

        self.patchers = []
        for name in ["cache_home", "data_home", "config_home",
                     "data_dirs", "config_dirs"]:
            self.patchers.append(
                unittest.mock.patch(
                    "xdg.BaseDirectory.xdg_{}".format(name),
                    new=getattr(self.mock, "xdg_{}".format(name))
                )
            )

        self.patchers.append(
            unittest.mock.patch("pathlib.Path", new=self.mock.Path)
        )

        for patcher in self.patchers:
            patcher.start()

    def tearDown(self):
        for patcher in self.patchers:
            patcher.stop()

    def test_type_base_paths_cache_writable(self):
        result = self.b.type_base_paths(backends.StorageType.CACHE, True)
        self.mock.Path.assert_called_once_with(self.mock.xdg_cache_home)
        self.appname.__rtruediv__.assert_called_once_with(self.mock.Path())
        self.assertEqual(result, [self.appname.__rtruediv__()])

    def test_type_base_paths_cache_readable(self):
        result = self.b.type_base_paths(backends.StorageType.CACHE, False)
        self.mock.Path.assert_called_once_with(self.mock.xdg_cache_home)
        self.appname.__rtruediv__.assert_called_once_with(self.mock.Path())
        self.assertEqual(result, [self.appname.__rtruediv__()])

    def test_type_base_paths_data_writable(self):
        result = self.b.type_base_paths(backends.StorageType.DATA, True)
        self.mock.Path.assert_called_once_with(self.mock.xdg_data_home)
        self.appname.__rtruediv__.assert_called_once_with(self.mock.Path())
        self.assertEqual(result, [self.appname.__rtruediv__()])

    def test_type_base_paths_data_readable(self):
        def generate_results(prefix):
            for i in itertools.count():
                yield getattr(unittest.mock.sentinel, "{}{}".format(prefix, i))

        pathlib.Path.side_effect = generate_results("Path")
        self.appname.__rtruediv__.side_effect = generate_results("appnamed")

        result = self.b.type_base_paths(backends.StorageType.DATA, False)

        self.assertCountEqual(
            self.mock.Path.mock_calls,
            [
                unittest.mock.call(self.mock.xdg_data_dir1),
                unittest.mock.call(self.mock.xdg_data_dir2),
            ]
        )

        self.assertCountEqual(
            self.appname.__rtruediv__.mock_calls,
            [
                unittest.mock.call(unittest.mock.sentinel.Path0),
                unittest.mock.call(unittest.mock.sentinel.Path1),
            ]
        )

        self.assertSequenceEqual(
            result,
            [
                unittest.mock.sentinel.appnamed0,
                unittest.mock.sentinel.appnamed1,
            ]
        )

    def test_type_base_paths_config_writable(self):
        result = self.b.type_base_paths(backends.StorageType.CONFIG, True)
        self.mock.Path.assert_called_once_with(self.mock.xdg_config_home)
        self.appname.__rtruediv__.assert_called_once_with(self.mock.Path())
        self.assertEqual(result, [self.appname.__rtruediv__()])

    def test_type_base_paths_config_readable(self):
        def generate_results(prefix):
            for i in itertools.count():
                yield getattr(unittest.mock.sentinel, "{}{}".format(prefix, i))

        pathlib.Path.side_effect = generate_results("Path")
        self.appname.__rtruediv__.side_effect = generate_results("appnamed")

        result = self.b.type_base_paths(backends.StorageType.CONFIG, False)

        self.assertCountEqual(
            self.mock.Path.mock_calls,
            [
                unittest.mock.call(self.mock.xdg_config_dir1),
                unittest.mock.call(self.mock.xdg_config_dir2),
            ]
        )

        self.assertCountEqual(
            self.appname.__rtruediv__.mock_calls,
            [
                unittest.mock.call(unittest.mock.sentinel.Path0),
                unittest.mock.call(unittest.mock.sentinel.Path1),
            ]
        )

        self.assertSequenceEqual(
            result,
            [
                unittest.mock.sentinel.appnamed0,
                unittest.mock.sentinel.appnamed1,
            ]
        )
