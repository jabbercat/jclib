import asyncio
import contextlib
import signal
import socket
import stat
import unittest
import unittest.mock

from aioxmpp.testutils import (
    run_coroutine,
    CoroutineMock
)

import mlxc.main as main
import mlxc.xdginfo as xdginfo


skip_without_unix = unittest.skipUnless(
    hasattr(asyncio.get_event_loop(),  "create_unix_server"),
    "requires event loop with unix socket support"
)

skip_with_unix = unittest.skipIf(
    hasattr(asyncio.get_event_loop(),  "create_unix_server"),
    "requires event loop WITHOUT unix socket support"
)

@skip_without_unix
class Test_UnixGlobalSingleton(unittest.TestCase):
    def setUp(self):
        self.loop = asyncio.get_event_loop()
        self.singleton = main._UnixGlobalSingleton(self.loop)

    def test_init(self):
        self.assertIs(
            self.singleton.listener,
            None
        )
        self.assertIs(
            self.singleton.socket_path,
            None
        )

    def test_get_socket_path_uses_xdg_runtime_dir(self):
        with contextlib.ExitStack() as stack:
            get_runtime_dir = stack.enter_context(unittest.mock.patch(
                "xdg.BaseDirectory.get_runtime_dir"
            ))
            join = stack.enter_context(unittest.mock.patch(
                "os.path.join"
            ))

            path = main._UnixGlobalSingleton.get_socket_path()

        self.assertSequenceEqual(
            get_runtime_dir.mock_calls,
            [
                unittest.mock.call()
            ]
        )

        self.assertSequenceEqual(
            join.mock_calls,
            [
                unittest.mock.call(get_runtime_dir(), *xdginfo.RESOURCE)
            ]
        )

        self.assertEqual(
            path,
            join()
        )

    def test_bind_socket(self):
        path = object()
        base = unittest.mock.Mock()

        with contextlib.ExitStack() as stack:
            socket_socket = stack.enter_context(unittest.mock.patch(
                "socket.socket",
                new=base.socket
            ))
            chmod = stack.enter_context(unittest.mock.patch(
                "os.chmod",
                new=base.chmod
            ))
            makedirs = stack.enter_context(unittest.mock.patch(
                "os.makedirs",
                new=base.makedirs
            ))
            dirname = stack.enter_context(unittest.mock.patch(
                "os.path.dirname",
                new=base.dirname
            ))

            sock = main._UnixGlobalSingleton.bind_socket(path)

        calls = list(base.mock_calls)
        self.assertSequenceEqual(
            calls,
            [
                unittest.mock.call.dirname(path),
                unittest.mock.call.makedirs(
                    dirname(),
                    mode=0o700),
                unittest.mock.call.socket(socket.AF_UNIX,
                                          socket.SOCK_STREAM),
                unittest.mock.call.socket().fileno(),
                unittest.mock.call.chmod(socket_socket().fileno(),
                                         stat.S_ISVTX | stat.S_IRWXU),
                unittest.mock.call.socket().bind(path),
            ]
        )

        self.assertEqual(
            socket_socket(),
            sock
        )

    def test_bind_socket_closes_and_reraises_on_error_in_chmod(self):
        path = object()
        base = unittest.mock.Mock()

        with contextlib.ExitStack() as stack:
            socket_socket = stack.enter_context(unittest.mock.patch(
                "socket.socket",
                new=base.socket
            ))
            chmod = stack.enter_context(unittest.mock.patch(
                "os.chmod",
                new=base.chmod
            ))
            makedirs = stack.enter_context(unittest.mock.patch(
                "os.makedirs",
                new=base.makedirs
            ))
            dirname = stack.enter_context(unittest.mock.patch(
                "os.path.dirname",
                new=base.dirname
            ))

            exc = OSError()

            chmod.side_effect = exc

            with self.assertRaises(OSError) as ctx:
                sock = main._UnixGlobalSingleton.bind_socket(path)

        self.assertIs(
            ctx.exception,
            exc
        )

        calls = list(base.mock_calls)
        self.assertSequenceEqual(
            calls,
            [
                unittest.mock.call.dirname(path),
                unittest.mock.call.makedirs(
                    dirname(),
                    mode=0o700),
                unittest.mock.call.socket(socket.AF_UNIX,
                                          socket.SOCK_STREAM),
                unittest.mock.call.socket().fileno(),
                unittest.mock.call.chmod(socket_socket().fileno(),
                                         stat.S_ISVTX | stat.S_IRWXU),
                unittest.mock.call.socket().close(),
            ]
        )

    def test_bind_socket_closes_and_reraises_on_error_in_chmod(self):
        path = object()
        base = unittest.mock.Mock()

        with contextlib.ExitStack() as stack:
            socket_socket = stack.enter_context(unittest.mock.patch(
                "socket.socket",
                new=base.socket
            ))
            chmod = stack.enter_context(unittest.mock.patch(
                "os.chmod",
                new=base.chmod
            ))
            makedirs = stack.enter_context(unittest.mock.patch(
                "os.makedirs",
                new=base.makedirs
            ))
            dirname = stack.enter_context(unittest.mock.patch(
                "os.path.dirname",
                new=base.dirname
            ))

            exc = OSError()

            socket_socket().bind.side_effect = exc

            base.mock_calls.clear()

            with self.assertRaises(OSError) as ctx:
                sock = main._UnixGlobalSingleton.bind_socket(path)

        self.assertIs(
            ctx.exception,
            exc
        )

        calls = list(base.mock_calls)
        self.assertSequenceEqual(
            calls,
            [
                unittest.mock.call.dirname(path),
                unittest.mock.call.makedirs(
                    dirname(),
                    mode=0o700),
                unittest.mock.call.socket(socket.AF_UNIX,
                                          socket.SOCK_STREAM),
                unittest.mock.call.socket().fileno(),
                unittest.mock.call.chmod(socket_socket().fileno(),
                                         stat.S_ISVTX | stat.S_IRWXU),
                unittest.mock.call.socket().bind(path),
                unittest.mock.call.socket().close(),
            ]
        )

    def test_start_returns_true_on_success(self):
        base = unittest.mock.Mock()

        with contextlib.ExitStack() as stack:
            get_socket_path = stack.enter_context(unittest.mock.patch.object(
                self.singleton,
                "get_socket_path",
                new=base.get_socket_path
            ))

            bind_socket = stack.enter_context(unittest.mock.patch.object(
                self.singleton,
                "bind_socket",
                new=base.bind_socket
            ))

            join = stack.enter_context(unittest.mock.patch(
                "os.path.join",
                new=base.join
            ))

            base.start_unix_server = CoroutineMock()
            start_unix_server = stack.enter_context(unittest.mock.patch(
                "asyncio.start_unix_server",
                new=base.start_unix_server
            ))

            result = run_coroutine(self.singleton.start())

        calls = list(base.mock_calls)

        self.assertSequenceEqual(
            calls,
            [
                unittest.mock.call.get_socket_path(),
                unittest.mock.call.join(
                    get_socket_path(),
                    "singletonify.sock"),
                unittest.mock.call.bind_socket(join()),
                unittest.mock.call.start_unix_server(
                    unittest.mock.ANY,
                    sock=bind_socket(),
                    loop=self.loop)
            ]
        )

        self.assertIs(
            result,
            True
        )

        self.assertIs(
            self.singleton.listener,
            run_coroutine(start_unix_server())
        )

        self.assertEqual(
            self.singleton.socket_path,
            join()
        )

    def test_start_returns_false_on_os_error_in_bind(self):
        base = unittest.mock.Mock()

        with contextlib.ExitStack() as stack:
            get_socket_path = stack.enter_context(unittest.mock.patch.object(
                self.singleton,
                "get_socket_path",
                new=base.get_socket_path
            ))

            bind_socket = stack.enter_context(unittest.mock.patch.object(
                self.singleton,
                "bind_socket",
                new=base.bind_socket
            ))
            bind_socket.side_effect = OSError()

            join = stack.enter_context(unittest.mock.patch(
                "os.path.join",
                new=base.join
            ))

            base.start_unix_server = CoroutineMock()
            start_unix_server = stack.enter_context(unittest.mock.patch(
                "asyncio.start_unix_server",
                new=base.start_unix_server
            ))

            result = run_coroutine(self.singleton.start())

        calls = list(base.mock_calls)

        self.assertSequenceEqual(
            calls,
            [
                unittest.mock.call.get_socket_path(),
                unittest.mock.call.join(
                    get_socket_path(),
                    "singletonify.sock"),
                unittest.mock.call.bind_socket(join()),
            ]
        )

        self.assertIs(
            result,
            False
        )

        self.assertIsNone(self.singleton.listener)
        self.assertIsNone(self.singleton.socket_path)

    def test_start_closes_and_returns_false_on_os_error_in_start(self):
        base = unittest.mock.Mock()

        with contextlib.ExitStack() as stack:
            get_socket_path = stack.enter_context(unittest.mock.patch.object(
                self.singleton,
                "get_socket_path",
                new=base.get_socket_path
            ))

            bind_socket = stack.enter_context(unittest.mock.patch.object(
                self.singleton,
                "bind_socket",
                new=base.bind_socket
            ))

            join = stack.enter_context(unittest.mock.patch(
                "os.path.join",
                new=base.join
            ))

            base.start_unix_server = CoroutineMock()
            start_unix_server = stack.enter_context(unittest.mock.patch(
                "asyncio.start_unix_server",
                new=base.start_unix_server
            ))
            start_unix_server.side_effect = OSError()

            result = run_coroutine(self.singleton.start())

        calls = list(base.mock_calls)

        self.assertSequenceEqual(
            calls,
            [
                unittest.mock.call.get_socket_path(),
                unittest.mock.call.join(
                    get_socket_path(),
                    "singletonify.sock"),
                unittest.mock.call.bind_socket(join()),
                unittest.mock.call.start_unix_server(
                    unittest.mock.ANY,
                    sock=bind_socket(),
                    loop=self.loop),
                unittest.mock.call.bind_socket().close()
            ]
        )

        self.assertIs(
            result,
            False
        )

        self.assertIsNone(self.singleton.listener)
        self.assertIsNone(self.singleton.socket_path)

    def test_stop_raises_runtime_error_if_not_started(self):
        with self.assertRaisesRegex(RuntimeError, "not started"):
            run_coroutine(self.singleton.stop())

    def test_stop_uses_listener_and_socket_path_and_cleans_up(self):
        path = object()

        base = unittest.mock.Mock()
        base.listener.wait_closed = CoroutineMock()

        self.singleton.socket_path = path
        self.singleton.listener = base.listener

        with contextlib.ExitStack() as stack:
            unlink = stack.enter_context(unittest.mock.patch(
                "os.unlink",
                new=base.unlink
            ))

            run_coroutine(self.singleton.stop())

        calls = list(base.mock_calls)
        self.assertSequenceEqual(
            calls,
            [
                unittest.mock.call.unlink(path),
                unittest.mock.call.listener.close(),
                unittest.mock.call.listener.wait_closed()
            ]
        )
    def test_stop_ignores_os_error_from_unlink(self):
        path = object()

        base = unittest.mock.Mock()
        base.listener.wait_closed = CoroutineMock()

        self.singleton.socket_path = path
        self.singleton.listener = base.listener

        with contextlib.ExitStack() as stack:
            unlink = stack.enter_context(unittest.mock.patch(
                "os.unlink",
                new=base.unlink
            ))
            unlink.side_effect = OSError()

            run_coroutine(self.singleton.stop())

        calls = list(base.mock_calls)
        self.assertSequenceEqual(
            calls,
            [
                unittest.mock.call.unlink(path),
                unittest.mock.call.listener.close(),
                unittest.mock.call.listener.wait_closed()
            ]
        )

    def test_init_raises_if_event_loop_is_not_unixy(self):
        loop = object()

        with self.assertRaisesRegex(RuntimeError,
                                    "not supported on this platform"):
            main._UnixGlobalSingleton(loop)


    def tearDown(self):
        del self.singleton


@skip_with_unix
class Test_UnixGlobalSingleton_OnNonUnix(unittest.TestCase):
    def test_init_raises(self):
        with self.assertRaisesRegex(RuntimeError,
                                    "not supported on this platform"):
            main._UnixGlobalSingleton(asyncio.get_event_loop())


class Testget_singleton_impl(unittest.TestCase):
    @skip_without_unix
    def test_returns_unix(self):
        loop = unittest.mock.Mock()

        with unittest.mock.patch(
                "mlxc.main._UnixGlobalSingleton"
        ) as Singleton:
            result = main.get_singleton_impl(loop)

        self.assertSequenceEqual(
            Singleton.mock_calls,
            [
                unittest.mock.call(loop),
            ]
        )

        self.assertEqual(
            result,
            Singleton()
        )


class TestMain(unittest.TestCase):
    def setUp(self):
        self.loop = asyncio.get_event_loop()
        self.main = main.Main(self.loop)

    def test_init(self):
        base = unittest.mock.Mock()

        instance = main.Main(base.loop)

        self.assertIs(instance.loop, base.loop)

    def test_setup(self):
        base = unittest.mock.Mock()

        instance = main.Main(base.loop)

        with contextlib.ExitStack() as stack:
            Future = stack.enter_context(unittest.mock.patch(
                "asyncio.Future",
                new=base.Future
            ))

            instance.setup()

        calls = list(base.mock_calls)
        self.assertSequenceEqual(
            calls,
            [
                unittest.mock.call.loop.add_signal_handler(
                    signal.SIGINT,
                    instance.handle_sigint_sigterm
                ),
                unittest.mock.call.loop.add_signal_handler(
                    signal.SIGTERM,
                    instance.handle_sigint_sigterm
                ),
                unittest.mock.call.Future(loop=base.loop)
            ]
        )

    def test_teardown(self):
        base = unittest.mock.Mock()

        instance = main.Main(base.loop)
        instance.setup()

        base.mock_calls.clear()

        with contextlib.ExitStack() as stack:
            instance.teardown()

        self.assertFalse(hasattr(instance, "main_future"))

        calls = list(base.mock_calls)
        self.assertSequenceEqual(
            calls,
            [
                unittest.mock.call.loop.remove_signal_handler(signal.SIGTERM),
                unittest.mock.call.loop.remove_signal_handler(signal.SIGINT),
            ]
        )

    def test_acquire_singleton_starts_get_singleton_impl(self):
        base = unittest.mock.Mock()

        base.get_singleton_impl().start = CoroutineMock()
        base.get_singleton_impl().start.return_value = True

        base.mock_calls.clear()

        with contextlib.ExitStack() as stack:
            get_singleton_impl = stack.enter_context(unittest.mock.patch(
                "mlxc.main.get_singleton_impl",
                new=base.get_singleton_impl
            ))

            result = run_coroutine(self.main.acquire_singleton())

        calls = list(base.mock_calls)
        self.assertSequenceEqual(
            calls,
            [
                unittest.mock.call.get_singleton_impl(self.main.loop),
                unittest.mock.call.get_singleton_impl().start(),
            ]
        )

        self.assertEqual(
            get_singleton_impl(),
            result
        )

    def test_acquire_singleton_sets_singleton_to_None_on_no_impl(self):
        base = unittest.mock.Mock()

        base.get_singleton_impl.side_effect = RuntimeError()

        base.mock_calls.clear()

        with contextlib.ExitStack() as stack:
            get_singleton_impl = stack.enter_context(unittest.mock.patch(
                "mlxc.main.get_singleton_impl",
                new=base.get_singleton_impl
            ))

            result = run_coroutine(self.main.acquire_singleton())

        calls = list(base.mock_calls)
        self.assertSequenceEqual(
            calls,
            [
                unittest.mock.call.get_singleton_impl(self.main.loop),
            ]
        )

        self.assertIs(
            None,
            result
        )

    def test_acquire_singleton_raises_on_start_failure(self):
        base = unittest.mock.Mock()

        base.get_singleton_impl().start = CoroutineMock()
        base.get_singleton_impl().start.return_value = False

        base.mock_calls.clear()

        with contextlib.ExitStack() as stack:
            get_singleton_impl = stack.enter_context(unittest.mock.patch(
                "mlxc.main.get_singleton_impl",
                new=base.get_singleton_impl
            ))

            result = run_coroutine(self.main.acquire_singleton())

        calls = list(base.mock_calls)
        self.assertSequenceEqual(
            calls,
            [
                unittest.mock.call.get_singleton_impl(self.main.loop),
                unittest.mock.call.get_singleton_impl().start(),
            ]
        )

        self.assertIs(
            False,
            result
        )

    def test_acquire_singleton_re_raises_start_exceptions(self):
        base = unittest.mock.Mock()

        exc = Exception()

        base.get_singleton_impl().start = CoroutineMock()
        base.get_singleton_impl().start.side_effect = exc

        base.mock_calls.clear()

        with contextlib.ExitStack() as stack:
            get_singleton_impl = stack.enter_context(unittest.mock.patch(
                "mlxc.main.get_singleton_impl",
                new=base.get_singleton_impl
            ))

            result = run_coroutine(self.main.acquire_singleton())

        calls = list(base.mock_calls)
        self.assertSequenceEqual(
            calls,
            [
                unittest.mock.call.get_singleton_impl(self.main.loop),
                unittest.mock.call.get_singleton_impl().start(),
            ]
        )

        self.assertIs(
            False,
            result
        )

    def test_run_call_sequence(self):
        base = unittest.mock.Mock()

        obj = object()

        base.acquire_singleton = CoroutineMock()
        run_coroutine(base.acquire_singleton()).stop = CoroutineMock()
        base.run_core = CoroutineMock()
        base.run_core.return_value = obj

        base.mock_calls.clear()

        with contextlib.ExitStack() as stack:
            acquire_singleton = stack.enter_context(unittest.mock.patch.object(
                self.main,
                "acquire_singleton",
                new=base.acquire_singleton
            ))

            run_core = stack.enter_context(unittest.mock.patch.object(
                self.main,
                "run_core",
                new=base.run_core
            ))

            setup = stack.enter_context(unittest.mock.patch.object(
                self.main,
                "setup",
                new=base.setup
            ))

            teardown = stack.enter_context(unittest.mock.patch.object(
                self.main,
                "teardown",
                new=base.teardown
            ))

            result = run_coroutine(self.main.run())

        calls = list(base.mock_calls)
        self.assertSequenceEqual(
            calls,
            [
                unittest.mock.call.setup(),
                unittest.mock.call.acquire_singleton(),
                unittest.mock.call.run_core(),
                unittest.mock.call.acquire_singleton().stop(),
                unittest.mock.call.teardown(),
            ]
        )

        self.assertEqual(
            result,
            obj
        )

    def test_run_handle_None_singleton(self):
        base = unittest.mock.Mock()

        obj = object()

        base.acquire_singleton = CoroutineMock()
        base.acquire_singleton.return_value = None
        base.run_core = CoroutineMock()
        base.run_core.return_value = obj

        base.mock_calls.clear()

        with contextlib.ExitStack() as stack:
            acquire_singleton = stack.enter_context(unittest.mock.patch.object(
                self.main,
                "acquire_singleton",
                new=base.acquire_singleton
            ))

            run_core = stack.enter_context(unittest.mock.patch.object(
                self.main,
                "run_core",
                new=base.run_core
            ))

            setup = stack.enter_context(unittest.mock.patch.object(
                self.main,
                "setup",
                new=base.setup
            ))

            teardown = stack.enter_context(unittest.mock.patch.object(
                self.main,
                "teardown",
                new=base.teardown
            ))

            result = run_coroutine(self.main.run())

        calls = list(base.mock_calls)
        self.assertSequenceEqual(
            calls,
            [
                unittest.mock.call.setup(),
                unittest.mock.call.acquire_singleton(),
                unittest.mock.call.run_core(),
                unittest.mock.call.teardown(),
            ]
        )

        self.assertEqual(
            result,
            obj
        )

    def test_run_handle_False_singleton(self):
        base = unittest.mock.Mock()

        obj = object()

        base.acquire_singleton = CoroutineMock()
        base.acquire_singleton.return_value = False
        base.run_core = CoroutineMock()
        base.run_core.return_value = obj

        base.mock_calls.clear()

        with contextlib.ExitStack() as stack:
            acquire_singleton = stack.enter_context(unittest.mock.patch.object(
                self.main,
                "acquire_singleton",
                new=base.acquire_singleton
            ))

            run_core = stack.enter_context(unittest.mock.patch.object(
                self.main,
                "run_core",
                new=base.run_core
            ))

            setup = stack.enter_context(unittest.mock.patch.object(
                self.main,
                "setup",
                new=base.setup
            ))

            teardown = stack.enter_context(unittest.mock.patch.object(
                self.main,
                "teardown",
                new=base.teardown
            ))

            result = run_coroutine(self.main.run())

        calls = list(base.mock_calls)
        self.assertSequenceEqual(
            calls,
            [
                unittest.mock.call.setup(),
                unittest.mock.call.acquire_singleton(),
                unittest.mock.call.teardown(),
            ]
        )

        self.assertEqual(
            result,
            1
        )

    def test_run_handle_core_exception(self):
        base = unittest.mock.Mock()

        exc = Exception()

        base.acquire_singleton = CoroutineMock()
        base.run_core = CoroutineMock()
        base.run_core.side_effect = exc

        base.mock_calls.clear()

        with contextlib.ExitStack() as stack:
            acquire_singleton = stack.enter_context(unittest.mock.patch.object(
                self.main,
                "acquire_singleton",
                new=base.acquire_singleton
            ))

            run_core = stack.enter_context(unittest.mock.patch.object(
                self.main,
                "run_core",
                new=base.run_core
            ))

            setup = stack.enter_context(unittest.mock.patch.object(
                self.main,
                "setup",
                new=base.setup
            ))

            teardown = stack.enter_context(unittest.mock.patch.object(
                self.main,
                "teardown",
                new=base.teardown
            ))

            result = run_coroutine(self.main.run())

        calls = list(base.mock_calls)
        self.assertSequenceEqual(
            calls,
            [
                unittest.mock.call.setup(),
                unittest.mock.call.acquire_singleton(),
                unittest.mock.call.run_core(),
                unittest.mock.call.acquire_singleton().stop(),
                unittest.mock.call.teardown()
            ]
        )

        self.assertEqual(
            result,
            1
        )

    def test_quit_sets_main_future_result(self):
        self.main.setup()

        self.assertFalse(self.main.main_future.done())
        self.main.quit()
        self.assertEqual(
            self.main.main_future.result(),
            0
        )

    def test_quit_is_noop_if_main_future_is_done(self):
        self.main.setup()

        self.main.main_future.set_result(1)
        self.assertTrue(self.main.main_future.done())
        self.main.quit()
        self.assertEqual(
            self.main.main_future.result(),
            1
        )

    def test_handle_sigint_sigterm_calls_quit(self):
        with contextlib.ExitStack() as stack:
            quit_ = stack.enter_context(unittest.mock.patch.object(
                self.main,
                "quit"
            ))

            self.main.handle_sigint_sigterm()

        calls = list(quit_.mock_calls)
        self.assertSequenceEqual(
            calls,
            [
                unittest.mock.call(),
            ]
        )

    def test_handle_sigint_sigterm_stops_the_loop_after_3_seconds(self):
        base = unittest.mock.Mock()

        base.mock_calls.clear()

        with contextlib.ExitStack() as stack:
            monotonic = stack.enter_context(unittest.mock.patch(
                "time.monotonic",
            ))
            monotonic.return_value = 0

            quit_ = stack.enter_context(unittest.mock.patch.object(
                self.main,
                "quit",
                new=base.quit
            ))

            stop = stack.enter_context(unittest.mock.patch.object(
                self.main.loop,
                "stop",
                new=base.stop
            ))

            self.main.handle_sigint_sigterm()

            monotonic.return_value = 2.99

            self.main.handle_sigint_sigterm()

            monotonic.return_value = 3.01

            self.main.handle_sigint_sigterm()

        calls = list(base.mock_calls)
        self.assertSequenceEqual(
            calls,
            [
                unittest.mock.call.quit(),
                unittest.mock.call.quit(),
                unittest.mock.call.stop()
            ]
        )

    def tearDown(self):
        del self.main
        del self.loop
