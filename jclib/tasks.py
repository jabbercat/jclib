import asyncio
import functools
import logging
import typing

import aioxmpp.callbacks


logger = logging.getLogger(__name__)


class AnnotatedTask:
    """
    A :class:`asyncio.Task` wrapper with human-readable information.

    :param asyncio_task: The asyncio Task of this annotated task.
    :type asyncio_task: :class:`asyncio.Task`
    """

    on_changed = aioxmpp.callbacks.Signal()

    def __init__(self, asyncio_task: asyncio.Task):
        super().__init__()
        self.__asyncio_task = asyncio_task
        self.__text = None
        self.__progress_ratio = None

    def add_done_callback(self, fn):
        @functools.wraps(fn)
        def wrapper(task):
            fn(self)

        self.__asyncio_task.add_done_callback(wrapper)

    @property
    def text(self) -> str:
        return self.__text

    @text.setter
    def text(self, value: str):
        if self.__text == value:
            return
        self.__text = value
        self.on_changed()

    @property
    def progress_ratio(self) -> typing.Optional[float]:
        return self.__progress_ratio

    @progress_ratio.setter
    def progress_ratio(self, value: typing.Optional[float]):
        if value is not None:
            value = float(value)
        if self.__progress_ratio == value:
            return
        self.__progress_ratio = value
        self.on_changed()

    @property
    def asyncio_task(self) -> asyncio.Task:
        return self.__asyncio_task


class TaskManager:
    """
    Manage :class:`AnnotatedTask` instances.
    """

    on_task_added = aioxmpp.callbacks.Signal()
    on_task_changed = aioxmpp.callbacks.Signal()
    on_task_done = aioxmpp.callbacks.Signal()

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._tasks = {}

    def _task_done(self, task):
        try:
            task.result()
        except:
            logger.warning("task crashed:", exc_info=True)

        del self._tasks[task]

    def _on_task_changed(self, annotated):
        self.on_task_changed(annotated)

    def add(self, task: asyncio.Task) -> AnnotatedTask:
        annotated = AnnotatedTask(task)
        annotated.on_changed.connect(functools.partial(
            self._on_task_changed,
            annotated,
        ))
        self._tasks[task] = annotated
        task.add_done_callback(self._task_done)
        annotated.add_done_callback(self.on_task_done)
        self.on_task_added(annotated)
        return annotated

    def start(self, coroutine) -> AnnotatedTask:
        task = asyncio.ensure_future(coroutine)
        return self.add(task)

    @property
    def tasks(self):
        return self._tasks.values()

    def get_annotation(self, asyncio_task: asyncio.Task) -> AnnotatedTask:
        """
        Return the annotation for a task.

        :param asyncio_task: The native :mod:`asyncio` task to fetch the
            annotation for.
        :type asyncio_task: :class:`asyncio.Task`
        :raises KeyError: if the task is not annotated
        :return: The annotation for the task.
        :rtype: :class:`AnnotatedTask`

        Obtain the :class:`AnnotatedTask` for a given `asyncio_task`. If the
        task does not have an annotation managed by this :class:`TaskManager`,
        :class:`KeyError` is raised.
        """
        return self._tasks[asyncio_task]

    def current(self) -> typing.Optional[AnnotatedTask]:
        """
        Return the currently running :class:`AnnotatedTask`.

        :return: The :class:`AnnotatedTask` of the currently running
                 :class:`asyncio.Task` or :data:`None` if there is none.
        """
        asyncio_task = asyncio.Task.current_task()
        try:
            return self.get_annotation(asyncio_task)
        except KeyError:
            return None

    def _require_current(self) -> AnnotatedTask:
        task = self.current()
        if task is None:
            raise RuntimeError(
                "must be called from within an AnnotatedTask coroutine"
            )
        return task

    def update_text(self, text: str):
        """
        Update the human-readable text of what the task is currently doing.

        :param text: The new text to use or :data:`None`
        :type text: :class:`str` or :data:`None`
        :raises RuntimeError: if there is no :class:`AnnotatedTask` for the
                              currently running task

        This method operates on the current :class:`AnnotatedTask`. If
        the current :class:`asyncio.Task` does not have an associated
        :class:`AnnotatedTask`, :class:`RuntimeError` is raised.
        """
        self._require_current().text = text

    def update_progress(self, ratio: float):
        """
        Update the progress ratio of the task.

        :param ratio: The new progress ratio (from 0 to 1 incl.)
        :type ratio: :class:`numbers.Real`
        :raises RuntimeError: if there is no :class:`AnnotatedTask` for the
                              currently running task

        This method operates on the current :class:`AnnotatedTask`. If
        the current :class:`asyncio.Task` does not have an associated
        :class:`AnnotatedTask`, :class:`RuntimeError` is raised.
        """
        self._require_current().progress_ratio = ratio


manager = TaskManager()
