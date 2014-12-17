import asyncio
import logging
import types

import lxml.etree as etree

__all__ = [
    "logged_async",
    "etree",
    "mlxc_namespaces",
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


mlxc_namespaces = types.SimpleNamespace()
mlxc_namespaces.roster = "https://xmlns.zombofant.net/mlxc/roster-data/1.0"
mlxc_namespaces.accounts = "https://xmlns.zombofant.net/mlxc/account-data/1.0"
