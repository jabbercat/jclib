import asyncio
import functools
import logging
import signal

from . import roster

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
    roster_window = roster.Roster()
    roster_window.show()
    fut = asyncio.Future()
    yield from fut

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
