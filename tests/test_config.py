import contextlib
import pathlib
import unittest
import unittest.mock
import traceback

import aioxmpp.callbacks
import aioxmpp.errors

import jclib.config as config

try:
    import xdg.BaseDirectory
    has_xdg = True
except:
    has_xdg = False


class Testescape_dirname(unittest.TestCase):
    def test_uses_urllib_quote(self):
        with unittest.mock.patch("urllib.parse.quote") as quote:
            path = config.escape_dirname("foo/bar baz")
        self.assertSequenceEqual(
            quote.mock_calls,
            [
                unittest.mock.call("foo/bar baz", safe=" ")
            ]
        )
        self.assertEqual(
            path,
            quote()
        )

    def test_safe_against_control_chars(self):
        self.assertEqual(
            "%00foo",
            config.escape_dirname("\x00foo")
        )

    def test_safe_against_slashes(self):
        self.assertEqual(
            "%2Ffoo",
            config.escape_dirname("/foo")
        )

    def test_safe_against_backslashes(self):
        self.assertEqual(
            "%5Cfoo",
            config.escape_dirname("\\foo")
        )

    def test_safe_against_colons(self):
        self.assertEqual(
            "%3Afoo",
            config.escape_dirname(":foo")
        )

    def test_not_escaping_spaces(self):
        self.assertEqual(
            " foo",
            config.escape_dirname(" foo")
        )


class Testunescape_dirname(unittest.TestCase):
    def test_inverse_operation_of_escape_dirname(self):
        tests = [
            "foo",
            "foo/bar/baz",
            "foo bar",
            "foo+bar",
            "foo%bar"
        ]

        for test in tests:
            self.assertEqual(
                test,
                config.unescape_dirname(config.escape_dirname(test))
            )


class TestConfigManager(unittest.TestCase):
    def setUp(self):
        self.uid = "urn:example:plugin"

        self.base = unittest.mock.Mock()
        self.base.pathprovider = unittest.mock.Mock([
            "site_config_dirs",
            "user_config_dir",
            "site_data_dirs",
            "user_data_dir",
        ])
        self.base.pathprovider.user_config_dir.return_value = unittest.mock.MagicMock()
        self.base.site1 = unittest.mock.MagicMock()
        self.base.site2 = unittest.mock.MagicMock()
        self.base.pathprovider.site_config_dirs.return_value = [
            self.base.site1,
            self.base.site2
        ]
        self.cm = config.ConfigManager(self.base.pathprovider)

    def test_get_config_paths(self):
        with unittest.mock.patch("jclib.config.escape_dirname") as escape_dirname:
            result = self.cm.get_config_paths(
                self.uid,
                "foo.xml"
            )

        escape_dirname.assert_called_with(self.uid)

        self.assertEqual(
            result,
            (
                self.base.pathprovider.user_config_dir() / escape_dirname() / "foo.xml",
                [
                    self.base.site2 / escape_dirname() / "foo.xml",
                    self.base.site1 / escape_dirname() / "foo.xml",
                ]
            )
        )

    def test_open_single_last_succeeds(self):
        f = object()
        uid, name = object(), object()

        with contextlib.ExitStack() as stack:
            get_config_paths = stack.enter_context(
                unittest.mock.patch.object(self.cm, "get_config_paths")
            )

            get_config_paths.return_value = (
                get_config_paths.p1,
                [
                    get_config_paths.p2,
                    get_config_paths.p3,
                ]
            )

            get_config_paths.p1.open.side_effect = FileNotFoundError()
            get_config_paths.p2.open.side_effect = PermissionError()
            get_config_paths.p3.open.return_value = f

            result = self.cm.open_single(uid, name)

        self.assertSequenceEqual(
            get_config_paths.mock_calls,
            [
                unittest.mock.call(uid, name),
                unittest.mock.call.p1.open("rb"),
                unittest.mock.call.p2.open("rb"),
                unittest.mock.call.p3.open("rb")
            ]
        )

        self.assertIs(result, f)

    def test_open_single_first_succeeds(self):
        f = object()
        uid, name = object(), object()

        with contextlib.ExitStack() as stack:
            get_config_paths = stack.enter_context(
                unittest.mock.patch.object(self.cm, "get_config_paths")
            )

            get_config_paths.return_value = (
                get_config_paths.p1,
                [
                    get_config_paths.p2,
                    get_config_paths.p3,
                ]
            )

            get_config_paths.p1.open.return_value = f
            get_config_paths.p2.open.side_effect = Exception()
            get_config_paths.p3.open.side_effect = Exception()

            result = self.cm.open_single(uid, name)

        self.assertSequenceEqual(
            get_config_paths.mock_calls,
            [
                unittest.mock.call(uid, name),
                unittest.mock.call.p1.open("rb"),
            ]
        )

        self.assertIs(result, f)

    def test_open_single_kwargs(self):
        f = object()
        uid, name, mode, encoding = object(), object(), object(), object()

        with contextlib.ExitStack() as stack:
            get_config_paths = stack.enter_context(
                unittest.mock.patch.object(self.cm, "get_config_paths")
            )
            is_write_mode = stack.enter_context(
                unittest.mock.patch("jclib.utils.is_write_mode")
            )
            is_write_mode.return_value = False

            get_config_paths.return_value = (
                get_config_paths.p1,
                [
                    get_config_paths.p2,
                    get_config_paths.p3,
                ]
            )

            get_config_paths.p1.open.side_effect = FileNotFoundError()
            get_config_paths.p2.open.side_effect = PermissionError()
            get_config_paths.p3.open.return_value = f

            result = self.cm.open_single(uid, name,
                                         mode=mode,
                                         encoding=encoding)

        self.assertSequenceEqual(
            get_config_paths.mock_calls,
            [
                unittest.mock.call(uid, name),
                unittest.mock.call.p1.open(mode, encoding=encoding),
                unittest.mock.call.p2.open(mode, encoding=encoding),
                unittest.mock.call.p3.open(mode, encoding=encoding)
            ]
        )

        self.assertIs(result, f)

    def test_open_single_with_writable_mode_creates_parent_directory(self):
        base = unittest.mock.Mock()

        f = object()
        uid, name, mode, encoding = object(), object(), object(), object()

        with contextlib.ExitStack() as stack:
            get_config_paths = stack.enter_context(
                unittest.mock.patch.object(
                    self.cm,
                    "get_config_paths",
                    new=base.get_config_paths)
            )
            mkdir_exist_ok = stack.enter_context(
                unittest.mock.patch(
                    "jclib.utils.mkdir_exist_ok",
                    new=base.mkdir_exist_ok)
            )
            is_write_mode = stack.enter_context(
                unittest.mock.patch("jclib.utils.is_write_mode")
            )
            is_write_mode.return_value = True

            get_config_paths.return_value = (
                base.p1,
                [
                    base.p2,
                    base.p3,
                ]
            )

            base.p1.open.return_value = f

            result = self.cm.open_single(uid, name,
                                         mode=mode,
                                         encoding=encoding)

        self.assertSequenceEqual(
            base.mock_calls,
            [
                unittest.mock.call.get_config_paths(uid, name),
                unittest.mock.call.mkdir_exist_ok(base.p1.parent),
                unittest.mock.call.p1.open(mode, encoding=encoding),
            ]
        )

        self.assertIs(result, f)

    def test_open_single_with_writable_mode_omits_site(self):
        base = unittest.mock.Mock()

        f = object()
        uid, name, mode, encoding = object(), object(), object(), object()

        with contextlib.ExitStack() as stack:
            get_config_paths = stack.enter_context(
                unittest.mock.patch.object(
                    self.cm,
                    "get_config_paths",
                    new=base.get_config_paths)
            )
            mkdir_exist_ok = stack.enter_context(
                unittest.mock.patch(
                    "jclib.utils.mkdir_exist_ok",
                    new=base.mkdir_exist_ok)
            )
            is_write_mode = stack.enter_context(
                unittest.mock.patch("jclib.utils.is_write_mode")
            )
            is_write_mode.return_value = True

            get_config_paths.return_value = (
                base.p1,
                [
                    base.p2,
                    base.p3,
                ]
            )

            exc = OSError()
            base.p1.open.side_effect = exc

            with self.assertRaises(OSError) as ctx:
                self.cm.open_single(uid, name,
                                    mode=mode,
                                    encoding=encoding)
            self.assertIs(ctx.exception, exc)

        self.assertSequenceEqual(
            base.mock_calls,
            [
                unittest.mock.call.get_config_paths(uid, name),
                unittest.mock.call.mkdir_exist_ok(base.p1.parent),
                unittest.mock.call.p1.open(mode, encoding=encoding),
            ]
        )

    def test_open_single_none_succeeds(self):
        f = object()
        uid, name = object(), object()

        with contextlib.ExitStack() as stack:
            get_config_paths = stack.enter_context(
                unittest.mock.patch.object(self.cm, "get_config_paths")
            )

            get_config_paths.return_value = (
                get_config_paths.p1,
                [
                    get_config_paths.p2,
                    get_config_paths.p3,
                ]
            )

            excs = [OSError() for i in range(3)]
            get_config_paths.p1.open.side_effect = excs[0]
            get_config_paths.p2.open.side_effect = excs[1]
            get_config_paths.p3.open.side_effect = excs[2]

            with self.assertRaises(aioxmpp.errors.MultiOSError) as ctx:
                self.cm.open_single(uid, name)

            self.assertSequenceEqual(
                ctx.exception.exceptions,
                excs
            )

        self.assertSequenceEqual(
            get_config_paths.mock_calls,
            [
                unittest.mock.call(uid, name),
                unittest.mock.call.p1.open("rb"),
                unittest.mock.call.p2.open("rb"),
                unittest.mock.call.p3.open("rb"),
            ]
        )

    def test_open_incremental_some_succeed(self):
        f1, f2 = object(), object()
        uid, name = object(), object()

        with contextlib.ExitStack() as stack:
            get_config_paths = stack.enter_context(
                unittest.mock.patch.object(self.cm, "get_config_paths")
            )

            get_config_paths.return_value = (
                get_config_paths.p1,
                [
                    get_config_paths.p2,
                    get_config_paths.p3,
                ]
            )

            get_config_paths.p1.open.return_value = f1
            get_config_paths.p2.open.side_effect = OSError()
            get_config_paths.p3.open.return_value = f2

            result = list(self.cm.open_incremental(uid, name))

        self.assertSequenceEqual(
            get_config_paths.mock_calls,
            [
                unittest.mock.call(uid, name),
                unittest.mock.call.p3.open("rb"),
                unittest.mock.call.p2.open("rb"),
                unittest.mock.call.p1.open("rb"),
            ]
        )

        self.assertSequenceEqual(
            result,
            [
                (f2, True),
                (f1, False)
            ]
        )

    def test_open_incremental_kwargs(self):
        f1, f2 = object(), object()
        uid, name, mode, encoding = object(), object(), object(), object()

        with contextlib.ExitStack() as stack:
            get_config_paths = stack.enter_context(
                unittest.mock.patch.object(self.cm, "get_config_paths")
            )
            is_write_mode = stack.enter_context(
                unittest.mock.patch("jclib.utils.is_write_mode")
            )
            is_write_mode.return_value = False

            get_config_paths.return_value = (
                get_config_paths.p1,
                [
                    get_config_paths.p2,
                    get_config_paths.p3,
                ]
            )

            get_config_paths.p1.open.return_value = f1
            get_config_paths.p2.open.side_effect = OSError()
            get_config_paths.p3.open.return_value = f2

            result = list(self.cm.open_incremental(uid, name,
                                                   mode=mode,
                                                   encoding=encoding))

        self.assertSequenceEqual(
            get_config_paths.mock_calls,
            [
                unittest.mock.call(uid, name),
                unittest.mock.call.p3.open(mode, encoding=encoding),
                unittest.mock.call.p2.open(mode, encoding=encoding),
                unittest.mock.call.p1.open(mode, encoding=encoding),
            ]
        )

        self.assertSequenceEqual(
            result,
            [
                (f2, True),
                (f1, False)
            ]
        )

    def test_open_incremental_omits_site_dirs_on_write_mode(self):
        f1, f2 = object(), object()
        uid, name, mode, encoding = object(), object(), object(), object()

        with contextlib.ExitStack() as stack:
            get_config_paths = stack.enter_context(
                unittest.mock.patch.object(self.cm, "get_config_paths")
            )
            is_write_mode = stack.enter_context(
                unittest.mock.patch("jclib.utils.is_write_mode")
            )
            is_write_mode.return_value = True

            get_config_paths.return_value = (
                get_config_paths.p1,
                [
                    get_config_paths.p2,
                    get_config_paths.p3,
                ]
            )

            get_config_paths.p1.open.return_value = f1

            result = list(self.cm.open_incremental(uid, name,
                                                   mode=mode,
                                                   encoding=encoding))

        self.assertSequenceEqual(
            get_config_paths.mock_calls,
            [
                unittest.mock.call(uid, name),
                unittest.mock.call.p1.open(mode, encoding=encoding),
            ]
        )

        self.assertSequenceEqual(
            result,
            [
                (f1, False)
            ]
        )

    def test_open_incremental_none_succeed(self):
        f1, f2 = object(), object()
        uid, name = object(), object()

        with contextlib.ExitStack() as stack:
            get_config_paths = stack.enter_context(
                unittest.mock.patch.object(self.cm, "get_config_paths")
            )

            get_config_paths.return_value = (
                get_config_paths.p1,
                [
                    get_config_paths.p2,
                    get_config_paths.p3,
                ]
            )

            get_config_paths.p1.open.side_effect = OSError()
            get_config_paths.p2.open.side_effect = OSError()
            get_config_paths.p3.open.side_effect = OSError()

            result = list(self.cm.open_incremental(uid, name))

        self.assertSequenceEqual(
            get_config_paths.mock_calls,
            [
                unittest.mock.call(uid, name),
                unittest.mock.call.p3.open("rb"),
                unittest.mock.call.p2.open("rb"),
                unittest.mock.call.p1.open("rb"),
            ]
        )

        self.assertSequenceEqual(
            result,
            [
            ]
        )

    def test_load_incremental(self):
        self.base.f1 = unittest.mock.MagicMock()
        self.base.f2 = unittest.mock.MagicMock()
        uid, filename = object(), object()
        with contextlib.ExitStack() as stack:
            open_incremental = stack.enter_context(
                unittest.mock.patch.object(self.cm,
                                           "open_incremental")
            )
            open_incremental.return_value = [
                (self.base.f1, True),
                (self.base.f2, False),
            ]

            self.cm.load_incremental(uid, filename, self.base.callback)

        open_incremental.assert_called_with(uid, filename)

        calls = list(self.base.mock_calls)
        self.assertSequenceEqual(
            calls,
            [
                unittest.mock.call.f1.__enter__(),
                unittest.mock.call.callback(self.base.f1, True),
                unittest.mock.call.f1.__exit__(None, None, None),
                unittest.mock.call.f2.__enter__(),
                unittest.mock.call.callback(self.base.f2, False),
                unittest.mock.call.f2.__exit__(None, None, None),
            ]
        )

    def test_on_writeback(self):
        self.assertIsInstance(
            config.ConfigManager.on_writeback,
            aioxmpp.callbacks.Signal
        )

    def test_writeback(self):
        cb = unittest.mock.Mock()
        cb.return_value = True
        self.cm.on_writeback.connect(cb)

        self.cm.writeback()

        cb.assert_called_with()

    def tearDown(self):
        del self.cm


@unittest.skipIf(not has_xdg, "pyxdg not installed")
class TestXDGProvider_Functional(unittest.TestCase):
    def setUp(self):
        self.p = config.XDGProvider("appname")

    def test_user_config_dir(self):
        with unittest.mock.patch("xdg.BaseDirectory.xdg_config_home",
                                 new="/path/to/config_home") as xdg_config_home:
            result = self.p.user_config_dir()
        self.assertEqual(
            result,
            pathlib.Path(xdg_config_home) / self.p.appname
        )

    def test_site_config_dirs(self):
        with unittest.mock.patch("xdg.BaseDirectory.xdg_config_dirs",
                                 new=["/path/to/config_home",
                                      "/etc/foo",
                                      "/etc/bar"]) as xdg_config_dirs:
            result = list(self.p.site_config_dirs())
        self.assertEqual(
            result,
            [
                pathlib.Path("/etc/foo") / self.p.appname,
                pathlib.Path("/etc/bar") / self.p.appname,
            ]
        )

    def test_user_data_dir(self):
        with unittest.mock.patch("xdg.BaseDirectory.xdg_data_home",
                                 new="/path/to/data_home") as xdg_data_home:
            result = self.p.user_data_dir()
        self.assertEqual(
            result,
            pathlib.Path(xdg_data_home) / self.p.appname
        )

    def test_site_data_dirs(self):
        with unittest.mock.patch("xdg.BaseDirectory.xdg_data_dirs",
                                 new=["/path/to/data_home",
                                      "/usr/foo",
                                      "/usr/bar"]) as xdg_config_dirs:
            result = list(self.p.site_data_dirs())
        self.assertEqual(
            result,
            [
                pathlib.Path("/usr/foo") / self.p.appname,
                pathlib.Path("/usr/bar") / self.p.appname,
            ]
        )

    def tearDown(self):
        del self.p


@unittest.skipIf(has_xdg, "pyxdg available")
class TestXDGProvider_NonFunctional(unittest.TestCase):
    def test_raises_on_init(self):
        with self.assertRaises(ImportError):
            config.XDGProvider("appname")


class Testglobals(unittest.TestCase):
    def test_UNIX_APPNAME(self):
        self.assertEqual(
            config.UNIX_APPNAME,
            "jabbercat.org"
        )


class Testmake_config_manager(unittest.TestCase):
    def test_uses_XDGProvider_if_available(self):
        with contextlib.ExitStack() as stack:
            XDGProvider = stack.enter_context(
                unittest.mock.patch("jclib.config.XDGProvider")
            )
            ConfigManager = stack.enter_context(
                unittest.mock.patch("jclib.config.ConfigManager")
            )

            result = config.make_config_manager()

        XDGProvider.assert_called_with(config.UNIX_APPNAME)
        ConfigManager.assert_called_with(XDGProvider())

        self.assertEqual(
            result,
            ConfigManager()
        )

    def test_raises_RuntimeError_if_all_providers_fail(self):
        with contextlib.ExitStack() as stack:
            XDGProvider = stack.enter_context(
                unittest.mock.patch("jclib.config.XDGProvider")
            )
            XDGProvider.side_effect = ImportError()

            with self.assertRaisesRegexp(RuntimeError,
                                         "no path provider for platform"):
                config.make_config_manager()
