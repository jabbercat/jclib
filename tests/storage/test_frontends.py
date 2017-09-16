import asyncio
import contextlib
import itertools
import pathlib
import tempfile
import unittest
import unittest.mock
import uuid

from datetime import datetime

import aioxmpp

import jclib.storage.account_model
import jclib.storage.common
import jclib.storage.peer_model
import jclib.storage.frontends as frontends

from aioxmpp.testutils import (
    run_coroutine,
    CoroutineMock,
)

from jclib.testutils import (
    inmemory_database,
)


NS = "https://xmlns.jabbercat.org/test/jclib.storage.frontends"


class MockBackend(jclib.storage.backends.Backend):
    def __init__(self):
        self.__tempdir = tempfile.TemporaryDirectory()
        self.__dirname = None

    def type_base_paths(self, type_, writable):
        return [pathlib.Path(
            self.__dirname,
        ) / type_.value]

    def __enter__(self):
        self.__dirname = self.__tempdir.__enter__()
        return self

    def __exit__(self, exc_type, exc_value, tb):
        self.__dirname = None
        self.__tempdir.__exit__(exc_type, exc_value, tb)


class Data1(aioxmpp.xso.XSO):
    TAG = (NS, "data1")

    foo = aioxmpp.xso.Attr("foo")
    bar = aioxmpp.xso.Text()


class Data2(aioxmpp.xso.XSO):
    TAG = (NS, "data2")

    foo = aioxmpp.xso.Child([Data1])


for level_type in frontends.StorageLevel:
    if level_type == frontends.StorageLevel.GLOBAL:
        continue
    frontends.XMLFrontend.register(level_type, Data1)
    frontends.XMLFrontend.register(level_type, Data2)


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


class Testescape_path_part(unittest.TestCase):
    def test_urlencdoes_argument(self):
        with contextlib.ExitStack() as stack:
            quote = stack.enter_context(
                unittest.mock.patch("urllib.parse.quote")
            )

            result = frontends.escape_path_part(
                unittest.mock.sentinel.part
            )

        quote.assert_called_once_with(
            unittest.mock.sentinel.part,
            safe=" "
        )

        self.assertEqual(result, quote())


class Testencode_uuid(unittest.TestCase):
    def test_encodes_uuid_as_base32(self):
        uid = unittest.mock.Mock()

        with contextlib.ExitStack() as stack:
            b32encode = stack.enter_context(
                unittest.mock.patch("base64.b32encode")
            )

            Path = stack.enter_context(
                unittest.mock.patch("pathlib.Path")
            )

            result = frontends.encode_uuid(uid)

            b32encode.assert_called_once_with(
                uid.bytes,
            )

            b32encode().decode.assert_called_once_with("ascii")
            b32encode().decode().rstrip.assert_called_once_with("=")
            b32encode().decode().rstrip().lower.assert_called_once_with()

            Path.assert_called_once_with(
                b32encode().decode().rstrip().lower()
            )

            self.assertEqual(
                result,
                Path(),
            )


class TestAccountLevel(unittest.TestCase):
    def test_key_path(self):
        il = frontends.AccountLevel(
            unittest.mock.sentinel.account,
        )

        with contextlib.ExitStack() as stack:
            encode_jid = stack.enter_context(
                unittest.mock.patch("jclib.storage.frontends.encode_jid")
            )

            result = il.key_path

            encode_jid.assert_called_once_with(
                unittest.mock.sentinel.account
            )

            self.assertEqual(
                result,
                encode_jid()
            )


class TestPeerLevel(unittest.TestCase):
    def test_key_path(self):
        encoded = unittest.mock.MagicMock()

        def generate_results():
            for i in itertools.count():
                yield getattr(
                    encoded, "jid{}".format(i)
                )

        il = frontends.PeerLevel(
            unittest.mock.sentinel.account,
            unittest.mock.sentinel.peer,
        )

        with contextlib.ExitStack() as stack:
            encode_jid = stack.enter_context(
                unittest.mock.patch("jclib.storage.frontends.encode_jid")
            )
            encode_jid.side_effect = generate_results()

            result = il.key_path

            self.assertSequenceEqual(
                encode_jid.mock_calls,
                [
                    unittest.mock.call(unittest.mock.sentinel.account),
                    unittest.mock.call(unittest.mock.sentinel.peer),
                ]
            )

            encoded.jid0.__truediv__.assert_called_once_with(encoded.jid1)

            self.assertEqual(
                result,
                encoded.jid0.__truediv__()
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

        with contextlib.ExitStack() as stack:
            escape_path_part = stack.enter_context(
                unittest.mock.patch("jclib.storage.frontends.escape_path_part")
            )

            result = self.f._get_path(
                unittest.mock.sentinel.type_,
                level_type,
                unittest.mock.sentinel.namespace,
                unittest.mock.sentinel.frontend_name,
                unittest.mock.sentinel.name,
            )

        self.backend.type_base_paths.assert_called_once_with(
            unittest.mock.sentinel.type_,
            True,
        )

        escape_path_part.assert_called_once_with(
            unittest.mock.sentinel.namespace
        )

        path_mock.__truediv__.assert_called_once_with(
            frontends.StorageLevel.GLOBAL.value
        )
        path_mock.__truediv__().__truediv__.assert_called_once_with(
            escape_path_part(),
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

        with contextlib.ExitStack() as stack:
            escape_path_part = stack.enter_context(
                unittest.mock.patch("jclib.storage.frontends.escape_path_part")
            )

            result = self.f._get_path(
                unittest.mock.sentinel.type_,
                level,
                unittest.mock.sentinel.namespace,
                unittest.mock.sentinel.name,
            )

        self.backend.type_base_paths.assert_called_once_with(
            unittest.mock.sentinel.type_,
            True,
        )

        escape_path_part.assert_called_once_with(
            unittest.mock.sentinel.namespace
        )

        path_mock.__truediv__.assert_called_once_with(level.level.value)
        path_mock.__truediv__().__truediv__.assert_called_once_with(
            level.key_path
        )
        path_mock.__truediv__().__truediv__().__truediv__\
            .assert_called_once_with(
                escape_path_part()
            )
        path_mock.__truediv__().__truediv__().__truediv__().__truediv__\
            .assert_called_once_with(
                unittest.mock.sentinel.name,
            )

        self.assertEqual(
            result,
            path_mock.__truediv__().__truediv__().__truediv__().__truediv__()
        )


class Test_get_engine(unittest.TestCase):
    def test__get_engine(self):
        path = unittest.mock.Mock()

        with contextlib.ExitStack() as stack:
            create_engine = stack.enter_context(
                unittest.mock.patch("sqlalchemy.create_engine")
            )

            mkdir_exist_ok = stack.enter_context(
                unittest.mock.patch("jclib.utils.mkdir_exist_ok")
            )

            listens_for = stack.enter_context(
                unittest.mock.patch("sqlalchemy.event.listens_for")
            )

            result = frontends._get_engine(
                path,
            )

            mkdir_exist_ok.assert_called_once_with(
                path.parent
            )

            create_engine.assert_called_once_with(
                "sqlite:///{}".format(path),
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


class TestDatabaseFrontend(unittest.TestCase):
    def setUp(self):
        self.backend = unittest.mock.Mock()
        self.f = frontends.DatabaseFrontend(self.backend)

    def test__get_path(self):
        path_mock = unittest.mock.MagicMock()
        self.backend.type_base_paths.return_value = [path_mock]

        with contextlib.ExitStack() as stack:
            escape_path_part = stack.enter_context(
                unittest.mock.patch("jclib.storage.frontends.escape_path_part")
            )

            result = self.f._get_path(
                unittest.mock.sentinel.type_,
                unittest.mock.sentinel.namespace,
                unittest.mock.sentinel.name,
            )

        self.backend.type_base_paths.assert_called_once_with(
            unittest.mock.sentinel.type_,
            True,
        )

        escape_path_part.assert_called_once_with(
            unittest.mock.sentinel.namespace
        )

        path_mock.__truediv__.assert_called_once_with(
            frontends.StorageLevel.GLOBAL.value
        )
        path_mock.__truediv__().__truediv__.assert_called_once_with(
            escape_path_part(),
        )
        path_mock.__truediv__().__truediv__().__truediv__\
            .assert_called_once_with(
                "db"
            )
        path_mock.__truediv__().__truediv__().__truediv__().__truediv__\
            .assert_called_once_with(
                unittest.mock.sentinel.name
            )

        self.assertEqual(
            result,
            path_mock.__truediv__().__truediv__().__truediv__().__truediv__()
        )

    def test_get_engine(self):
        with contextlib.ExitStack() as stack:
            _get_engine = stack.enter_context(
                unittest.mock.patch(
                    "jclib.storage.frontends._get_engine"
                )
            )

            _get_path = stack.enter_context(
                unittest.mock.patch.object(self.f, "_get_path")
            )

            sessionmaker = stack.enter_context(
                unittest.mock.patch("sqlalchemy.orm.sessionmaker")
            )

            result = self.f.get_engine(
                unittest.mock.sentinel.type_,
                unittest.mock.sentinel.level,
                unittest.mock.sentinel.namespace,
            )

            _get_path.assert_called_once_with(
                unittest.mock.sentinel.type_,
                unittest.mock.sentinel.level,
                unittest.mock.sentinel.namespace,
            )

            _get_engine.assert_called_once_with(_get_path())

            sessionmaker.assert_not_called()

            self.assertEqual(
                result,
                _get_engine(),
            )

    def test_get_engine_is_lru_cache(self):
        self.assertTrue(hasattr(type(self.f).get_engine, "cache_info"))



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
                    unittest.mock.patch("jclib.utils.mkdir_exist_ok")
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
                unittest.mock.patch("jclib.utils.mkdir_exist_ok")
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
                    unittest.mock.patch("jclib.utils.mkdir_exist_ok")
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
                unittest.mock.patch("jclib.utils.mkdir_exist_ok")
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
                unittest.mock.patch("jclib.utils.mkdir_exist_ok")
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

        self.backend.type_base_paths.assert_called_once_with(
            unittest.mock.sentinel.type_,
            True,
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

    def test__init_engine_for_peer(self):
        with contextlib.ExitStack() as stack:
            peer_metadata = stack.enter_context(
                unittest.mock.patch.object(
                    jclib.storage.peer_model.Base,
                    "metadata"
                )
            )

            account_metadata = stack.enter_context(
                unittest.mock.patch.object(
                    jclib.storage.account_model.Base,
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

            account_metadata.create_all.assert_not_called()

    def test__init_engine_for_account(self):
        with contextlib.ExitStack() as stack:
            peer_metadata = stack.enter_context(
                unittest.mock.patch.object(
                    jclib.storage.peer_model.Base,
                    "metadata"
                )
            )

            account_metadata = stack.enter_context(
                unittest.mock.patch.object(
                    jclib.storage.account_model.Base,
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

    def test__init_engine_fails_for_global(self):
        with contextlib.ExitStack() as stack:
            peer_metadata = stack.enter_context(
                unittest.mock.patch.object(
                    jclib.storage.peer_model.Base,
                    "metadata"
                )
            )

            account_metadata = stack.enter_context(
                unittest.mock.patch.object(
                    jclib.storage.account_model.Base,
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

    def test__init_engine_fails_for_unknown_enum(self):
        with contextlib.ExitStack() as stack:
            peer_metadata = stack.enter_context(
                unittest.mock.patch.object(
                    jclib.storage.peer_model.Base,
                    "metadata"
                )
            )

            account_metadata = stack.enter_context(
                unittest.mock.patch.object(
                    jclib.storage.account_model.Base,
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

    def test__get_sessionmaker(self):
        with contextlib.ExitStack() as stack:
            _get_engine = stack.enter_context(
                unittest.mock.patch(
                    "jclib.storage.frontends._get_engine"
                )
            )

            _get_path = stack.enter_context(
                unittest.mock.patch.object(self.f, "_get_path")
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

            _get_path.assert_called_once_with(
                unittest.mock.sentinel.type_,
                unittest.mock.sentinel.level,
                unittest.mock.sentinel.namespace,
            )

            _get_engine.assert_called_once_with(_get_path())

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
            session_scope.side_effect = jclib.storage.common.session_scope
            stack.enter_context(
                unittest.mock.patch(
                    "jclib.storage.common.session_scope",
                    new=session_scope
                )
            )

            touch_mtime = stack.enter_context(
                unittest.mock.patch.object(
                    jclib.storage.peer_model.SmallBlob,
                    "touch_mtime",
                )
            )

            self.f._store_blob(
                unittest.mock.sentinel.type_,
                frontends.PeerLevel(
                    unittest.mock.sentinel.account,
                    unittest.mock.sentinel.peer,
                ),
                unittest.mock.sentinel.namespace,
                unittest.mock.sentinel.name,
                unittest.mock.sentinel.data,
            )

            _get_sessionmaker.assert_called_once_with(
                unittest.mock.sentinel.type_,
                jclib.storage.common.StorageLevel.PEER,
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
                jclib.storage.peer_model.SmallBlob,
            )

            self.assertEqual(
                blob.account,
                unittest.mock.sentinel.account,
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
            session_scope.side_effect = jclib.storage.common.session_scope
            stack.enter_context(
                unittest.mock.patch(
                    "jclib.storage.common.session_scope",
                    new=session_scope
                )
            )

            touch_mtime = stack.enter_context(
                unittest.mock.patch.object(
                    jclib.storage.account_model.SmallBlob,
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
                jclib.storage.common.StorageLevel.ACCOUNT,
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
                jclib.storage.account_model.SmallBlob,
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
            session_scope.side_effect = jclib.storage.common.session_scope
            stack.enter_context(
                unittest.mock.patch(
                    "jclib.storage.common.session_scope",
                    new=session_scope
                )
            )

            get = stack.enter_context(
                unittest.mock.patch.object(
                    jclib.storage.peer_model.SmallBlob,
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
                jclib.storage.common.StorageLevel.PEER,
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
            session_scope.side_effect = jclib.storage.common.session_scope
            stack.enter_context(
                unittest.mock.patch(
                    "jclib.storage.common.session_scope",
                    new=session_scope
                )
            )

            get = stack.enter_context(
                unittest.mock.patch.object(
                    jclib.storage.peer_model.SmallBlob,
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
                jclib.storage.common.StorageLevel.PEER,
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
            session_scope.side_effect = jclib.storage.common.session_scope
            stack.enter_context(
                unittest.mock.patch(
                    "jclib.storage.common.session_scope",
                    new=session_scope
                )
            )

            get = stack.enter_context(
                unittest.mock.patch.object(
                    jclib.storage.account_model.SmallBlob,
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
                jclib.storage.common.StorageLevel.ACCOUNT,
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
            session_scope.side_effect = jclib.storage.common.session_scope
            stack.enter_context(
                unittest.mock.patch(
                    "jclib.storage.common.session_scope",
                    new=session_scope
                )
            )

            filter_by = stack.enter_context(
                unittest.mock.patch.object(
                    jclib.storage.peer_model.SmallBlob,
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
                jclib.storage.common.StorageLevel.PEER,
                unittest.mock.sentinel.namespace,
            )

            session_scope.assert_called_once_with(
                _get_sessionmaker(),
            )

            session = _get_sessionmaker()()
            session.query.assert_called_once_with(
                jclib.storage.peer_model.SmallBlob,
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
            session_scope.side_effect = jclib.storage.common.session_scope
            stack.enter_context(
                unittest.mock.patch(
                    "jclib.storage.common.session_scope",
                    new=session_scope
                )
            )

            filter_by = stack.enter_context(
                unittest.mock.patch.object(
                    jclib.storage.account_model.SmallBlob,
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
                jclib.storage.common.StorageLevel.ACCOUNT,
                unittest.mock.sentinel.namespace,
            )

            session_scope.assert_called_once_with(
                _get_sessionmaker(),
            )

            session = _get_sessionmaker()()
            session.query.assert_called_once_with(
                jclib.storage.account_model.SmallBlob,
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
                    jclib.storage.common.SmallBlobMixin.data,
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
                    jclib.storage.common.SmallBlobMixin.accessed,
                    jclib.storage.common.SmallBlobMixin.created,
                    jclib.storage.common.SmallBlobMixin.modified,
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
                jclib.storage.common.SmallBlobMixin.accessed,
                jclib.storage.common.SmallBlobMixin.created,
                jclib.storage.common.SmallBlobMixin.modified,
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
                jclib.storage.peer_model.Base,
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
                jclib.storage.peer_model.Base,
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
                jclib.storage.peer_model.Base,
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


class TestAppendFrontend(unittest.TestCase):
    def setUp(self):
        self.backend = unittest.mock.Mock()
        self.f = frontends.AppendFrontend(self.backend)

    def test_uses_per_level_key_file_mixin(self):
        self.assertIsInstance(
            self.f,
            frontends._PerLevelKeyFileMixin
        )

    def test_submit_creates_directory_and_appends(self):
        ts = unittest.mock.Mock()
        ts.year = 1234
        ts.month = 2
        ts.day = 1

        with contextlib.ExitStack() as stack:
            _get_path = stack.enter_context(
                unittest.mock.patch.object(
                    self.f,
                    "_get_path",
                )
            )
            _get_path.return_value.open.return_value = unittest.mock.MagicMock(
                ["__enter__", "__exit__"]
            )
            _get_path.return_value.open.return_value.__enter__.return_value = \
                unittest.mock.Mock()

            datetime = stack.enter_context(
                unittest.mock.patch("jclib.storage.frontends.datetime")
            )

            mkdir_exist_ok = stack.enter_context(
                unittest.mock.patch("jclib.utils.mkdir_exist_ok")
            )

            self.f.submit(
                unittest.mock.sentinel.type_,
                unittest.mock.sentinel.level,
                unittest.mock.sentinel.namespace,
                "filename",
                unittest.mock.sentinel.data,
                ts=ts,
            )

            datetime.utcnow.assert_not_called()

            _get_path.assert_called_once_with(
                unittest.mock.sentinel.type_,
                unittest.mock.sentinel.level,
                unittest.mock.sentinel.namespace,
                pathlib.Path("append") / "1234" / "02-01" / "filename"
            )

            mkdir_exist_ok.assert_called_once_with(
                _get_path().parent
            )

            _get_path().open.assert_called_once_with("ab")
            _get_path().open().__enter__.assert_called_once_with()

            f = _get_path().open().__enter__()
            f.write.assert_called_once_with(unittest.mock.sentinel.data)

    def test_submit_uses_current_datetime_if_ts_not_given(self):
        ts = unittest.mock.Mock()
        ts.year = 2345
        ts.month = 12
        ts.day = 2

        with contextlib.ExitStack() as stack:
            _get_path = stack.enter_context(
                unittest.mock.patch.object(
                    self.f,
                    "_get_path",
                )
            )
            _get_path.return_value.open.return_value = unittest.mock.MagicMock(
                ["__enter__", "__exit__"]
            )
            _get_path.return_value.open.return_value.__enter__.return_value = \
                unittest.mock.Mock()

            datetime = stack.enter_context(
                unittest.mock.patch("jclib.storage.frontends.datetime")
            )
            datetime.utcnow.return_value = ts

            self.f.submit(
                unittest.mock.sentinel.type_,
                unittest.mock.sentinel.level,
                unittest.mock.sentinel.namespace,
                "filename",
                unittest.mock.sentinel.data,
            )

            datetime.utcnow.assert_called_once_with()

            _get_path.assert_called_once_with(
                unittest.mock.sentinel.type_,
                unittest.mock.sentinel.level,
                unittest.mock.sentinel.namespace,
                pathlib.Path("append") / "2345" / "12-02" / "filename"
            )

            _get_path().open.assert_called_once_with("ab")
            _get_path().open().__enter__.assert_called_once_with()

            f = _get_path().open().__enter__()
            f.write.assert_called_once_with(unittest.mock.sentinel.data)


class TestXMLFrontend(unittest.TestCase):
    def setUp(self):
        self.backend = unittest.mock.Mock()
        self.f = frontends.XMLFrontend(self.backend)

    def test__get_path(self):
        level_type = unittest.mock.Mock()
        path_mock = unittest.mock.MagicMock()
        self.backend.type_base_paths.return_value = [path_mock]

        with contextlib.ExitStack() as stack:
            escape_path_part = stack.enter_context(
                unittest.mock.patch("jclib.storage.frontends.escape_path_part")
            )

            result = self.f._get_path(
                unittest.mock.sentinel.type_,
                level_type,
            )

        self.backend.type_base_paths.assert_called_once_with(
            unittest.mock.sentinel.type_,
            True,
        )

        escape_path_part.assert_called_once_with(
            "dns:jabbercat.org"
        )

        path_mock.__truediv__.assert_called_once_with(
            frontends.StorageLevel.GLOBAL.value
        )
        path_mock.__truediv__().__truediv__.assert_called_once_with(
            escape_path_part(),
        )
        path_mock.__truediv__().__truediv__().__truediv__\
            .assert_called_once_with(
                "xml-storage"
            )
        path_mock.__truediv__().__truediv__().__truediv__().__truediv__\
            .assert_called_once_with(
                "{}.xml".format(level_type.value)
            )

        self.assertEqual(
            result,
            path_mock.__truediv__().__truediv__().__truediv__().__truediv__()
        )

    def test__get_path_peer(self):
        path_mock = unittest.mock.MagicMock()
        level_type = frontends.StorageLevel.PEER
        self.backend.type_base_paths.return_value = [path_mock]

        with contextlib.ExitStack() as stack:
            escape_path_part = stack.enter_context(
                unittest.mock.patch("jclib.storage.frontends.escape_path_part")
            )

            encode_jid = stack.enter_context(
                unittest.mock.patch("jclib.storage.frontends.encode_jid")
            )

            result = self.f._get_path(
                unittest.mock.sentinel.type_,
                level_type,
                account=unittest.mock.sentinel.account,
            )

        self.backend.type_base_paths.assert_called_once_with(
            unittest.mock.sentinel.type_,
            True,
        )

        escape_path_part.assert_called_once_with(
            "dns:jabbercat.org"
        )

        encode_jid.assert_called_once_with(unittest.mock.sentinel.account)

        path_mock.__truediv__.assert_called_once_with(
            frontends.StorageLevel.ACCOUNT.value
        )
        path_mock.__truediv__().__truediv__.assert_called_once_with(
            encode_jid(),
        )
        path_mock.__truediv__().__truediv__().__truediv__\
            .assert_called_once_with(
                escape_path_part(),
            )
        path_mock.__truediv__().__truediv__().__truediv__().__truediv__\
            .assert_called_once_with(
                "xml-storage"
            )
        path_mock.__truediv__().__truediv__().__truediv__().__truediv__()\
            .__truediv__.assert_called_once_with(
                "{}.xml".format(level_type.value)
            )

        self.assertEqual(
            result,
            path_mock.__truediv__().__truediv__().__truediv__().__truediv__()
            .__truediv__()
        )

    def test__load_account(self):
        level = frontends.AccountLevel(
            unittest.mock.sentinel.account,
        )

        with contextlib.ExitStack() as stack:
            _get_path = stack.enter_context(
                unittest.mock.patch.object(self.f, "_get_path")
            )
            _get_path.return_value = unittest.mock.MagicMock()

            read_single_xso = stack.enter_context(
                unittest.mock.patch("aioxmpp.xml.read_single_xso")
            )

            result = self.f._load(
                unittest.mock.sentinel.type_,
                level,
            )

        _get_path.assert_called_once_with(
            unittest.mock.sentinel.type_,
            level.level,
            account=unittest.mock.ANY,
        )

        _get_path().open.assert_called_once_with(
            "rb",
        )

        read_single_xso.assert_called_once_with(
            _get_path().open().__enter__(),
            jclib.storage.account_model.XMLStorage,
        )

        self.assertEqual(
            result,
            read_single_xso(),
        )

    def test__load_account_returns_fresh_object_if_nonexistant(self):
        level = frontends.AccountLevel(
            unittest.mock.sentinel.account,
        )

        path = unittest.mock.MagicMock()
        path.open.side_effect = FileNotFoundError

        with contextlib.ExitStack() as stack:
            _get_path = stack.enter_context(
                unittest.mock.patch.object(self.f, "_get_path")
            )
            _get_path.return_value = path

            read_single_xso = stack.enter_context(
                unittest.mock.patch("aioxmpp.xml.read_single_xso")
            )

            result = self.f._load(
                unittest.mock.sentinel.type_,
                level,
            )

        _get_path.assert_called_once_with(
            unittest.mock.sentinel.type_,
            level.level,
            account=unittest.mock.ANY,
        )

        _get_path().open.assert_called_once_with(
            "rb",
        )

        self.assertIsInstance(
            result,
            jclib.storage.account_model.XMLStorage,
        )

    def test__load_peer(self):
        level = frontends.PeerLevel(
            unittest.mock.sentinel.account,
            unittest.mock.sentinel.peer,
        )

        with contextlib.ExitStack() as stack:
            _get_path = stack.enter_context(
                unittest.mock.patch.object(self.f, "_get_path")
            )
            _get_path.return_value = unittest.mock.MagicMock()

            read_single_xso = stack.enter_context(
                unittest.mock.patch("aioxmpp.xml.read_single_xso")
            )

            result = self.f._load(
                unittest.mock.sentinel.type_,
                level,
            )

        _get_path.assert_called_once_with(
            unittest.mock.sentinel.type_,
            level.level,
            account=unittest.mock.sentinel.account,
        )

        _get_path().open.assert_called_once_with(
            "rb",
        )

        read_single_xso.assert_called_once_with(
            _get_path().open().__enter__(),
            jclib.storage.peer_model.XMLStorage,
        )

        self.assertEqual(
            result,
            read_single_xso(),
        )

    def test__load_peer_returns_fresh_object_if_nonexistant(self):
        level = frontends.PeerLevel(
            unittest.mock.sentinel.account,
            unittest.mock.sentinel.peer,
        )

        path = unittest.mock.MagicMock()
        path.open.side_effect = FileNotFoundError

        with contextlib.ExitStack() as stack:
            _get_path = stack.enter_context(
                unittest.mock.patch.object(self.f, "_get_path")
            )
            _get_path.return_value = path

            read_single_xso = stack.enter_context(
                unittest.mock.patch("aioxmpp.xml.read_single_xso")
            )

            result = self.f._load(
                unittest.mock.sentinel.type_,
                level,
            )

        _get_path.assert_called_once_with(
            unittest.mock.sentinel.type_,
            level.level,
            account=unittest.mock.sentinel.account,
        )

        _get_path().open.assert_called_once_with(
            "rb",
        )

        self.assertIsInstance(
            result,
            jclib.storage.peer_model.XMLStorage,
        )

    def test__open_uses__load_to_obtain_data(self):
        level = unittest.mock.Mock(spec=frontends.LevelDescriptor)
        level.level = frontends.StorageLevel.ACCOUNT

        with contextlib.ExitStack() as stack:
            _load = stack.enter_context(
                unittest.mock.patch.object(self.f, "_load")
            )

            result = self.f._open(
                unittest.mock.sentinel.type_,
                level,
            )

        _load.assert_called_once_with(
            unittest.mock.sentinel.type_,
            level,
        )

        self.assertEqual(result, _load())

    def test__open_caches_data(self):
        level = unittest.mock.Mock(spec=frontends.LevelDescriptor)
        level.level = frontends.StorageLevel.ACCOUNT

        with contextlib.ExitStack() as stack:
            _load = stack.enter_context(
                unittest.mock.patch.object(self.f, "_load")
            )

            result1 = self.f._open(
                unittest.mock.sentinel.type_,
                level,
            )

            result2 = self.f._open(
                unittest.mock.sentinel.type_,
                level,
            )

        _load.assert_called_once_with(
            unittest.mock.sentinel.type_,
            level,
        )

        self.assertEqual(result1, _load())
        self.assertEqual(result1, result2)

    def test__open_caches_peer_data_by_identity(self):
        level1 = frontends.PeerLevel(
            unittest.mock.sentinel.identity1,
            unittest.mock.sentinel.peer1,
        )

        level2 = frontends.PeerLevel(
            unittest.mock.sentinel.identity1,
            unittest.mock.sentinel.peer2,
        )

        level3 = frontends.PeerLevel(
            unittest.mock.sentinel.identity2,
            unittest.mock.sentinel.peer2,
        )


        def generate_results():
            for i in itertools.count(1):
                yield getattr(unittest.mock.sentinel, "data{}".format(i))


        with contextlib.ExitStack() as stack:
            _load = stack.enter_context(
                unittest.mock.patch.object(self.f, "_load")
            )
            _load.side_effect = generate_results()

            result11 = self.f._open(
                unittest.mock.sentinel.type_,
                level1,
            )

            result21 = self.f._open(
                unittest.mock.sentinel.type_,
                level2,
            )

            result31 = self.f._open(
                unittest.mock.sentinel.type_,
                level3,
            )

            result12 = self.f._open(
                unittest.mock.sentinel.type_,
                level1,
            )

            result22 = self.f._open(
                unittest.mock.sentinel.type_,
                level2,
            )

            result32 = self.f._open(
                unittest.mock.sentinel.type_,
                level3,
            )

        self.assertCountEqual(
            _load.mock_calls,
            [
                unittest.mock.call(unittest.mock.sentinel.type_, level1),
                unittest.mock.call(unittest.mock.sentinel.type_, level3),
            ]
        )

        self.assertEqual(result11, unittest.mock.sentinel.data1)
        self.assertEqual(result21, unittest.mock.sentinel.data1)
        self.assertEqual(result31, unittest.mock.sentinel.data2)

        self.assertEqual(result12, unittest.mock.sentinel.data1)
        self.assertEqual(result22, unittest.mock.sentinel.data1)
        self.assertEqual(result32, unittest.mock.sentinel.data2)

    def test_get_level_keys_returns_keys_of_data(self):
        storage = unittest.mock.Mock()

        with contextlib.ExitStack() as stack:
            _open = stack.enter_context(
                unittest.mock.patch.object(self.f, "_open")
            )

            _open.return_value = storage

            result = self.f.get_level_keys(
                unittest.mock.sentinel.type_,
                unittest.mock.sentinel.level_type,
            )

        _open.assert_called_once_with(
            unittest.mock.sentinel.type_,
            unittest.mock.sentinel.level_type,
        )

        storage.items.keys.assert_called_once_with()

        self.assertEqual(
            result,
            storage.items.keys(),
        )

    def test_get_all_returns_data_for_account(self):
        level = frontends.AccountLevel(
            unittest.mock.sentinel.account,
        )
        storage = unittest.mock.Mock()
        storage.items = unittest.mock.MagicMock()
        xso_type = unittest.mock.Mock(["TAG"])

        with contextlib.ExitStack() as stack:
            _open = stack.enter_context(
                unittest.mock.patch.object(self.f, "_open")
            )

            _open.return_value = storage

            result = self.f.get_all(
                unittest.mock.sentinel.type_,
                level,
                xso_type,
            )

        _open.assert_called_once_with(
            unittest.mock.sentinel.type_,
            level,
        )

        storage.items.__getitem__.assert_called_once_with(
            unittest.mock.sentinel.account,
        )

        storage.items.__getitem__().__getitem__.assert_called_once_with(
            xso_type.TAG,
        )

        self.assertEqual(
            result,
            storage.items[...][...]
        )

    def test_get_all_handles_KeyError_for_items(self):
        level = frontends.AccountLevel(
            unittest.mock.sentinel.account,
        )
        storage = unittest.mock.Mock()
        storage.items = unittest.mock.MagicMock()
        storage.items.__getitem__.side_effect = KeyError

        with contextlib.ExitStack() as stack:
            _open = stack.enter_context(
                unittest.mock.patch.object(self.f, "_open")
            )

            _open.return_value = storage

            result = self.f.get_all(
                unittest.mock.sentinel.type_,
                level,
                unittest.mock.sentinel.xso_type,
            )

        _open.assert_called_once_with(
            unittest.mock.sentinel.type_,
            level,
        )

        storage.items.__getitem__.assert_called_once_with(
            unittest.mock.sentinel.account,
        )

        self.assertSequenceEqual(
            result,
            [],
        )

        self.assertIsInstance(
            result,
            aioxmpp.xso.model.XSOList,
        )

    def test_get_all_handles_KeyError_for_data(self):
        level = frontends.AccountLevel(
            unittest.mock.sentinel.account,
        )
        xso_type = unittest.mock.Mock(["TAG"])
        storage = unittest.mock.Mock()
        storage.items = unittest.mock.MagicMock()
        storage.items.__getitem__.return_value.__getitem__.side_effect = KeyError

        with contextlib.ExitStack() as stack:
            _open = stack.enter_context(
                unittest.mock.patch.object(self.f, "_open")
            )

            _open.return_value = storage

            result = self.f.get_all(
                unittest.mock.sentinel.type_,
                level,
                xso_type,
            )

        _open.assert_called_once_with(
            unittest.mock.sentinel.type_,
            level,
        )

        storage.items.__getitem__.assert_called_once_with(
            unittest.mock.sentinel.account,
        )

        storage.items.__getitem__().__getitem__.assert_called_once_with(
            xso_type.TAG,
        )

        self.assertSequenceEqual(
            result,
            [],
        )

        self.assertIsInstance(
            result,
            aioxmpp.xso.model.XSOList,
        )

    def test_get_all_returns_data_for_peer(self):
        account = unittest.mock.Mock()
        level = frontends.PeerLevel(
            account,
            unittest.mock.sentinel.jid,
        )
        storage = unittest.mock.Mock()
        storage.items = unittest.mock.MagicMock()
        xso_type = unittest.mock.Mock(["TAG"])

        with contextlib.ExitStack() as stack:
            _open = stack.enter_context(
                unittest.mock.patch.object(self.f, "_open")
            )

            _open.return_value = storage

            result = self.f.get_all(
                unittest.mock.sentinel.type_,
                level,
                xso_type,
            )

        _open.assert_called_once_with(
            unittest.mock.sentinel.type_,
            level,
        )

        storage.items.__getitem__.assert_called_once_with(
            (
                account,
                unittest.mock.sentinel.jid,
            )
        )

        storage.items.__getitem__().__getitem__.assert_called_once_with(
            xso_type.TAG,
        )

        self.assertEqual(
            result,
            storage.items[...][...]
        )

    def test_get_uses_get_all(self):
        with contextlib.ExitStack() as stack:
            get_all = stack.enter_context(
                unittest.mock.patch.object(self.f, "get_all")
            )
            get_all.return_value = unittest.mock.MagicMock()

            result = self.f.get(
                unittest.mock.sentinel.type_,
                unittest.mock.sentinel.level,
                unittest.mock.sentinel.xso_type,
            )

        get_all.assert_called_once_with(
            unittest.mock.sentinel.type_,
            unittest.mock.sentinel.level,
            unittest.mock.sentinel.xso_type,
        )

        get_all().__getitem__.assert_called_once_with(0)

        self.assertEqual(
            result,
            get_all()[...],
        )

    def test_get_returns_None_on_IndexError(self):
        with contextlib.ExitStack() as stack:
            get_all = stack.enter_context(
                unittest.mock.patch.object(self.f, "get_all")
            )
            get_all.return_value = unittest.mock.MagicMock()
            get_all.return_value.__getitem__.side_effect = IndexError

            result = self.f.get(
                unittest.mock.sentinel.type_,
                unittest.mock.sentinel.level,
                unittest.mock.sentinel.xso_type,
            )

        get_all.assert_called_once_with(
            unittest.mock.sentinel.type_,
            unittest.mock.sentinel.level,
            unittest.mock.sentinel.xso_type,
        )

        get_all().__getitem__.assert_called_once_with(0)

        self.assertIsNone(result)

    def test_get_reraises_IndexError_from_get_all(self):
        with contextlib.ExitStack() as stack:
            get_all = stack.enter_context(
                unittest.mock.patch.object(self.f, "get_all")
            )
            get_all.side_effect = IndexError

            with self.assertRaises(IndexError):
                self.f.get(
                    unittest.mock.sentinel.type_,
                    unittest.mock.sentinel.level,
                    unittest.mock.sentinel.xso_type,
                )

    def test__put_into_single_xso_existing(self):
        items = unittest.mock.MagicMock()

        class TestXSO(aioxmpp.xso.XSO):
            TAG = ("test namespace", "test tag")

        xso = TestXSO()

        self.f._put_into(
            items,
            unittest.mock.sentinel.key,
            xso,
        )

        items.__getitem__.assert_called_once_with(unittest.mock.sentinel.key)

        items.__getitem__().__getitem__.assert_called_once_with(
            ("test namespace", "test tag"),
        )

        items.__getitem__().__getitem__().__setitem__.assert_called_once_with(
            slice(None),
            [xso],
        )

    def test__put_into_single_xso_key_missing(self):
        items = unittest.mock.MagicMock()
        items.__getitem__.side_effect = KeyError()

        class TestXSO(aioxmpp.xso.XSO):
            TAG = ("test namespace", "test tag")

        xso = TestXSO()

        with contextlib.ExitStack() as stack:
            XSOList = stack.enter_context(
                unittest.mock.patch("aioxmpp.xso.model.XSOList")
            )

            self.f._put_into(
                items,
                unittest.mock.sentinel.key,
                xso,
            )

        items.__getitem__.assert_called_once_with(unittest.mock.sentinel.key)

        XSOList.assert_called_once_with([xso])

        items.__setitem__.assert_called_once_with(
            unittest.mock.sentinel.key,
            {
                ("test namespace", "test tag"): XSOList(),
            }
        )

    def test__put_into_single_xso_type_missing(self):
        items = unittest.mock.MagicMock()
        items.__getitem__.return_value.__getitem__.side_effect = KeyError()

        xso = unittest.mock.Mock(spec=aioxmpp.xso.XSO)

        with contextlib.ExitStack() as stack:
            XSOList = stack.enter_context(
                unittest.mock.patch("aioxmpp.xso.model.XSOList")
            )

            self.f._put_into(
                items,
                unittest.mock.sentinel.key,
                xso,
            )

        items.__getitem__.assert_called_once_with(unittest.mock.sentinel.key)

        items.__getitem__().__getitem__.assert_called_once_with(
            type(xso),
        )

        XSOList.assert_called_once_with([xso])

        items.__getitem__().__setitem__.assert_called_once_with(
            type(xso),
            XSOList(),
        )

    def test__put_into_multiple_xsos_existing(self):
        items = unittest.mock.MagicMock()

        class TestXSO(aioxmpp.xso.XSO):
            TAG = ("test namespace", "test tag")

        xso1 = TestXSO()
        xso2 = TestXSO()

        self.f._put_into(
            items,
            unittest.mock.sentinel.key,
            [xso1, xso2],
        )

        items.__getitem__.assert_called_once_with(unittest.mock.sentinel.key)

        items.__getitem__().__getitem__.assert_called_once_with(
            ("test namespace", "test tag")
        )

        items.__getitem__().__getitem__().__setitem__.assert_called_once_with(
            slice(None),
            [xso1, xso2],
        )

    def test__put_into_single_xso_key_missing(self):
        items = unittest.mock.MagicMock()
        items.__getitem__.side_effect = KeyError()

        class TestXSO(aioxmpp.xso.XSO):
            TAG = ("test namespace", "test tag")

        xso1 = TestXSO()
        xso2 = TestXSO()

        with contextlib.ExitStack() as stack:
            XSOList = stack.enter_context(
                unittest.mock.patch("aioxmpp.xso.model.XSOList")
            )

            self.f._put_into(
                items,
                unittest.mock.sentinel.key,
                [xso1, xso2],
            )

        items.__getitem__.assert_called_once_with(unittest.mock.sentinel.key)

        XSOList.assert_called_once_with([xso1, xso2])

        items.__setitem__.assert_called_once_with(
            unittest.mock.sentinel.key,
            {
                ("test namespace", "test tag"): XSOList(),
            }
        )

    def test__put_into_single_xso_type_missing(self):
        items = unittest.mock.MagicMock()
        items.__getitem__.return_value.__getitem__.side_effect = KeyError()

        class TestXSO(aioxmpp.xso.XSO):
            TAG = ("test namespace", "test tag")

        xso1 = TestXSO()
        xso2 = TestXSO()

        with contextlib.ExitStack() as stack:
            XSOList = stack.enter_context(
                unittest.mock.patch("aioxmpp.xso.model.XSOList")
            )

            self.f._put_into(
                items,
                unittest.mock.sentinel.key,
                [xso1, xso2],
            )

        items.__getitem__.assert_called_once_with(unittest.mock.sentinel.key)

        items.__getitem__().__getitem__.assert_called_once_with(
            ("test namespace", "test tag"),
        )

        XSOList.assert_called_once_with([xso1, xso2])

        items.__getitem__().__setitem__.assert_called_once_with(
            ("test namespace", "test tag"),
            XSOList(),
        )

    def test_put_to_account(self):
        level = frontends.AccountLevel(
            unittest.mock.sentinel.account,
        )

        storage = unittest.mock.Mock()
        storage.items = unittest.mock.MagicMock()

        with contextlib.ExitStack() as stack:
            _open = stack.enter_context(
                unittest.mock.patch.object(self.f, "_open")
            )
            _open.return_value = storage

            _put_into = stack.enter_context(
                unittest.mock.patch.object(self.f, "_put_into")
            )

            XSOList = stack.enter_context(
                unittest.mock.patch("aioxmpp.xso.model.XSOList")
            )

            self.f.put(
                unittest.mock.sentinel.type_,
                level,
                unittest.mock.sentinel.xso,
            )

        _open.assert_called_once_with(
            unittest.mock.sentinel.type_,
            level,
        )

        _put_into.assert_called_once_with(
            storage.items,
            unittest.mock.sentinel.account,
            unittest.mock.sentinel.xso,
        )

    def test_put_to_peer(self):
        account = unittest.mock.Mock()
        level = frontends.PeerLevel(
            account,
            unittest.mock.sentinel.peer,
        )
        storage = unittest.mock.Mock()
        storage.items = unittest.mock.MagicMock()

        with contextlib.ExitStack() as stack:
            _open = stack.enter_context(
                unittest.mock.patch.object(self.f, "_open")
            )
            _open.return_value = storage

            _put_into = stack.enter_context(
                unittest.mock.patch.object(self.f, "_put_into")
            )

            XSOList = stack.enter_context(
                unittest.mock.patch("aioxmpp.xso.model.XSOList")
            )

            self.f.put(
                unittest.mock.sentinel.type_,
                level,
                unittest.mock.sentinel.xso,
            )

        _open.assert_called_once_with(
            unittest.mock.sentinel.type_,
            level,
        )

        _put_into.assert_called_once_with(
            storage.items,
            (account, unittest.mock.sentinel.peer),
            unittest.mock.sentinel.xso,
        )

    def test__save(self):
        with contextlib.ExitStack() as stack:
            _get_path = stack.enter_context(
                unittest.mock.patch.object(self.f, "_get_path")
            )

            write_single_xso = stack.enter_context(
                unittest.mock.patch("aioxmpp.xml.write_single_xso")
            )

            mkdir_exist_ok = stack.enter_context(
                unittest.mock.patch("jclib.utils.mkdir_exist_ok")
            )

            safe_writer = stack.enter_context(
                unittest.mock.patch("jclib.utils.safe_writer")
            )
            safe_writer.return_value = unittest.mock.MagicMock([
                "__enter__",
                "__exit__",
            ])

            self.f._save(
                unittest.mock.sentinel.data,
                unittest.mock.sentinel.type_,
                unittest.mock.sentinel.level_type,
                unittest.mock.sentinel.identities,
            )

        _get_path.assert_called_once_with(
            unittest.mock.sentinel.type_,
            unittest.mock.sentinel.level_type,
            unittest.mock.sentinel.identities,
        )

        mkdir_exist_ok.assert_called_once_with(
            _get_path().parent,
        )

        safe_writer.assert_called_once_with(
            _get_path()
        )

        safe_writer().__enter__.assert_called_once_with()

        write_single_xso.assert_called_once_with(
            unittest.mock.sentinel.data,
            safe_writer().__enter__(),
        )

    def test__writeback_uses__save(self):
        level = frontends.PeerLevel(
            unittest.mock.sentinel.identity,
            unittest.mock.sentinel.peer,
        )

        with contextlib.ExitStack() as stack:
            _save = stack.enter_context(
                unittest.mock.patch.object(self.f, "_save")
            )

            _load = stack.enter_context(
                unittest.mock.patch.object(self.f, "_load")
            )

            data = self.f._open(
                unittest.mock.sentinel.type_,
                level,
            )

            _save.assert_not_called()
            _open = stack.enter_context(
                unittest.mock.patch.object(self.f, "_open")
            )

            self.f._writeback(
                unittest.mock.sentinel.type_,
                (
                    level.level,
                    level.account,
                )
            )

        _save.assert_called_once_with(
            data,
            unittest.mock.sentinel.type_,
            level.level,
            level.account,
        )

        _open.assert_not_called()

    def test__writeback_is_noop_if_not_open(self):
        level = unittest.mock.Mock()
        level.level = frontends.StorageLevel.ACCOUNT

        with contextlib.ExitStack() as stack:
            _save = stack.enter_context(
                unittest.mock.patch.object(self.f, "_save")
            )

            _load = stack.enter_context(
                unittest.mock.patch.object(self.f, "_load")
            )

            data = self.f._open(
                unittest.mock.sentinel.type_,
                level,
            )

            _save.assert_not_called()
            _open = stack.enter_context(
                unittest.mock.patch.object(self.f, "_open")
            )

            self.f._writeback(
                unittest.mock.sentinel.other_type,
                level,
            )

        _save.assert_not_called()
        _open.assert_not_called()

    def test_flush_all_calls_writeback_for_open_stuff(self):
        level1 = frontends.AccountLevel(
            unittest.mock.sentinel.account1,
        )

        level3 = frontends.PeerLevel(
            unittest.mock.sentinel.account1,
            unittest.mock.sentinel.peer1,
        )

        level4 = frontends.PeerLevel(
            unittest.mock.sentinel.account1,
            unittest.mock.sentinel.peer2,
        )

        with contextlib.ExitStack() as stack:
            _writeback = stack.enter_context(
                unittest.mock.patch.object(self.f, "_writeback")
            )

            _load = stack.enter_context(
                unittest.mock.patch.object(self.f, "_load"),
            )

            self.f._open(
                unittest.mock.sentinel.type1,
                level3,
            )

            self.f._open(
                unittest.mock.sentinel.type1,
                level4,
            )

            self.f._open(
                unittest.mock.sentinel.type2,
                level1,
            )

            self.f.flush_all()


        self.assertCountEqual(
            _writeback.mock_calls,
            [
                unittest.mock.call(
                    unittest.mock.sentinel.type1,
                    (
                        level3.level,
                        level3.account,
                    )
                ),
                unittest.mock.call(
                    unittest.mock.sentinel.type2,
                    (
                        level1.level,
                    )
                ),
            ]
        )

    def test_register_registers_XSO_child_for_account(self):
        class Foo(aioxmpp.xso.XSO):
            TAG = "urn:test", "account"

        frontends.XMLFrontend.register(
            frontends.StorageLevel.ACCOUNT,
            Foo,
        )

        self.assertIn(
            Foo.TAG,
            jclib.storage.account_model.XMLStorageItem.CHILD_MAP,
        )

        self.assertIn(
            Foo,
            jclib.storage.account_model.XMLStorageItem.data._classes,
        )

    def test_register_registers_XSO_child_for_peer(self):
        class Foo(aioxmpp.xso.XSO):
            TAG = "urn:test", "peer"

        frontends.XMLFrontend.register(
            frontends.StorageLevel.PEER,
            Foo,
        )

        self.assertIn(
            Foo.TAG,
            jclib.storage.peer_model.XMLStorageItem.CHILD_MAP,
        )

        self.assertIn(
            Foo,
            jclib.storage.peer_model.XMLStorageItem.data._classes,
        )

    def test_put_get_cycle_account(self):
        with MockBackend() as backend:
            self.f = frontends.XMLFrontend(backend)

            j1 = aioxmpp.JID.fromstr("romeo@montague.lit")
            j2 = aioxmpp.JID.fromstr("juliet@capulet.lit")

            d1s = []
            for i in range(3):
                d1 = Data1()
                d1.foo = "test foo data {}".format(i)
                d1.bar = "test bar data {}".format(i)
                d1s.append(d1)

            self.f.put(
                jclib.storage.common.StorageType.CACHE,
                frontends.AccountLevel(j1),
                [d1s[0], d1s[1]]
            )

            self.f.put(
                jclib.storage.common.StorageType.CACHE,
                frontends.AccountLevel(j2),
                [d1s[2]],
            )

            self.f.flush_all()

            self.f = frontends.XMLFrontend(backend)

            for i, d1 in enumerate(self.f.get_all(
                    jclib.storage.common.StorageType.CACHE,
                    frontends.AccountLevel(j1), Data1)):
                self.assertEqual(
                    d1.foo,
                    d1s[i].foo,
                    i,
                )
                self.assertEqual(
                    d1.bar,
                    d1s[i].bar,
                    i,
                )

            for i, d1 in enumerate(self.f.get_all(
                    jclib.storage.common.StorageType.CACHE,
                    frontends.AccountLevel(j2), Data1), 2):
                self.assertEqual(
                    d1.foo,
                    d1s[i].foo,
                    i,
                )
                self.assertEqual(
                    d1.bar,
                    d1s[i].bar,
                    i,
                )

    def test_put_get_cycle_peer(self):
        with MockBackend() as backend:
            self.f = frontends.XMLFrontend(backend)

            i1 = aioxmpp.JID.fromstr("account1@server.example")
            i2 = aioxmpp.JID.fromstr("account2@server.example")
            j1 = aioxmpp.JID.fromstr("romeo@montague.lit")
            j2 = aioxmpp.JID.fromstr("juliet@capulet.lit")

            d1s = []
            for i in range(3):
                d1 = Data1()
                d1.foo = "test foo data {}".format(i)
                d1.bar = "test bar data {}".format(i)
                d1s.append(d1)

            self.f.put(
                jclib.storage.common.StorageType.CACHE,
                frontends.PeerLevel(i1, j1),
                [d1s[0], d1s[1]]
            )

            self.f.put(
                jclib.storage.common.StorageType.CACHE,
                frontends.PeerLevel(i2, j2),
                [d1s[2]],
            )

            self.f.flush_all()

            self.f = frontends.XMLFrontend(backend)

            for i, d1 in enumerate(self.f.get_all(
                    jclib.storage.common.StorageType.CACHE,
                    frontends.PeerLevel(i1, j1), Data1)):
                self.assertEqual(
                    d1.foo,
                    d1s[i].foo,
                    i,
                )
                self.assertEqual(
                    d1.bar,
                    d1s[i].bar,
                    i,
                )

            for i, d1 in enumerate(self.f.get_all(
                    jclib.storage.common.StorageType.CACHE,
                    frontends.PeerLevel(i2, j2), Data1), 2):
                self.assertEqual(
                    d1.foo,
                    d1s[i].foo,
                    i,
                )
                self.assertEqual(
                    d1.bar,
                    d1s[i].bar,
                    i,
                )
