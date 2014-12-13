import asyncio

import functools

from . import Qt

try:
    from quamash import inline_async
except ImportError:
    def inline_task_done(qloop, task):
        qloop.quit()

    def inline_async(coro):
        qloop = Qt.QEventLoop()
        task = asyncio.async(coro)
        task.add_done_callback(functools.partial(inline_task_done, qloop))
        qloop.exec()
        return task.result()


def block_widget_for_coro(widget, coro):
    prev_cursor = widget.cursor()
    widget.setEnabled(False)
    widget.setCursor(Qt.Qt.WaitCursor)
    try:
        return inline_async(coro)
    finally:
        widget.setCursor(prev_cursor)
        widget.setEnabled(True)
