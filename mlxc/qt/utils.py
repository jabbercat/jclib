import asyncio
import functools
import logging
import random

from . import Qt

logger = logging.getLogger(__name__)

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

def asyncified_done(task):
    task.result()

def asyncify(fn):
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        task = asyncio.async(fn(*args, **kwargs))
        task.add_done_callback(asyncified_done)
    return wrapper

@asyncio.coroutine
def block_widget_for_coro(widget, coro):
    prev_cursor = widget.cursor()
    widget.setEnabled(False)
    widget.setCursor(Qt.Qt.WaitCursor)
    try:
        return (yield from coro)
    finally:
        widget.setCursor(prev_cursor)
        widget.setEnabled(True)

@asyncio.coroutine
def exec_async(dlg):
    future = asyncio.Future()
    def done(result):
        nonlocal future
        future.set_result(result)
    dlg.done.connect(done)
    dlg.show()
    yield from future

_system_random = random.SystemRandom()
_dragndrop_state = (None, None)

def start_drag(data):
    global _dragndrop_state
    if _dragndrop_state[0] is not None:
        logger.warning("dropping old dragndrop data: %r",
                       _dragndrop_state[1])

    key = _system_random.getrandbits(64).to_bytes(8, 'little')
    _dragndrop_state = key, data
    return key

def get_drag(key):
    if _dragndrop_state[0] != key:
        return None
    return _dragndrop_state[1]

def pop_drag(key):
    global _dragndrop_state
    if _dragndrop_state[0] != key:
        return None
    result = _dragndrop_state[1]
    _dragndrop_state = None, None
    return result

@asyncio.coroutine
def async_dialog(dlg):
    logger = logging.getLogger(__name__+".async_dialog")
    fut = asyncio.Future()
    dlg.finished.connect(fut.set_result)
    dlg.show()
    logger.debug("async_dialog: dialog /should/ be visible, waiting ...")
    yield from fut
    dlg.finished.disconnect(fut.set_result)
