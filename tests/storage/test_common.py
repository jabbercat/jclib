import contextlib
import unittest
import unittest.mock

import jclib.storage.common as common


class Testsession_scope(unittest.TestCase):
    def setUp(self):
        self.session = unittest.mock.Mock()
        self.sm = unittest.mock.Mock()
        self.sm.return_value = self.session
        self.ss = common.session_scope(self.sm)

    def test_is_context_manager(self):
        self.assertTrue(hasattr(self.ss, "__enter__"))
        self.assertTrue(hasattr(self.ss, "__exit__"))

    def test_enter_creates_and_returns_session(self):
        result = self.ss.__enter__()
        self.sm.assert_called_once_with()
        self.assertEqual(result, self.session)

    def test_clean_exit_commits_and_closes_session(self):
        self.ss.__enter__()
        self.session.commit.assert_not_called()
        self.session.rollback.assert_not_called()
        self.session.close.assert_not_called()
        self.ss.__exit__(None, None, None)
        self.session.commit.assert_called_once_with()
        self.session.rollback.assert_not_called()
        self.session.close.assert_called_once_with()

    def test_clean_exit_commits_and_closes_session(self):
        class FooException(Exception):
            pass

        with contextlib.ExitStack() as stack:
            stack.enter_context(self.assertRaises(FooException))
            stack.enter_context(self.ss)

            self.session.commit.assert_not_called()
            self.session.rollback.assert_not_called()
            self.session.close.assert_not_called()

            raise FooException()

        self.session.commit.assert_not_called()
        self.session.rollback.assert_called_once_with()
        self.session.close.assert_called_once_with()
