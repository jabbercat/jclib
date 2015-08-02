import asyncio
import contextlib
import os.path
import unittest
import unittest.mock
import xml.sax.handler

import xdg.BaseDirectory

import aioxmpp.errors
import aioxmpp.utils as aioxmpp_utils

import mlxc.utils as utils


class Test_imports_from_aioxmpp(unittest.TestCase):
    def test_imports(self):
        self.assertIs(
            utils.namespaces,
            aioxmpp_utils.namespaces
        )


class Testmlxc_namespaces(unittest.TestCase):
    def test_account_namespace(self):
        self.assertEqual(
            "https://xmlns.zombofant.net/mlxc/core/account/1.0",
            utils.mlxc_namespaces.account
        )

    def test_roster_namespace(self):
        self.assertEqual(
            "https://xmlns.zombofant.net/mlxc/core/roster/1.0",
            utils.mlxc_namespaces.roster
        )


class Testmultiopen(unittest.TestCase):
    def setUp(self):
        self.paths = [
            "/foo/bar",
            "/baz",
            "/fnord",
        ]

    def test_first_success(self):
        mode = object()
        encoding = object()
        obj = object()

        with contextlib.ExitStack() as stack:
            open_ = stack.enter_context(unittest.mock.patch(
                "builtins.open"
            ))
            open_.return_value = obj

            result = utils.multiopen(
                self.paths,
                "foo.xml",
                mode,
                encoding=encoding)

        self.assertIs(
            result,
            obj)

        self.assertSequenceEqual(
            open_.mock_calls,
            [
                unittest.mock.call(
                    os.path.join(self.paths[0], "foo.xml"),
                    mode,
                    encoding=encoding)
            ]
        )

    def test_tries_and_returns_first_success(self):
        mode = object()
        encoding = object()
        obj = object()

        excs = [FileNotFoundError() for i in range(len(self.paths)-1)]
        excs_to_use = list(excs)
        call_rec = unittest.mock.Mock()

        def open_mock(*args, **kwargs):
            call_rec(*args, **kwargs)
            if excs_to_use:
                raise excs_to_use.pop(0)
            return obj

        with contextlib.ExitStack() as stack:
            open_ = stack.enter_context(unittest.mock.patch(
                "builtins.open",
                open_mock
            ))

            result = utils.multiopen(
                self.paths,
                "foo.xml",
                mode,
                encoding=encoding)

        self.assertSequenceEqual(
            call_rec.mock_calls,
            [
                unittest.mock.call(
                    os.path.join(path, "foo.xml"),
                    mode,
                    encoding=encoding)
                for path in self.paths
            ]
        )


class Testxdgopen_generic(unittest.TestCase):
    def test_open_r(self):
        paths = ["/foo/bar", "/fnord", "/baz"]

        base = unittest.mock.Mock()
        base.load_paths.return_value = iter(paths)
        resource = ["foo", "bar"]
        encoding = object()

        with unittest.mock.patch("mlxc.utils.multiopen") as multiopen:
            utils.xdgopen_generic(
                resource,
                "foo.xml",
                "rb",
                load_paths=base.load_paths,
                save_path=base.save_path,
                encoding=encoding
            )

        self.assertSequenceEqual(
            base.mock_calls,
            [
                unittest.mock.call.load_paths(*resource),
            ]
        )

        self.assertSequenceEqual(
            multiopen.mock_calls,
            [
                unittest.mock.call(
                    list(reversed(paths)),
                    "foo.xml",
                    mode="rb",
                    encoding=encoding
                )
            ]
        )

    def test_open_w(self):
        path = "/foo/bar"

        base = unittest.mock.Mock()
        base.save_path.return_value = path
        resource = ["foo", "bar"]
        encoding = object()

        with unittest.mock.patch("builtins.open") as open_:
            utils.xdgopen_generic(
                resource,
                "foo.xml",
                "wb",
                load_paths=base.load_paths,
                save_path=base.save_path,
                encoding=encoding
            )

        self.assertSequenceEqual(
            base.mock_calls,
            [
                unittest.mock.call.save_path(*resource),
            ]
        )

        self.assertSequenceEqual(
            open_.mock_calls,
            [
                unittest.mock.call(
                    os.path.join(path, "foo.xml"),
                    mode="wb",
                    encoding=encoding
                )
            ]
        )

    def test_open_a(self):
        path = "/foo/bar"

        base = unittest.mock.Mock()
        base.save_path.return_value = path
        resource = ["foo", "bar"]
        encoding = object()

        with unittest.mock.patch("builtins.open") as open_:
            utils.xdgopen_generic(
                resource,
                "foo.xml",
                "ab",
                load_paths=base.load_paths,
                save_path=base.save_path,
                encoding=encoding
            )

        self.assertSequenceEqual(
            base.mock_calls,
            [
                unittest.mock.call.save_path(*resource),
            ]
        )

        self.assertSequenceEqual(
            open_.mock_calls,
            [
                unittest.mock.call(
                    os.path.join(path, "foo.xml"),
                    mode="ab",
                    encoding=encoding
                )
            ]
        )

    def test_open_rplus(self):
        path = "/foo/bar"

        base = unittest.mock.Mock()
        base.save_path.return_value = path
        resource = ["foo", "bar"]
        encoding = object()

        with unittest.mock.patch("builtins.open") as open_:
            utils.xdgopen_generic(
                resource,
                "foo.xml",
                "r+b",
                load_paths=base.load_paths,
                save_path=base.save_path,
                encoding=encoding
            )

        self.assertSequenceEqual(
            base.mock_calls,
            [
                unittest.mock.call.save_path(*resource),
            ]
        )

        self.assertSequenceEqual(
            open_.mock_calls,
            [
                unittest.mock.call(
                    os.path.join(path, "foo.xml"),
                    mode="r+b",
                    encoding=encoding
                )
            ]
        )


class Testxdgconfigopen(unittest.TestCase):
    def test_delegate_to_xdgopen_generic(self):
        mode = "fnord"
        encoding = object()
        resource = object()

        with unittest.mock.patch(
                "mlxc.utils.xdgopen_generic"
        ) as xdgopen_generic:
            utils.xdgconfigopen(resource, "baz.xml",
                                mode=mode,
                                encoding=encoding)

        self.assertSequenceEqual(
            xdgopen_generic.mock_calls,
            [
                unittest.mock.call(
                    resource,
                    "baz.xml",
                    mode,
                    xdg.BaseDirectory.load_config_paths,
                    xdg.BaseDirectory.save_config_path,
                    encoding=encoding
                )
            ]
        )


class Testxdgdataopen(unittest.TestCase):
    def test_delegate_to_xdgopen_generic(self):
        mode = "fnord"
        encoding = object()
        resource = object()

        with unittest.mock.patch(
                "mlxc.utils.xdgopen_generic"
        ) as xdgopen_generic:
            utils.xdgdataopen(resource, "baz.xml",
                              mode=mode,
                              encoding=encoding)

        self.assertSequenceEqual(
            xdgopen_generic.mock_calls,
            [
                unittest.mock.call(
                    resource,
                    "baz.xml",
                    mode,
                    xdg.BaseDirectory.load_data_paths,
                    xdg.BaseDirectory.save_data_path,
                    encoding=encoding
                )
            ]
        )


class Testwrite_xso(unittest.TestCase):
    def test_write_to_io(self):
        base = unittest.mock.Mock()

        instance = base.XMPPXMLGenerator()
        base.mock_calls.clear()

        dest = base.dest
        xso = base.xso

        with unittest.mock.patch(
                "aioxmpp.xml.XMPPXMLGenerator",
                new=base.XMPPXMLGenerator
        ) as XMPPXMLGenerator:
            utils.write_xso(dest, xso)

        self.assertSequenceEqual(
            base.mock_calls,
            [
                unittest.mock.call.XMPPXMLGenerator(
                    out=dest,
                    short_empty_elements=True),
                unittest.mock.call.XMPPXMLGenerator().startDocument(),
                unittest.mock.call.XMPPXMLGenerator().characters("\n"),
                unittest.mock.call.xso.unparse_to_sax(
                    instance
                ),
                unittest.mock.call.XMPPXMLGenerator().characters("\n"),
                unittest.mock.call.XMPPXMLGenerator().endDocument()
            ]
        )


class Testread_xso(unittest.TestCase):
    def test_read_from_io(self):
        base = unittest.mock.Mock()

        xso_parser = base.XSOParser()
        sax_driver = base.SAXDriver()

        base.mock_calls.clear()

        with contextlib.ExitStack() as stack:
            XSOParser = stack.enter_context(unittest.mock.patch(
                "aioxmpp.xso.XSOParser",
                base.XSOParser
            ))
            SAXDriver = stack.enter_context(unittest.mock.patch(
                "aioxmpp.xso.SAXDriver",
                base.SAXDriver
            ))
            make_parser = stack.enter_context(unittest.mock.patch(
                "xml.sax.make_parser",
                base.make_parser
            ))

            utils.read_xso(base.src, {
                base.A: base.cb,
            })

        self.assertSequenceEqual(
            base.mock_calls,
            [
                unittest.mock.call.XSOParser(),
                unittest.mock.call.XSOParser().add_class(
                    base.A,
                    base.cb
                ),
                unittest.mock.call.SAXDriver(xso_parser),
                unittest.mock.call.make_parser(),
                unittest.mock.call.make_parser().setFeature(
                    xml.sax.handler.feature_namespaces,
                    True),
                unittest.mock.call.make_parser().setFeature(
                    xml.sax.handler.feature_external_ges,
                    False),
                unittest.mock.call.make_parser().setContentHandler(
                    sax_driver),
                unittest.mock.call.make_parser().parse(base.src)
            ]
        )


class Testlogged_async(unittest.TestCase):
    def test_attaches_log_function(self):
        base = unittest.mock.Mock()

        loop = object()
        coro = object()
        name = object()
        with contextlib.ExitStack() as stack:
            async = stack.enter_context(unittest.mock.patch(
                "asyncio.async",
                new=base.async
            ))

            partial = stack.enter_context(unittest.mock.patch(
                "functools.partial",
                new=base.partial
            ))

            task = utils.logged_async(coro, loop=loop, name=name)

        calls = list(base.mock_calls)
        self.assertSequenceEqual(
            calls,
            [
                unittest.mock.call.async(coro, loop=loop),
                unittest.mock.call.partial(
                    utils._logged_task_done,
                    name=name),
                unittest.mock.call.async().add_done_callback(
                    partial()
                ),
            ]
        )

        self.assertEqual(
            task,
            async()
        )

    def test_uses_current_event_loop_as_default(self):
        base = unittest.mock.Mock()

        coro = object()
        with contextlib.ExitStack() as stack:
            async = stack.enter_context(unittest.mock.patch(
                "asyncio.async",
                new=base.async
            ))

            partial = stack.enter_context(unittest.mock.patch(
                "functools.partial",
                new=base.partial
            ))

            get_event_loop = stack.enter_context(unittest.mock.patch(
                "asyncio.get_event_loop",
                new=base.get_event_loop
            ))

            task = utils.logged_async(coro)

        calls = list(base.mock_calls)
        self.assertSequenceEqual(
            calls,
            [
                unittest.mock.call.get_event_loop(),
                unittest.mock.call.async(coro, loop=get_event_loop()),
                unittest.mock.call.partial(
                    utils._logged_task_done,
                    name=async(),
                ),
                unittest.mock.call.async().add_done_callback(
                    partial()
                ),
            ]
        )

        self.assertEqual(
            task,
            async()
        )

    def test_logged_task_done_no_exception(self):
        name = object()

        task = unittest.mock.Mock()

        with unittest.mock.patch("mlxc.utils.logger") as logger:
            utils._logged_task_done(task, name=name)

        self.assertSequenceEqual(
            logger.mock_calls,
            [
                unittest.mock.call.info("task %s returned a value: %r",
                                        name, task.result())
            ]
        )

    def test_logged_task_done_cancelled(self):
        name = object()

        task = unittest.mock.Mock()
        task.result.side_effect = asyncio.CancelledError()

        with unittest.mock.patch("mlxc.utils.logger") as logger:
            utils._logged_task_done(task, name=name)

        self.assertSequenceEqual(
            logger.mock_calls,
            [
                unittest.mock.call.debug("task %s cancelled",
                                         name)
            ]
        )

    def test_logged_task_done_exception(self):
        name = object()

        task = unittest.mock.Mock()
        task.result.side_effect = Exception()

        with unittest.mock.patch("mlxc.utils.logger") as logger:
            utils._logged_task_done(task, name=name)

        self.assertSequenceEqual(
            logger.mock_calls,
            [
                unittest.mock.call.exception("task %s failed",
                                             name)
            ]
        )


# foo
