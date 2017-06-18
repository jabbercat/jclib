import asyncio
import contextlib
import sys
import unittest
import unittest.mock

from aioxmpp.testutils import (
    make_listener,
    run_coroutine,
)

from aioxmpp.e2etest import blocking

import mlxc.tasks as tasks


class TestAnnotatedTask(unittest.TestCase):
    def setUp(self):
        self.original_task = unittest.mock.Mock(spec=asyncio.Task)
        self.at = tasks.AnnotatedTask(self.original_task)

        self.listener = make_listener(self.at)

    def test_setting_text_emits_on_changed(self):
        self.assertIsNone(self.at.text)
        self.at.text = "foo"
        self.assertEqual(self.at.text, "foo")

        self.listener.on_changed.assert_called_once_with()

    def test_setting_progress_ratio_emits_on_changed(self):
        self.assertEqual(self.at.progress_ratio, 0)
        self.at.progress_ratio = 0.8
        self.assertEqual(self.at.progress_ratio, 0.8)

        self.listener.on_changed.assert_called_once_with()

    def test_asyncio_task(self):
        self.assertEqual(self.at.asyncio_task, self.original_task)

        with self.assertRaisesRegex(AttributeError, "can't set attribute"):
            self.at.asyncio_task = self.at.asyncio_task


class TestTaskManager(unittest.TestCase):
    def setUp(self):
        self.tm = tasks.TaskManager()
        self.tasks_to_kill = []

        self.listener = make_listener(self.tm)

    @asyncio.coroutine
    @staticmethod
    def some_job():
        while True:
            yield from asyncio.sleep(1)

    @blocking
    def tearDown(self):
        for task in self.tasks_to_kill:
            if task.done():
                continue

            task.cancel()
            try:
                yield from task
            except asyncio.CancelledError:
                pass
        del self.tm

    def _ensure_future(self, coro):
        task = asyncio.ensure_future(coro)
        task.add_done_callback(self._remove_task)
        self.tasks_to_kill.append(task)
        return task

    def _remove_task(self, task):
        self.tasks_to_kill.remove(task)

    def test_add_adds_task_and_emits_signal(self):
        task = self._ensure_future(self.some_job())

        with contextlib.ExitStack() as stack:
            AnnotatedTask = stack.enter_context(
                unittest.mock.patch("mlxc.tasks.AnnotatedTask")
            )

            result = self.tm.add(task)

        AnnotatedTask.assert_called_once_with(task)

        self.listener.on_task_added.assert_called_once_with(
            AnnotatedTask()
        )

        self.assertCountEqual(
            self.tm.tasks,
            [AnnotatedTask()]
        )

        self.assertEqual(
            result,
            AnnotatedTask(),
        )

        task.cancel()

    def test_on_change_emits_on_task_changed(self):
        task = self._ensure_future(self.some_job())

        result = self.tm.add(task)

        self.listener.on_task_changed.assert_not_called()

        result.on_changed()

        self.listener.on_task_changed.assert_called_once_with(
            result,
        )

        task.cancel()

    def test_task_is_already_in_list_when_on_task_added_emits(self):
        result = asyncio.Future()

        def on_task_added(t):
            try:
                self.assertIn(
                    t, self.tm.tasks
                )
            except:
                result.set_exception(sys.exc_info[1])
            else:
                result.set_result(None)
            # disconnect
            return True

        task = self._ensure_future(self.some_job())

        self.tm.on_task_added.connect(on_task_added)

        with contextlib.ExitStack() as stack:
            stack.enter_context(
                unittest.mock.patch("mlxc.tasks.AnnotatedTask")
            )

            self.tm.add(task)

        run_coroutine(result)

        task.cancel()

    def test_start_uses_ensure_future_and_add_and_returns_task(self):
        with contextlib.ExitStack() as stack:
            add = stack.enter_context(
                unittest.mock.patch.object(self.tm, "add")
            )

            ensure_future = stack.enter_context(
                unittest.mock.patch("asyncio.ensure_future")
            )

            coro = self.some_job()
            result = self.tm.start(coro)

        ensure_future.assert_called_once_with(coro)

        add.assert_called_once_with(ensure_future())

        self.assertEqual(result, add())

    def test_get_annotation(self):
        task = self._ensure_future(self.some_job())

        annotation = self.tm.add(task)

        self.assertEqual(
            self.tm.get_annotation(task),
            annotation,
        )

    def test_get_annotation_raises_KeyError_for_unannotated(self):
        task = self._ensure_future(self.some_job())

        with self.assertRaises(KeyError):
            self.tm.get_annotation(task)

    def test_current_uses_get_annotated(self):
        with contextlib.ExitStack() as stack:
            current_task = stack.enter_context(unittest.mock.patch.object(
                asyncio.Task,
                "current_task",
            ))

            get_annotation = stack.enter_context(unittest.mock.patch.object(
                self.tm,
                "get_annotation",
            ))

            result = self.tm.current()

        current_task.assert_called_once_with()
        get_annotation.assert_called_once_with(current_task())

        self.assertEqual(
            result,
            get_annotation(),
        )

    def test_current_returns_None_if_no_annotation(self):
        with contextlib.ExitStack() as stack:
            current_task = stack.enter_context(unittest.mock.patch.object(
                asyncio.Task,
                "current_task",
            ))

            get_annotation = stack.enter_context(unittest.mock.patch.object(
                self.tm,
                "get_annotation",
            ))
            get_annotation.side_effect = KeyError

            result = self.tm.current()

        current_task.assert_called_once_with()
        get_annotation.assert_called_once_with(current_task())

        self.assertIsNone(
            result,
        )

    def test_update_text_uses_current(self):
        annotated_task = unittest.mock.Mock()

        with contextlib.ExitStack() as stack:
            current = stack.enter_context(unittest.mock.patch.object(
                self.tm,
                "current",
            ))
            current.return_value = annotated_task

            self.tm.update_text(unittest.mock.sentinel.text)

        current.assert_called_once_with()

        self.assertEqual(
            annotated_task.text,
            unittest.mock.sentinel.text,
        )

    def test_update_text_raises_if_current_returs_None(self):
        with contextlib.ExitStack() as stack:
            current = stack.enter_context(unittest.mock.patch.object(
                self.tm,
                "current",
            ))
            current.return_value = None

            with self.assertRaisesRegex(
                    RuntimeError,
                    r"must be called from within an AnnotatedTask coroutine"):
                self.tm.update_text(unittest.mock.sentinel.text)

    def test_update_progress_uses_current(self):
        annotated_task = unittest.mock.Mock()

        with contextlib.ExitStack() as stack:
            current = stack.enter_context(unittest.mock.patch.object(
                self.tm,
                "current",
            ))
            current.return_value = annotated_task

            self.tm.update_progress(unittest.mock.sentinel.progress)

        current.assert_called_once_with()

        self.assertEqual(
            annotated_task.progress_ratio,
            unittest.mock.sentinel.progress,
        )

    def test_update_progress_raises_if_current_returs_None(self):
        with contextlib.ExitStack() as stack:
            current = stack.enter_context(unittest.mock.patch.object(
                self.tm,
                "current",
            ))
            current.return_value = None

            with self.assertRaisesRegex(
                    RuntimeError,
                    r"must be called from within an AnnotatedTask coroutine"):
                self.tm.update_progress(unittest.mock.sentinel.progress)

    def test_tasks_get_removed_when_done(self):
        task = self._ensure_future(self.some_job())

        result = self.tm.add(task)

        task.cancel()

        with self.assertRaises(asyncio.CancelledError):
            run_coroutine(task)
        # ensure that scheduled callbacks run
        run_coroutine(asyncio.sleep(0))

        self.assertNotIn(result, self.tm.tasks)

        with self.assertRaises(KeyError):
            self.tm.get_annotation(task)

    def test_global_instance(self):
        self.assertIsInstance(
            tasks.manager,
            tasks.TaskManager,
        )


class TestIntegration(unittest.TestCase):
    def setUp(self):
        self.tm = tasks.TaskManager()
        self.listener = make_listener(self.tm)

    @blocking
    def tearDown(self):
        for task in list(self.tm.tasks):
            task = task.asyncio_task
            if task.done():
                continue
            task.cancel()
            try:
                yield from task
            except asyncio.CancelledError:
                pass
        del self.tm

    def test_current_works_recursively(self):
        start_signal = asyncio.Future()
        done_signal = asyncio.Future()

        @asyncio.coroutine
        def check_current():
            nonlocal annotated
            self.assertEqual(
                self.tm.current(),
                annotated,
            )

        @asyncio.coroutine
        def some_job():
            yield from start_signal
            try:
                yield from check_current()
            except:
                done_signal.set_exception(sys.exc_info[1])
            else:
                done_signal.set_result(None)

        annotated = self.tm.start(some_job())
        start_signal.set_result(None)
        run_coroutine(done_signal)

    def test_manage_annotations_using_update_methods(self):
        start_signal = asyncio.Future()
        done_signal = asyncio.Future()

        @asyncio.coroutine
        def some_job():
            yield from start_signal
            self.tm.update_text("I am a job!")
            self.tm.update_progress(0.5)
            done_signal.set_result(None)
            while True:
                yield from asyncio.sleep(1)

        annotated = self.tm.start(some_job())

        listener = make_listener(annotated)

        listener.on_changed.assert_not_called()

        start_signal.set_result(None)
        run_coroutine(done_signal)

        self.assertCountEqual(
            listener.on_changed.mock_calls,
            [
                unittest.mock.call(),
                unittest.mock.call(),
            ]
        )
