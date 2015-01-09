import asyncio
import functools
import logging
import types

import lxml.etree as etree

__all__ = [
    "logged_async",
    "etree",
    "mlxc_namespaces",
    "booltostr",
    "strtobool"
]

logger = logging.getLogger(__name__)

def _logged_task_done(task):
    try:
        value = task.result()
    except asyncio.CancelledError:
        logger.debug("task cancelled: %s", task, exc_info=True)
    except:
        logger.exception("task failed: %s", task)
    else:
        if value is not None:
            logger.info("task returned (unexpectedly?) a value: %r",
                        value)


def logged_async(coro, loop=None):
    task = asyncio.async(coro, loop=loop)
    task.add_done_callback(_logged_task_done)
    return task

def strtobool(s):
    return s.lower().strip() in ["true", "1", "yes"]

def booltostr(b):
    return str(b)

def presencetostr(p):
    if p.available:
        if not p.show:
            # TRANSLATEME
            return "Available"
        # TRANSLATEME
        return "Available ({})".format(p.show)
    else:
        return "Not available"

@asyncio.coroutine
def save_etree(dest, tree, *, loop=None, **kwargs):
    loop = loop or asyncio.get_event_loop()
    yield from loop.run_in_executor(
        None,
        functools.partial(tree.write, dest, **kwargs)
    )

@asyncio.coroutine
def load_etree(source, *, loop=None, custom_parser=None, **kwargs):
    if custom_parser is True or (custom_parser is None and kwargs):
        custom_parser = etree.XMLParser(**kwargs)
    else:
        custom_parser = None
    loop = loop or asyncio.get_event_loop()
    return (yield from loop.run_in_executor(
        None,
        functools.partial(etree.parse, source, parser=custom_parser)
    ))

mlxc_namespaces = types.SimpleNamespace()
mlxc_namespaces.roster = "https://xmlns.zombofant.net/mlxc/roster/1.0"
mlxc_namespaces.accounts = "https://xmlns.zombofant.net/mlxc/account/1.0"
