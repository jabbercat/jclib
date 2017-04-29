import asyncio
import contextlib
import itertools
import pathlib
import unittest
import unittest.mock
import uuid

from datetime import datetime

import aioxmpp

import mlxc.storage.account_model
import mlxc.storage.common
import mlxc.storage.identity_model
import mlxc.storage.peer_model
import mlxc.storage.frontends as frontends

from aioxmpp.testutils import (
    run_coroutine,
    CoroutineMock,
)

from mlxc.testutils import (
    inmemory_database,
)


class Testencode_jid(unittest.TestCase):
    def test_hashes_jid(self):
        jid = unittest.mock.sentinel.jid

        with contextlib.ExitStack() as stack:
            str_ = stack.enter_context(
                unittest.mock.patch.object(frontends, "str")
            )

            sha256 = stack.enter_context(
                unittest.mock.patch("hashlib.sha256")
            )

            b32encode = stack.enter_context(
                unittest.mock.patch("base64.b32encode")
            )

            Path = stack.enter_context(
                unittest.mock.patch("pathlib.Path",
                                    new=unittest.mock.MagicMock())
            )

            def generate_results():
                for i in itertools.count():
                    yield getattr(unittest.mock.sentinel, "part{}".format(i))

            lowered = b32encode().decode().rstrip().lower()
            lowered.__getitem__.side_effect = generate_results()
            b32encode.reset_mock()

            result = frontends.encode_jid(jid)

        str_.assert_called_once_with(jid)
        str_().encode.assert_called_once_with("utf-8")
        sha256.assert_called_once_with()
        sha256().update.assert_called_once_with(str_().encode())
        sha256().digest.assert_called_once_with()
        b32encode.assert_called_once_with(sha256().digest())
        b32encode().decode.assert_called_once_with("ascii")
        b32encode().decode().rstrip.assert_called_once_with("=")
        b32encode().decode().rstrip().lower.assert_called_once_with()

        self.assertSequenceEqual(
            lowered.mock_calls,
            [
                unittest.mock._Call(("__getitem__",
                                     (slice(None, 2, None),), {})),
                unittest.mock._Call(("__getitem__",
                                     (slice(2, 4, None),), {})),
                unittest.mock._Call(("__getitem__",
                                     (slice(4, None, None),), {})),
            ]
        )

        Path.assert_called_once_with(unittest.mock.sentinel.part0)
        Path().__truediv__\
            .assert_called_once_with(unittest.mock.sentinel.part1)
        Path().__truediv__().__truediv__\
            .assert_called_once_with(unittest.mock.sentinel.part2)

        self.assertEqual(
            result,
            Path().__truediv__().__truediv__()
        )


class Test_PerLevelKeyFileMixin(unittest.TestCase):
    class Frontend(frontends._PerLevelKeyFileMixin, frontends.Frontend):
        pass

    def setUp(self):
        self.backend = unittest.mock.Mock()
        self.f = self.Frontend(self.backend)

    def test__get_path(self):
        path_mock = unittest.mock.MagicMock()
        level = unittest.mock.Mock()
        self.backend.type_base_paths.return_value = [path_mock]

        result = self.f._get_path(
            unittest.mock.sentinel.type_,
            level,
            unittest.mock.sentinel.namespace,
            unittest.mock.sentinel.name,
        )

        path_mock.__truediv__.assert_called_once_with(level.level.value)
        path_mock.__truediv__().__truediv__.assert_called_once_with(
            level.key_path
        )
        path_mock.__truediv__().__truediv__().__truediv__\
            .assert_called_once_with(
                unittest.mock.sentinel.namespace,
            )
        path_mock.__truediv__().__truediv__().__truediv__().__truediv__\
            .assert_called_once_with(
                unittest.mock.sentinel.name,
            )

        self.assertEqual(
            result,
            path_mock.__truediv__().__truediv__().__truediv__().__truediv__()
        )


class Test_PerLevelMixin(unittest.TestCase):
    class Frontend(frontends._PerLevelMixin, frontends.Frontend):
        pass

    def setUp(self):
        self.backend = unittest.mock.Mock()
        self.f = self.Frontend(self.backend)

    def test__get_path(self):
        path_mock = unittest.mock.MagicMock()
        level_type = unittest.mock.Mock()
        self.backend.type_base_paths.return_value = [path_mock]

        result = self.f._get_path(
            unittest.mock.sentinel.type_,
            level_type,
            unittest.mock.sentinel.namespace,
            unittest.mock.sentinel.frontend_name,
            unittest.mock.sentinel.name,
        )

        path_mock.__truediv__.assert_called_once_with(
            frontends.StorageLevel.GLOBAL.value
        )
        path_mock.__truediv__().__truediv__.assert_called_once_with(
            unittest.mock.sentinel.namespace,
        )
        path_mock.__truediv__().__truediv__().__truediv__\
            .assert_called_once_with(
                unittest.mock.sentinel.frontend_name
            )
        path_mock.__truediv__().__truediv__().__truediv__().__truediv__\
            .assert_called_once_with(
                level_type.value
            )
        path_mock.__truediv__().__truediv__().__truediv__().__truediv__()\
            .__truediv__.assert_called_once_with(
                unittest.mock.sentinel.name,
            )

        self.assertEqual(
            result,
            path_mock.__truediv__().__truediv__().__truediv__().__truediv__()
            .__truediv__()
        )


class TestLargeBlobFrontend(unittest.TestCase):
    def setUp(self):
        self.backend = unittest.mock.Mock()
        self.f = frontends.LargeBlobFrontend(self.backend)

    def test_uses_mixin(self):
        self.assertIsInstance(
            self.f,
            frontends._PerLevelKeyFileMixin
        )

    def test_offers_filelike_interface(self):
        self.assertIsInstance(
            self.f,
            frontends.FileLikeFrontend
        )

    def test_open_readable(self):
        for mode in ["r", "rb", "rt"]:
            with contextlib.ExitStack() as stack:
                _get_path = stack.enter_context(
                    unittest.mock.patch.object(self.f, "_get_path")
                )

                mkdir_exist_ok = stack.enter_context(
                    unittest.mock.patch("mlxc.utils.mkdir_exist_ok")
                )

                result = run_coroutine(self.f.open(
                    unittest.mock.sentinel.type_,
                    unittest.mock.sentinel.level,
                    unittest.mock.sentinel.namespace,
                    "filename",
                    mode,
                    a=unittest.mock.sentinel.kwarg,
                    encoding=unittest.mock.sentinel.encoding,
                ))

                _get_path.assert_called_once_with(
                    unittest.mock.sentinel.type_,
                    unittest.mock.sentinel.level,
                    unittest.mock.sentinel.namespace,
                    pathlib.Path("largeblobs") / "filename",
                )
                _get_path().open.assert_called_once_with(
                    mode,
                    a=unittest.mock.sentinel.kwarg,
                    encoding=unittest.mock.sentinel.encoding,
                )
                self.assertEqual(
                    result,
                    _get_path().open()
                )

                mkdir_exist_ok.assert_not_called()

    def test_open_allows_omission_of_mode_argument(self):
        with contextlib.ExitStack() as stack:
            _get_path = stack.enter_context(
                unittest.mock.patch.object(self.f, "_get_path")
            )

            mkdir_exist_ok = stack.enter_context(
                unittest.mock.patch("mlxc.utils.mkdir_exist_ok")
            )

            result = run_coroutine(self.f.open(
                unittest.mock.sentinel.type_,
                unittest.mock.sentinel.level,
                unittest.mock.sentinel.namespace,
                "filename",
                a=unittest.mock.sentinel.kwarg,
                encoding=unittest.mock.sentinel.encoding,
            ))

            _get_path.assert_called_once_with(
                unittest.mock.sentinel.type_,
                unittest.mock.sentinel.level,
                unittest.mock.sentinel.namespace,
                pathlib.Path("largeblobs") / "filename",
            )
            _get_path().open.assert_called_once_with(
                "r",
                a=unittest.mock.sentinel.kwarg,
                encoding=unittest.mock.sentinel.encoding,
            )
            self.assertEqual(
                result,
                _get_path().open()
            )

            mkdir_exist_ok.assert_not_called()

    def test_open_writable(self):
        modes = ["r+", "w", "w+", "x", "x+", "a", "a+"]
        modes = [
            "".join(parts)
            for parts in itertools.product(modes, ["", "t", "b"])
        ]
        for mode in modes:
            with contextlib.ExitStack() as stack:
                _get_path = stack.enter_context(
                    unittest.mock.patch.object(self.f, "_get_path")
                )

                mkdir_exist_ok = stack.enter_context(
                    unittest.mock.patch("mlxc.utils.mkdir_exist_ok")
                )

                result = run_coroutine(self.f.open(
                    unittest.mock.sentinel.type_,
                    unittest.mock.sentinel.level,
                    unittest.mock.sentinel.namespace,
                    "filename",
                    mode,
                    a=unittest.mock.sentinel.kwarg,
                    encoding=unittest.mock.sentinel.encoding,
                ))

                _get_path.assert_called_once_with(
                    unittest.mock.sentinel.type_,
                    unittest.mock.sentinel.level,
                    unittest.mock.sentinel.namespace,
                    pathlib.Path("largeblobs") / "filename",
                )
                mkdir_exist_ok.assert_called_once_with(
                    _get_path().parent,
                )
                _get_path().open.assert_called_once_with(
                    mode,
                    a=unittest.mock.sentinel.kwarg,
                    encoding=unittest.mock.sentinel.encoding,
                )
                self.assertEqual(
                    result,
                    _get_path().open()
                )

    def test_stat(self):
        with contextlib.ExitStack() as stack:
            _get_path = stack.enter_context(
                unittest.mock.patch.object(self.f, "_get_path")
            )

            mkdir_exist_ok = stack.enter_context(
                unittest.mock.patch("mlxc.utils.mkdir_exist_ok")
            )

            result = run_coroutine(self.f.stat(
                unittest.mock.sentinel.type_,
                unittest.mock.sentinel.level,
                unittest.mock.sentinel.namespace,
                "filename",
            ))

            _get_path.assert_called_once_with(
                unittest.mock.sentinel.type_,
                unittest.mock.sentinel.level,
                unittest.mock.sentinel.namespace,
                pathlib.Path("largeblobs") / "filename",
            )
            _get_path().stat.assert_called_once_with()
            self.assertEqual(
                result,
                _get_path().stat()
            )

            mkdir_exist_ok.assert_not_called()

    def test_unlink(self):
        with contextlib.ExitStack() as stack:
            _get_path = stack.enter_context(
                unittest.mock.patch.object(self.f, "_get_path")
            )

            mkdir_exist_ok = stack.enter_context(
                unittest.mock.patch("mlxc.utils.mkdir_exist_ok")
            )

            run_coroutine(self.f.unlink(
                unittest.mock.sentinel.type_,
                unittest.mock.sentinel.level,
                unittest.mock.sentinel.namespace,
                "filename",
            ))

            _get_path.assert_called_once_with(
                unittest.mock.sentinel.type_,
                unittest.mock.sentinel.level,
                unittest.mock.sentinel.namespace,
                pathlib.Path("largeblobs") / "filename",
            )
            _get_path().unlink.assert_called_once_with()

            mkdir_exist_ok.assert_not_called()


class TestSmallBlobFrontend(unittest.TestCase):
    def setUp(self):
        self.backend = unittest.mock.Mock()
        self.f = frontends.SmallBlobFrontend(self.backend)

    def test_implements_FileLikeFrontend(self):
        self.assertIsInstance(
            self.f,
            frontends.FileLikeFrontend,
        )

    def test__get_path(self):
        path_mock = unittest.mock.MagicMock()
        level_type = unittest.mock.MagicMock()
        self.backend.type_base_paths.return_value = [path_mock]

        result = self.f._get_path(
            unittest.mock.sentinel.type_,
            level_type,
            unittest.mock.sentinel.namespace,
        )

        path_mock.__truediv__.assert_called_once_with(
            frontends.StorageLevel.GLOBAL.value
        )
        path_mock.__truediv__().__truediv__.assert_called_once_with(
            unittest.mock.sentinel.namespace,
        )
        path_mock.__truediv__().__truediv__().__truediv__\
            .assert_called_once_with(
                "smallblobs"
            )
        level_type.value.__add__.assert_called_once_with(".sqlite")
        path_mock.__truediv__().__truediv__().__truediv__().__truediv__\
            .assert_called_once_with(
                level_type.value.__add__()
            )

        self.assertEqual(
            result,
            path_mock.__truediv__().__truediv__().__truediv__().__truediv__()
        )

    def test__get_engine(self):
        with contextlib.ExitStack() as stack:
            _get_path = stack.enter_context(
                unittest.mock.patch.object(self.f, "_get_path")
            )

            create_engine = stack.enter_context(
                unittest.mock.patch("sqlalchemy.create_engine")
            )

            mkdir_exist_ok = stack.enter_context(
                unittest.mock.patch("mlxc.utils.mkdir_exist_ok")
            )

            listens_for = stack.enter_context(
                unittest.mock.patch("sqlalchemy.event.listens_for")
            )

            result = self.f._get_engine(
                unittest.mock.sentinel.type_,
                unittest.mock.sentinel.level,
                unittest.mock.sentinel.namespace,
            )

            _get_path.assert_called_once_with(
                unittest.mock.sentinel.type_,
                unittest.mock.sentinel.level,
                unittest.mock.sentinel.namespace,
            )

            mkdir_exist_ok.assert_called_once_with(
                _get_path().parent
            )

            create_engine.assert_called_once_with(
                "sqlite:///{}".format(_get_path()),
            )

            self.assertSequenceEqual(
                listens_for.mock_calls,
                [
                    unittest.mock.call(create_engine(), "connect"),
                    unittest.mock.call()(unittest.mock.ANY),
                    unittest.mock.call(create_engine(), "begin"),
                    unittest.mock.call()(unittest.mock.ANY),
                ]
            )

            self.assertEqual(result, create_engine())

    def test__init_engine_for_peer(self):
        with contextlib.ExitStack() as stack:
            peer_metadata = stack.enter_context(
                unittest.mock.patch.object(
                    mlxc.storage.peer_model.Base,
                    "metadata"
                )
            )

            identity_metadata = stack.enter_context(
                unittest.mock.patch.object(
                    mlxc.storage.identity_model.Base,
                    "metadata"
                )
            )

            account_metadata = stack.enter_context(
                unittest.mock.patch.object(
                    mlxc.storage.account_model.Base,
                    "metadata"
                )
            )

            self.f._init_engine(
                unittest.mock.sentinel.engine,
                frontends.StorageLevel.PEER,
            )

            peer_metadata.create_all.assert_called_once_with(
                unittest.mock.sentinel.engine,
            )

            identity_metadata.create_all.assert_not_called()
            account_metadata.create_all.assert_not_called()

    def test__init_engine_for_identity(self):
        with contextlib.ExitStack() as stack:
            peer_metadata = stack.enter_context(
                unittest.mock.patch.object(
                    mlxc.storage.peer_model.Base,
                    "metadata"
                )
            )

            identity_metadata = stack.enter_context(
                unittest.mock.patch.object(
                    mlxc.storage.identity_model.Base,
                    "metadata"
                )
            )

            account_metadata = stack.enter_context(
                unittest.mock.patch.object(
                    mlxc.storage.account_model.Base,
                    "metadata"
                )
            )

            self.f._init_engine(
                unittest.mock.sentinel.engine,
                frontends.StorageLevel.IDENTITY,
            )

            identity_metadata.create_all.assert_called_once_with(
                unittest.mock.sentinel.engine,
            )

            peer_metadata.create_all.assert_not_called()
            account_metadata.create_all.assert_not_called()

    def test__init_engine_for_account(self):
        with contextlib.ExitStack() as stack:
            peer_metadata = stack.enter_context(
                unittest.mock.patch.object(
                    mlxc.storage.peer_model.Base,
                    "metadata"
                )
            )

            identity_metadata = stack.enter_context(
                unittest.mock.patch.object(
                    mlxc.storage.identity_model.Base,
                    "metadata"
                )
            )

            account_metadata = stack.enter_context(
                unittest.mock.patch.object(
                    mlxc.storage.account_model.Base,
                    "metadata"
                )
            )

            self.f._init_engine(
                unittest.mock.sentinel.engine,
                frontends.StorageLevel.ACCOUNT,
            )

            account_metadata.create_all.assert_called_once_with(
                unittest.mock.sentinel.engine,
            )

            peer_metadata.create_all.assert_not_called()
            identity_metadata.create_all.assert_not_called()

    def test__init_engine_fails_for_global(self):
        with contextlib.ExitStack() as stack:
            peer_metadata = stack.enter_context(
                unittest.mock.patch.object(
                    mlxc.storage.peer_model.Base,
                    "metadata"
                )
            )

            identity_metadata = stack.enter_context(
                unittest.mock.patch.object(
                    mlxc.storage.identity_model.Base,
                    "metadata"
                )
            )

            account_metadata = stack.enter_context(
                unittest.mock.patch.object(
                    mlxc.storage.account_model.Base,
                    "metadata"
                )
            )

            with self.assertRaisesRegexp(
                    ValueError,
                    "GLOBAL level not supported"):
                self.f._init_engine(
                    unittest.mock.sentinel.engine,
                    frontends.StorageLevel.GLOBAL,
                )

            account_metadata.create_all.assert_not_called()
            peer_metadata.create_all.assert_not_called()
            identity_metadata.create_all.assert_not_called()

    def test__init_engine_fails_for_unknown_enum(self):
        with contextlib.ExitStack() as stack:
            peer_metadata = stack.enter_context(
                unittest.mock.patch.object(
                    mlxc.storage.peer_model.Base,
                    "metadata"
                )
            )

            identity_metadata = stack.enter_context(
                unittest.mock.patch.object(
                    mlxc.storage.identity_model.Base,
                    "metadata"
                )
            )

            account_metadata = stack.enter_context(
                unittest.mock.patch.object(
                    mlxc.storage.account_model.Base,
                    "metadata"
                )
            )

            with self.assertRaisesRegexp(
                    ValueError,
                    "unknown storage level: .*sentinel.+"):
                self.f._init_engine(
                    unittest.mock.sentinel.engine,
                    unittest.mock.sentinel.fubar,
                )

            account_metadata.create_all.assert_not_called()
            peer_metadata.create_all.assert_not_called()
            identity_metadata.create_all.assert_not_called()

    def test__get_sessionmaker(self):
        with contextlib.ExitStack() as stack:
            _get_engine = stack.enter_context(
                unittest.mock.patch.object(self.f, "_get_engine")
            )

            _init_engine = stack.enter_context(
                unittest.mock.patch.object(self.f, "_init_engine")
            )

            sessionmaker = stack.enter_context(
                unittest.mock.patch("sqlalchemy.orm.sessionmaker")
            )

            result = self.f._get_sessionmaker(
                unittest.mock.sentinel.type_,
                unittest.mock.sentinel.level,
                unittest.mock.sentinel.namespace,
            )

            _get_engine.assert_called_once_with(
                unittest.mock.sentinel.type_,
                unittest.mock.sentinel.level,
                unittest.mock.sentinel.namespace,
            )

            _init_engine.assert_called_once_with(
                _get_engine(),
                unittest.mock.sentinel.level,
            )

            sessionmaker.assert_called_once_with(bind=_get_engine())

            self.assertEqual(
                result,
                sessionmaker()
            )

    def test__get_sessionmaker_is_lru_cache(self):
        self.assertTrue(hasattr(type(self.f)._get_sessionmaker, "cache_info"))

    def test__store_blob_peer(self):
        with contextlib.ExitStack() as stack:
            _get_sessionmaker = stack.enter_context(
                unittest.mock.patch.object(self.f, "_get_sessionmaker")
            )

            session_scope = unittest.mock.MagicMock()
            session_scope.side_effect = mlxc.storage.common.session_scope
            stack.enter_context(
                unittest.mock.patch(
                    "mlxc.storage.common.session_scope",
                    new=session_scope
                )
            )

            touch_mtime = stack.enter_context(
                unittest.mock.patch.object(
                    mlxc.storage.peer_model.SmallBlob,
                    "touch_mtime",
                )
            )

            self.f._store_blob(
                unittest.mock.sentinel.type_,
                frontends.PeerLevel(
                    unittest.mock.sentinel.identity,
                    unittest.mock.sentinel.peer,
                ),
                unittest.mock.sentinel.namespace,
                unittest.mock.sentinel.name,
                unittest.mock.sentinel.data,
            )

            _get_sessionmaker.assert_called_once_with(
                unittest.mock.sentinel.type_,
                mlxc.storage.common.StorageLevel.PEER,
                unittest.mock.sentinel.namespace,
            )

            session_scope.assert_called_once_with(
                _get_sessionmaker(),
            )

            _get_sessionmaker()().merge.assert_called_once_with(
                unittest.mock.ANY,
            )

            _, (blob, ), _ = _get_sessionmaker()().merge.mock_calls[0]

            touch_mtime.assert_called_once_with()

            self.assertIsInstance(
                blob,
                mlxc.storage.peer_model.SmallBlob,
            )

            self.assertEqual(
                blob.identity,
                unittest.mock.sentinel.identity,
            )

            self.assertEqual(
                blob.peer,
                unittest.mock.sentinel.peer,
            )

            self.assertEqual(
                blob.data,
                unittest.mock.sentinel.data,
            )

            self.assertEqual(
                blob.name,
                unittest.mock.sentinel.name,
            )

    def test__store_blob_account(self):
        with contextlib.ExitStack() as stack:
            _get_sessionmaker = stack.enter_context(
                unittest.mock.patch.object(self.f, "_get_sessionmaker")
            )

            session_scope = unittest.mock.MagicMock()
            session_scope.side_effect = mlxc.storage.common.session_scope
            stack.enter_context(
                unittest.mock.patch(
                    "mlxc.storage.common.session_scope",
                    new=session_scope
                )
            )

            touch_mtime = stack.enter_context(
                unittest.mock.patch.object(
                    mlxc.storage.account_model.SmallBlob,
                    "touch_mtime",
                )
            )

            self.f._store_blob(
                unittest.mock.sentinel.type_,
                frontends.AccountLevel(
                    unittest.mock.sentinel.account,
                ),
                unittest.mock.sentinel.namespace,
                unittest.mock.sentinel.name,
                unittest.mock.sentinel.data,
            )

            _get_sessionmaker.assert_called_once_with(
                unittest.mock.sentinel.type_,
                mlxc.storage.common.StorageLevel.ACCOUNT,
                unittest.mock.sentinel.namespace,
            )

            session_scope.assert_called_once_with(
                _get_sessionmaker(),
            )

            _get_sessionmaker()().merge.assert_called_once_with(
                unittest.mock.ANY,
            )

            _, (blob, ), _ = _get_sessionmaker()().merge.mock_calls[0]

            touch_mtime.assert_called_once_with()

            self.assertIsInstance(
                blob,
                mlxc.storage.account_model.SmallBlob,
            )

            self.assertEqual(
                blob.account,
                unittest.mock.sentinel.account,
            )

            self.assertEqual(
                blob.data,
                unittest.mock.sentinel.data,
            )

            self.assertEqual(
                blob.name,
                unittest.mock.sentinel.name,
            )

    def test__store_blob_identity(self):
        with contextlib.ExitStack() as stack:
            _get_sessionmaker = stack.enter_context(
                unittest.mock.patch.object(self.f, "_get_sessionmaker")
            )

            session_scope = unittest.mock.MagicMock()
            session_scope.side_effect = mlxc.storage.common.session_scope
            stack.enter_context(
                unittest.mock.patch(
                    "mlxc.storage.common.session_scope",
                    new=session_scope
                )
            )

            touch_mtime = stack.enter_context(
                unittest.mock.patch.object(
                    mlxc.storage.identity_model.SmallBlob,
                    "touch_mtime",
                )
            )

            self.f._store_blob(
                unittest.mock.sentinel.type_,
                frontends.IdentityLevel(
                    unittest.mock.sentinel.identity,
                ),
                unittest.mock.sentinel.namespace,
                unittest.mock.sentinel.name,
                unittest.mock.sentinel.data,
            )

            _get_sessionmaker.assert_called_once_with(
                unittest.mock.sentinel.type_,
                mlxc.storage.common.StorageLevel.IDENTITY,
                unittest.mock.sentinel.namespace,
            )

            session_scope.assert_called_once_with(
                _get_sessionmaker(),
            )

            _get_sessionmaker()().merge.assert_called_once_with(
                unittest.mock.ANY,
            )

            _, (blob, ), _ = _get_sessionmaker()().merge.mock_calls[0]

            touch_mtime.assert_called_once_with()

            self.assertIsInstance(
                blob,
                mlxc.storage.identity_model.SmallBlob,
            )

            self.assertEqual(
                blob.identity,
                unittest.mock.sentinel.identity,
            )

            self.assertEqual(
                blob.data,
                unittest.mock.sentinel.data,
            )

            self.assertEqual(
                blob.name,
                unittest.mock.sentinel.name,
            )

    def test_store_uses__store_blob(self):
        with contextlib.ExitStack() as stack:
            _store_blob = stack.enter_context(
                unittest.mock.patch.object(self.f, "_store_blob")
            )

            run_in_executor = stack.enter_context(
                unittest.mock.patch.object(
                    asyncio.get_event_loop(),
                    "run_in_executor",
                    new=CoroutineMock(),
                )
            )
            run_in_executor.return_value = None

            run_coroutine(self.f.store(
                unittest.mock.sentinel.type_,
                unittest.mock.sentinel.level,
                unittest.mock.sentinel.namespace,
                unittest.mock.sentinel.name,
                unittest.mock.sentinel.data,
            ))

            run_in_executor.assert_called_once_with(
                None,
                _store_blob,
                unittest.mock.sentinel.type_,
                unittest.mock.sentinel.level,
                unittest.mock.sentinel.namespace,
                unittest.mock.sentinel.name,
                unittest.mock.sentinel.data,
            )

    def test__load_blob_peer_level(self):
        with contextlib.ExitStack() as stack:
            _get_sessionmaker = stack.enter_context(
                unittest.mock.patch.object(self.f, "_get_sessionmaker")
            )

            session_scope = unittest.mock.MagicMock()
            session_scope.side_effect = mlxc.storage.common.session_scope
            stack.enter_context(
                unittest.mock.patch(
                    "mlxc.storage.common.session_scope",
                    new=session_scope
                )
            )

            get = stack.enter_context(
                unittest.mock.patch.object(
                    mlxc.storage.peer_model.SmallBlob,
                    "get",
                )
            )

            level = frontends.PeerLevel(
                unittest.mock.sentinel.identity,
                unittest.mock.sentinel.peer,
            )

            result = self.f._load_blob(
                unittest.mock.sentinel.type_,
                level,
                unittest.mock.sentinel.namespace,
                unittest.mock.sentinel.name,
                unittest.mock.sentinel.query,
            )

            _get_sessionmaker.assert_called_once_with(
                unittest.mock.sentinel.type_,
                mlxc.storage.common.StorageLevel.PEER,
                unittest.mock.sentinel.namespace,
            )

            session_scope.assert_called_once_with(
                _get_sessionmaker(),
            )

            get.assert_called_once_with(
                _get_sessionmaker()(),
                level,
                unittest.mock.sentinel.name,
                unittest.mock.sentinel.query,
            )

            get().touch.assert_not_called()

            self.assertEqual(
                result,
                get(),
            )

    def test__load_blob_with_touch(self):
        get_result = unittest.mock.Mock()

        def generate_results():
            for i in itertools.count():
                yield getattr(get_result, "i{}".format(i))

        with contextlib.ExitStack() as stack:
            _get_sessionmaker = stack.enter_context(
                unittest.mock.patch.object(self.f, "_get_sessionmaker")
            )

            session_scope = unittest.mock.MagicMock()
            session_scope.side_effect = mlxc.storage.common.session_scope
            stack.enter_context(
                unittest.mock.patch(
                    "mlxc.storage.common.session_scope",
                    new=session_scope
                )
            )

            get = stack.enter_context(
                unittest.mock.patch.object(
                    mlxc.storage.peer_model.SmallBlob,
                    "get",
                )
            )
            get.side_effect = generate_results()

            level = frontends.PeerLevel(
                unittest.mock.sentinel.identity,
                unittest.mock.sentinel.peer,
            )

            result = self.f._load_blob(
                unittest.mock.sentinel.type_,
                level,
                unittest.mock.sentinel.namespace,
                unittest.mock.sentinel.name,
                unittest.mock.sentinel.query,
                touch=True,
            )

            _get_sessionmaker.assert_called_once_with(
                unittest.mock.sentinel.type_,
                mlxc.storage.common.StorageLevel.PEER,
                unittest.mock.sentinel.namespace,
            )

            session_scope.assert_called_once_with(
                _get_sessionmaker(),
            )

            self.assertSequenceEqual(
                get.mock_calls,
                [
                    unittest.mock.call(
                        _get_sessionmaker()(), level,
                        unittest.mock.sentinel.name,
                        unittest.mock.sentinel.query,
                    ),
                    unittest.mock.call(
                        _get_sessionmaker()(), level,
                        unittest.mock.sentinel.name,
                    ),
                ]
            )

            get_result.i1.touch_atime.assert_called_once_with()

            self.assertEqual(
                result,
                get_result.i0,
            )

    def test__load_blob_account_level(self):
        with contextlib.ExitStack() as stack:
            _get_sessionmaker = stack.enter_context(
                unittest.mock.patch.object(self.f, "_get_sessionmaker")
            )

            session_scope = unittest.mock.MagicMock()
            session_scope.side_effect = mlxc.storage.common.session_scope
            stack.enter_context(
                unittest.mock.patch(
                    "mlxc.storage.common.session_scope",
                    new=session_scope
                )
            )

            get = stack.enter_context(
                unittest.mock.patch.object(
                    mlxc.storage.account_model.SmallBlob,
                    "get",
                )
            )

            level = frontends.AccountLevel(
                unittest.mock.sentinel.account,
            )

            result = self.f._load_blob(
                unittest.mock.sentinel.type_,
                level,
                unittest.mock.sentinel.namespace,
                unittest.mock.sentinel.name,
                unittest.mock.sentinel.query,
            )

            _get_sessionmaker.assert_called_once_with(
                unittest.mock.sentinel.type_,
                mlxc.storage.common.StorageLevel.ACCOUNT,
                unittest.mock.sentinel.namespace,
            )

            session_scope.assert_called_once_with(
                _get_sessionmaker(),
            )

            get.assert_called_once_with(
                _get_sessionmaker()(),
                level,
                unittest.mock.sentinel.name,
                unittest.mock.sentinel.query,
            )

            self.assertEqual(get(), result)

    def test__load_blob_identity_level(self):
        with contextlib.ExitStack() as stack:
            _get_sessionmaker = stack.enter_context(
                unittest.mock.patch.object(self.f, "_get_sessionmaker")
            )

            session_scope = unittest.mock.MagicMock()
            session_scope.side_effect = mlxc.storage.common.session_scope
            stack.enter_context(
                unittest.mock.patch(
                    "mlxc.storage.common.session_scope",
                    new=session_scope
                )
            )

            get = stack.enter_context(
                unittest.mock.patch.object(
                    mlxc.storage.identity_model.SmallBlob,
                    "get",
                )
            )

            level = frontends.IdentityLevel(
                unittest.mock.sentinel.identity,
            )

            result = self.f._load_blob(
                unittest.mock.sentinel.type_,
                level,
                unittest.mock.sentinel.namespace,
                unittest.mock.sentinel.name,
                unittest.mock.sentinel.query,
            )

            _get_sessionmaker.assert_called_once_with(
                unittest.mock.sentinel.type_,
                mlxc.storage.common.StorageLevel.IDENTITY,
                unittest.mock.sentinel.namespace,
            )

            session_scope.assert_called_once_with(
                _get_sessionmaker(),
            )

            get.assert_called_once_with(
                _get_sessionmaker()(),
                level,
                unittest.mock.sentinel.name,
                unittest.mock.sentinel.query,
            )

            self.assertEqual(get(), result)

    def test__load_in_executor_uses__load_blob(self):
        with contextlib.ExitStack() as stack:
            _load_blob = stack.enter_context(
                unittest.mock.patch.object(self.f, "_load_blob")
            )

            run_in_executor = stack.enter_context(
                unittest.mock.patch.object(
                    asyncio.get_event_loop(),
                    "run_in_executor",
                    new=CoroutineMock(),
                )
            )
            run_in_executor.return_value = unittest.mock.sentinel.data

            result = run_coroutine(self.f._load_in_executor(
                unittest.mock.sentinel.type_,
                unittest.mock.sentinel.level,
                unittest.mock.sentinel.namespace,
                unittest.mock.sentinel.name,
                unittest.mock.sentinel.query,
                touch=unittest.mock.sentinel.touch,
            ))

            run_in_executor.assert_called_once_with(
                None,
                unittest.mock.ANY,
            )

            _load_blob.assert_not_called()

            _, (_, func), _ = run_in_executor.mock_calls[0]
            func()

            _load_blob.assert_called_once_with(
                unittest.mock.sentinel.type_,
                unittest.mock.sentinel.level,
                unittest.mock.sentinel.namespace,
                unittest.mock.sentinel.name,
                unittest.mock.sentinel.query,
                touch=unittest.mock.sentinel.touch,
            )

            self.assertEqual(result, unittest.mock.sentinel.data)

    def test__load_in_executor_defaults(self):
        with contextlib.ExitStack() as stack:
            _load_blob = stack.enter_context(
                unittest.mock.patch.object(self.f, "_load_blob")
            )

            run_in_executor = stack.enter_context(
                unittest.mock.patch.object(
                    asyncio.get_event_loop(),
                    "run_in_executor",
                    new=CoroutineMock(),
                )
            )
            run_in_executor.return_value = unittest.mock.sentinel.data

            result = run_coroutine(self.f._load_in_executor(
                unittest.mock.sentinel.type_,
                unittest.mock.sentinel.level,
                unittest.mock.sentinel.namespace,
                unittest.mock.sentinel.name,
                unittest.mock.sentinel.query,
            ))

            run_in_executor.assert_called_once_with(
                None,
                unittest.mock.ANY,
            )

            _load_blob.assert_not_called()

            _, (_, func), _ = run_in_executor.mock_calls[0]
            func()

            _load_blob.assert_called_once_with(
                unittest.mock.sentinel.type_,
                unittest.mock.sentinel.level,
                unittest.mock.sentinel.namespace,
                unittest.mock.sentinel.name,
                unittest.mock.sentinel.query,
                touch=False,
            )

            self.assertEqual(result, unittest.mock.sentinel.data)

    def test__unlink_blob_peer_level(self):
        with contextlib.ExitStack() as stack:
            _get_sessionmaker = stack.enter_context(
                unittest.mock.patch.object(self.f, "_get_sessionmaker")
            )

            session_scope = unittest.mock.MagicMock()
            session_scope.side_effect = mlxc.storage.common.session_scope
            stack.enter_context(
                unittest.mock.patch(
                    "mlxc.storage.common.session_scope",
                    new=session_scope
                )
            )

            filter_by = stack.enter_context(
                unittest.mock.patch.object(
                    mlxc.storage.peer_model.SmallBlob,
                    "filter_by",
                )
            )

            level = frontends.PeerLevel(
                unittest.mock.sentinel.identity,
                unittest.mock.sentinel.peer,
            )

            result = self.f._unlink_blob(
                unittest.mock.sentinel.type_,
                level,
                unittest.mock.sentinel.namespace,
                unittest.mock.sentinel.name,
            )

            _get_sessionmaker.assert_called_once_with(
                unittest.mock.sentinel.type_,
                mlxc.storage.common.StorageLevel.PEER,
                unittest.mock.sentinel.namespace,
            )

            session_scope.assert_called_once_with(
                _get_sessionmaker(),
            )

            session = _get_sessionmaker()()
            session.query.assert_called_once_with(
                mlxc.storage.peer_model.SmallBlob,
            )
            filter_by.assert_called_once_with(
                session.query(),
                level,
                unittest.mock.sentinel.name,
            )
            filter_by().delete.assert_called_once_with()

            self.assertEqual(
                result,
                filter_by().delete()
            )

    def test__unlink_blob_identity_level(self):
        with contextlib.ExitStack() as stack:
            _get_sessionmaker = stack.enter_context(
                unittest.mock.patch.object(self.f, "_get_sessionmaker")
            )

            session_scope = unittest.mock.MagicMock()
            session_scope.side_effect = mlxc.storage.common.session_scope
            stack.enter_context(
                unittest.mock.patch(
                    "mlxc.storage.common.session_scope",
                    new=session_scope
                )
            )

            filter_by = stack.enter_context(
                unittest.mock.patch.object(
                    mlxc.storage.identity_model.SmallBlob,
                    "filter_by",
                )
            )

            level = frontends.IdentityLevel(
                unittest.mock.sentinel.identity,
            )

            result = self.f._unlink_blob(
                unittest.mock.sentinel.type_,
                level,
                unittest.mock.sentinel.namespace,
                unittest.mock.sentinel.name,
            )

            _get_sessionmaker.assert_called_once_with(
                unittest.mock.sentinel.type_,
                mlxc.storage.common.StorageLevel.IDENTITY,
                unittest.mock.sentinel.namespace,
            )

            session_scope.assert_called_once_with(
                _get_sessionmaker(),
            )

            session = _get_sessionmaker()()
            session.query.assert_called_once_with(
                mlxc.storage.identity_model.SmallBlob,
            )
            filter_by.assert_called_once_with(
                session.query(),
                level,
                unittest.mock.sentinel.name,
            )
            filter_by().delete.assert_called_once_with()

            self.assertEqual(
                result,
                filter_by().delete()
            )

    def test__unlink_blob_account_level(self):
        with contextlib.ExitStack() as stack:
            _get_sessionmaker = stack.enter_context(
                unittest.mock.patch.object(self.f, "_get_sessionmaker")
            )

            session_scope = unittest.mock.MagicMock()
            session_scope.side_effect = mlxc.storage.common.session_scope
            stack.enter_context(
                unittest.mock.patch(
                    "mlxc.storage.common.session_scope",
                    new=session_scope
                )
            )

            filter_by = stack.enter_context(
                unittest.mock.patch.object(
                    mlxc.storage.account_model.SmallBlob,
                    "filter_by",
                )
            )

            level = frontends.AccountLevel(
                unittest.mock.sentinel.account,
            )

            result = self.f._unlink_blob(
                unittest.mock.sentinel.type_,
                level,
                unittest.mock.sentinel.namespace,
                unittest.mock.sentinel.name,
            )

            _get_sessionmaker.assert_called_once_with(
                unittest.mock.sentinel.type_,
                mlxc.storage.common.StorageLevel.ACCOUNT,
                unittest.mock.sentinel.namespace,
            )

            session_scope.assert_called_once_with(
                _get_sessionmaker(),
            )

            session = _get_sessionmaker()()
            session.query.assert_called_once_with(
                mlxc.storage.account_model.SmallBlob,
            )
            filter_by.assert_called_once_with(
                session.query(),
                level,
                unittest.mock.sentinel.name,
            )
            filter_by().delete.assert_called_once_with()

            self.assertEqual(
                result,
                filter_by().delete()
            )

    def test__unlink_in_executor_uses__unlink_blob(self):
        with contextlib.ExitStack() as stack:
            _unlink_blob = stack.enter_context(
                unittest.mock.patch.object(self.f, "_unlink_blob")
            )

            run_in_executor = stack.enter_context(
                unittest.mock.patch.object(
                    asyncio.get_event_loop(),
                    "run_in_executor",
                    new=CoroutineMock(),
                )
            )
            run_in_executor.return_value = unittest.mock.sentinel.data

            result = run_coroutine(self.f._unlink_in_executor(
                unittest.mock.sentinel.type_,
                unittest.mock.sentinel.level,
                unittest.mock.sentinel.namespace,
                unittest.mock.sentinel.name,
            ))

            run_in_executor.assert_called_once_with(
                None,
                _unlink_blob,
                unittest.mock.sentinel.type_,
                unittest.mock.sentinel.level,
                unittest.mock.sentinel.namespace,
                unittest.mock.sentinel.name,
            )

            self.assertEqual(result, unittest.mock.sentinel.data)

    def test_load_uses__load_in_executor(self):
        with contextlib.ExitStack() as stack:
            _load_in_executor = stack.enter_context(
                unittest.mock.patch.object(
                    self.f, "_load_in_executor",
                    new=CoroutineMock()
                )
            )
            _load_in_executor.return_value = unittest.mock.sentinel.data,

            result = run_coroutine(self.f.load(
                unittest.mock.sentinel.type_,
                unittest.mock.sentinel.level,
                unittest.mock.sentinel.namespace,
                unittest.mock.sentinel.name,
            ))

            _load_in_executor.assert_called_once_with(
                unittest.mock.sentinel.type_,
                unittest.mock.sentinel.level,
                unittest.mock.sentinel.namespace,
                unittest.mock.sentinel.name,
                [
                    mlxc.storage.common.SmallBlobMixin.data,
                ],
                touch=True,
            )

            self.assertEqual(result, unittest.mock.sentinel.data)

    def test_open_raises_on_writable_mode(self):
        modes = itertools.product(
            [
                "r+",
                "w",
                "w+",
                "x",
                "x+",
                "a",
                "a+"
            ],
            [
                "",
                "b",
                "t",
            ]
        )

        for mode in modes:
            mode = "".join(mode)
            with self.assertRaisesRegexp(
                    ValueError,
                    "writable open modes are not supported by "
                    "SmallBlobFrontend"):
                run_coroutine(self.f.open(
                    unittest.mock.sentinel.type_,
                    unittest.mock.sentinel.level,
                    unittest.mock.sentinel.namespace,
                    unittest.mock.sentinel.name,
                    mode,
                ))

    def test_open_uses_load_and_wraps_in_StringIO_for_text_modes(self):
        modes = [
            None,
            "r",
            "rt",
        ]

        for mode in modes:
            with contextlib.ExitStack() as stack:
                getdefaultencoding = stack.enter_context(
                    unittest.mock.patch("sys.getdefaultencoding")
                )
                getdefaultencoding.return_value = \
                    unittest.mock.sentinel.defaultencoding

                StringIO = stack.enter_context(
                    unittest.mock.patch("io.StringIO")
                )

                raw = unittest.mock.Mock()
                load = stack.enter_context(
                    unittest.mock.patch.object(
                        self.f, "load",
                        new=CoroutineMock()
                    )
                )
                load.return_value = raw

                if mode is None:
                    args = ()
                else:
                    args = (mode,)

                result = run_coroutine(self.f.open(
                    unittest.mock.sentinel.type_,
                    unittest.mock.sentinel.level,
                    unittest.mock.sentinel.namespace,
                    unittest.mock.sentinel.name,
                    *args,
                ))

                load.assert_called_once_with(
                    unittest.mock.sentinel.type_,
                    unittest.mock.sentinel.level,
                    unittest.mock.sentinel.namespace,
                    unittest.mock.sentinel.name,
                )

                raw.decode.assert_called_once_with(
                    unittest.mock.sentinel.defaultencoding
                )

                StringIO.assert_called_once_with(raw.decode())

                self.assertEqual(result, StringIO())

    def test_open_allows_custom_encoding_for_text_modes(self):
        modes = [
            None,
            "r",
            "rt",
        ]

        for mode in modes:
            with contextlib.ExitStack() as stack:
                getdefaultencoding = stack.enter_context(
                    unittest.mock.patch("sys.getdefaultencoding")
                )
                getdefaultencoding.return_value = \
                    unittest.mock.sentinel.defaultencoding

                StringIO = stack.enter_context(
                    unittest.mock.patch("io.StringIO")
                )

                raw = unittest.mock.Mock()
                load = stack.enter_context(
                    unittest.mock.patch.object(
                        self.f, "load",
                        new=CoroutineMock()
                    )
                )
                load.return_value = raw

                if mode is None:
                    args = ()
                else:
                    args = (mode,)

                result = run_coroutine(self.f.open(
                    unittest.mock.sentinel.type_,
                    unittest.mock.sentinel.level,
                    unittest.mock.sentinel.namespace,
                    unittest.mock.sentinel.name,
                    *args,
                    encoding=unittest.mock.sentinel.encoding,
                ))

                load.assert_called_once_with(
                    unittest.mock.sentinel.type_,
                    unittest.mock.sentinel.level,
                    unittest.mock.sentinel.namespace,
                    unittest.mock.sentinel.name,
                )

                raw.decode.assert_called_once_with(
                    unittest.mock.sentinel.encoding
                )

                StringIO.assert_called_once_with(raw.decode())

                self.assertEqual(result, StringIO())

    def test_open_uses_load_and_wraps_in_BytesIO_for_binary_modes(self):
        modes = [
            "rb",
        ]

        for mode in modes:
            with contextlib.ExitStack() as stack:
                BytesIO = stack.enter_context(
                    unittest.mock.patch("io.BytesIO")
                )

                raw = unittest.mock.Mock()
                load = stack.enter_context(
                    unittest.mock.patch.object(
                        self.f, "load",
                        new=CoroutineMock()
                    )
                )
                load.return_value = raw

                result = run_coroutine(self.f.open(
                    unittest.mock.sentinel.type_,
                    unittest.mock.sentinel.level,
                    unittest.mock.sentinel.namespace,
                    unittest.mock.sentinel.name,
                    mode,
                ))

                load.assert_called_once_with(
                    unittest.mock.sentinel.type_,
                    unittest.mock.sentinel.level,
                    unittest.mock.sentinel.namespace,
                    unittest.mock.sentinel.name,
                )

                raw.decode.assert_not_called()

                BytesIO.assert_called_once_with(raw)

                self.assertEqual(result, BytesIO())

    def test_open_raises_ValueError_on_encoding_with_binary_mode(self):
        modes = [
            "rb",
        ]

        for mode in modes:
            with contextlib.ExitStack() as stack:
                load = stack.enter_context(
                    unittest.mock.patch.object(
                        self.f, "load",
                        new=CoroutineMock()
                    )
                )

                stack.enter_context(
                    self.assertRaisesRegexp(
                        ValueError,
                        "binary mode doesn't take an encoding argument")
                )

                run_coroutine(self.f.open(
                    unittest.mock.sentinel.type_,
                    unittest.mock.sentinel.level,
                    unittest.mock.sentinel.namespace,
                    unittest.mock.sentinel.name,
                    mode,
                    encoding=unittest.mock.sentinel.encoding
                ))

            load.assert_not_called()

    def test_open_raises_FileNotFoundError_when_load_raises_KeyError(self):
        modes = ["r", "rb", "rt"]

        for mode in modes:
            exc = KeyError()

            with contextlib.ExitStack() as stack:
                load = stack.enter_context(
                    unittest.mock.patch.object(
                        self.f, "load",
                        new=CoroutineMock()
                    )
                )
                load.side_effect = exc

                ctx = stack.enter_context(
                    self.assertRaisesRegexp(
                        FileNotFoundError,
                        "sentinel\.name does not exist in namespace "
                        "sentinel\.namespace for sentinel\.level"
                    )
                )

                run_coroutine(self.f.open(
                    unittest.mock.sentinel.type_,
                    unittest.mock.sentinel.level,
                    unittest.mock.sentinel.namespace,
                    unittest.mock.sentinel.name,
                    mode,
                ))

            self.assertEqual(
                ctx.exception.__cause__,
                exc,
            )

    def test_stat_uses__load_in_executor(self):
        EPOCH = datetime(1970, 1, 1)

        accessed = datetime(2017, 4, 29, 15, 23, 0)
        created = datetime(2017, 4, 29, 15, 20, 0)
        modified = datetime(2017, 4, 29, 15, 21, 0)

        with contextlib.ExitStack() as stack:
            _load_in_executor = stack.enter_context(
                unittest.mock.patch.object(
                    self.f, "_load_in_executor",
                    new=CoroutineMock()
                )
            )
            _load_in_executor.return_value = (
                accessed,
                created,
                modified,
                unittest.mock.sentinel.len_,
            )

            result = run_coroutine(self.f.stat(
                unittest.mock.sentinel.type_,
                unittest.mock.sentinel.level,
                unittest.mock.sentinel.namespace,
                unittest.mock.sentinel.name,
            ))

            _load_in_executor.assert_called_once_with(
                unittest.mock.sentinel.type_,
                unittest.mock.sentinel.level,
                unittest.mock.sentinel.namespace,
                unittest.mock.sentinel.name,
                [
                    mlxc.storage.common.SmallBlobMixin.accessed,
                    mlxc.storage.common.SmallBlobMixin.created,
                    mlxc.storage.common.SmallBlobMixin.modified,
                    unittest.mock.ANY,
                ]
            )

            self.assertEqual(
                result.st_atime,
                (accessed - EPOCH).total_seconds()
            )

            self.assertEqual(
                result.st_birthtime,
                (created - EPOCH).total_seconds()
            )

            self.assertEqual(
                result.st_mtime,
                (modified - EPOCH).total_seconds()
            )

            self.assertEqual(
                result.st_size,
                unittest.mock.sentinel.len_,
            )

    def test_stat_raises_FileNotFoundError_when__load_blob_raises_KeyError(self):  # NOQA
        exc = KeyError()

        with contextlib.ExitStack() as stack:
            _load_in_executor = stack.enter_context(
                unittest.mock.patch.object(
                    self.f, "_load_in_executor",
                    new=CoroutineMock()
                )
            )
            _load_in_executor.side_effect = exc

            ctx = stack.enter_context(
                self.assertRaisesRegexp(
                    FileNotFoundError,
                    "sentinel\.name does not exist in namespace "
                    "sentinel\.namespace for sentinel\.level"
                )
            )

            run_coroutine(self.f.stat(
                unittest.mock.sentinel.type_,
                unittest.mock.sentinel.level,
                unittest.mock.sentinel.namespace,
                unittest.mock.sentinel.name,
            ))

        self.assertEqual(
            ctx.exception.__cause__,
            exc,
        )

        _load_in_executor.assert_called_once_with(
            unittest.mock.sentinel.type_,
            unittest.mock.sentinel.level,
            unittest.mock.sentinel.namespace,
            unittest.mock.sentinel.name,
            [
                mlxc.storage.common.SmallBlobMixin.accessed,
                mlxc.storage.common.SmallBlobMixin.created,
                mlxc.storage.common.SmallBlobMixin.modified,
                unittest.mock.ANY,
            ]
        )

    def test_unlink_uses__unlink_in_executor(self):
        with contextlib.ExitStack() as stack:
            _unlink_in_executor = stack.enter_context(
                unittest.mock.patch.object(
                    self.f,
                    "_unlink_in_executor",
                    new=CoroutineMock(),
                )
            )
            _unlink_in_executor.return_value = 1

            run_coroutine(self.f.unlink(
                unittest.mock.sentinel.type_,
                unittest.mock.sentinel.level,
                unittest.mock.sentinel.namespace,
                unittest.mock.sentinel.name,
            ))

            _unlink_in_executor.assert_called_once_with(
                unittest.mock.sentinel.type_,
                unittest.mock.sentinel.level,
                unittest.mock.sentinel.namespace,
                unittest.mock.sentinel.name,
            )

    def test_unlink_raises_FileNotFoundError_if_non_existant(self):
        with contextlib.ExitStack() as stack:
            _unlink_in_executor = stack.enter_context(
                unittest.mock.patch.object(
                    self.f,
                    "_unlink_in_executor",
                    new=CoroutineMock(),
                )
            )
            _unlink_in_executor.return_value = 0

            stack.enter_context(
                self.assertRaisesRegexp(
                    FileNotFoundError,
                    "sentinel\.name does not exist in namespace "
                    "sentinel\.namespace for sentinel\.level"
                )
            )

            run_coroutine(self.f.unlink(
                unittest.mock.sentinel.type_,
                unittest.mock.sentinel.level,
                unittest.mock.sentinel.namespace,
                unittest.mock.sentinel.name,
            ))

        _unlink_in_executor.assert_called_once_with(
            unittest.mock.sentinel.type_,
            unittest.mock.sentinel.level,
            unittest.mock.sentinel.namespace,
            unittest.mock.sentinel.name,
        )

    def test_store_load_cycle(self):
        account = uuid.uuid4()
        peer = aioxmpp.JID.fromstr("romeo@montague.lit")
        data1 = "∀x∈X: ∃y∈Y: x<y".encode("utf-8")

        descriptor = frontends.PeerLevel(
            account,
            peer,
        )

        with contextlib.ExitStack() as stack:
            _get_sessionmaker = stack.enter_context(
                unittest.mock.patch.object(self.f, "_get_sessionmaker")
            )
            _get_sessionmaker.return_value = inmemory_database(
                mlxc.storage.peer_model.Base,
            )

            run_coroutine(self.f.store(
                unittest.mock.sentinel.type_,
                descriptor,
                unittest.mock.sentinel.namespace,
                "some name",
                data1,
            ))

            self.assertEqual(
                run_coroutine(self.f.load(
                    unittest.mock.sentinel.type_,
                    descriptor,
                    unittest.mock.sentinel.namespace,
                    "some name",
                )),
                data1,
            )

    def test_store_unlink_cycle(self):
        account = uuid.uuid4()
        peer = aioxmpp.JID.fromstr("romeo@montague.lit")
        data1 = "∀x∈X: ∃y∈Y: x<y".encode("utf-8")

        descriptor = frontends.PeerLevel(
            account,
            peer,
        )

        with contextlib.ExitStack() as stack:
            _get_sessionmaker = stack.enter_context(
                unittest.mock.patch.object(self.f, "_get_sessionmaker")
            )
            _get_sessionmaker.return_value = inmemory_database(
                mlxc.storage.peer_model.Base,
            )

            run_coroutine(self.f.store(
                unittest.mock.sentinel.type_,
                descriptor,
                unittest.mock.sentinel.namespace,
                "some name",
                data1,
            ))

            run_coroutine(self.f.unlink(
                unittest.mock.sentinel.type_,
                descriptor,
                unittest.mock.sentinel.namespace,
                "some name",
            ))

            with self.assertRaises(KeyError):
                run_coroutine(self.f.load(
                    unittest.mock.sentinel.type_,
                    descriptor,
                    unittest.mock.sentinel.namespace,
                    "some name",
                ))

            with self.assertRaises(FileNotFoundError):
                run_coroutine(self.f.unlink(
                    unittest.mock.sentinel.type_,
                    descriptor,
                    unittest.mock.sentinel.namespace,
                    "some name",
                ))

    def test_stat_calculates_length_properly(self):
        account = uuid.uuid4()
        peer = aioxmpp.JID.fromstr("romeo@montague.lit")
        data1 = "∀x∈X: ∃y∈Y: x<y".encode("utf-8")
        data2 = "simple text".encode("utf-8")

        descriptor = frontends.PeerLevel(
            account,
            peer,
        )

        with contextlib.ExitStack() as stack:
            _get_sessionmaker = stack.enter_context(
                unittest.mock.patch.object(self.f, "_get_sessionmaker")
            )
            _get_sessionmaker.return_value = inmemory_database(
                mlxc.storage.peer_model.Base,
            )

            run_coroutine(self.f.store(
                unittest.mock.sentinel.type_,
                descriptor,
                unittest.mock.sentinel.namespace,
                "some name",
                data1,
            ))

            result = run_coroutine(self.f.stat(
                unittest.mock.sentinel.type_,
                descriptor,
                unittest.mock.sentinel.namespace,
                "some name",
            ))

            self.assertEqual(
                result.st_size,
                len(data1)
            )

            run_coroutine(self.f.store(
                unittest.mock.sentinel.type_,
                descriptor,
                unittest.mock.sentinel.namespace,
                "some name",
                data2,
            ))

            result = run_coroutine(self.f.stat(
                unittest.mock.sentinel.type_,
                descriptor,
                unittest.mock.sentinel.namespace,
                "some name",
            ))

            self.assertEqual(
                result.st_size,
                len(data2)
            )
