import asyncio
import functools
import logging
import signal

__all__ = [
    "run_async_user_task",
    "spawn_main",
]

logger = logging.getLogger(__name__)

def handle_sigintterm(loop):
    print()
    print("SIGINT / SIGTERM received")
    # FIXME: clean shutdown please
    loop.stop()

@asyncio.coroutine
def main(loop):
    loop.add_signal_handler(
        signal.SIGINT,
        functools.partial(handle_sigintterm, loop))
    loop.add_signal_handler(
        signal.SIGTERM,
        functools.partial(handle_sigintterm, loop))
    from . import roster
    roster_window = roster.Roster()
    roster_window.show()
    fut = asyncio.Future()
    # while True:
    #     yield from asyncio.sleep(1)
    #     print("tick")
    #     yield from asyncio.sleep(1)
    #     print("tock")
    yield from fut

def async_user_task_done(task):
    try:
        task.result()
    except:
        logger.exception("user task failed:")

def main_done(loop, task):
    try:
        task.result()
    except:
        logger.exception("main task failed:")
        loop.stop()

def spawn_main(loop):
    task = asyncio.async(main(loop),
                         loop=loop)
    task.add_done_callback(
        functools.partial(main_done, loop)
    )

def run_async_user_task(coro):
    task = asyncio.async(coro)
    task.add_done_callback(async_user_task_done)
