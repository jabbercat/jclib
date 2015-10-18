import asyncio
import functools
import logging
import os.path
import types
import xml.sax.handler

import xdg.BaseDirectory

import aioxmpp.errors
import aioxmpp.xml
import aioxmpp.xso

from aioxmpp.utils import namespaces


mlxc_namespaces = types.SimpleNamespace()
mlxc_namespaces.roster = "https://xmlns.zombofant.net/mlxc/core/roster/1.0"
mlxc_namespaces.account = "https://xmlns.zombofant.net/mlxc/core/account/1.0"


logger = logging.getLogger(__name__)


def multiopen(paths, name, mode, *args, **kwargs):
    """
    Attempt to open a file called `name`, using multiple base paths given as
    iterable `paths`.

    `mode` is passed to :func:`open`, as well as the other `args` and `kwargs`.

    Return the first file which gets opened successfully. If no file can be
    opened, a :class:`aioxmpp.errors.MultiOSError` is raised with all the
    exceptions which were raised by the individial :func:`open` calls
    attached.
    """
    excs = []
    for path in paths:
        try:
            return open(os.path.join(path, name), mode, *args, **kwargs)
        except OSError as exc:
            excs.append(exc)
    raise aioxmpp.errors.MultiOSError("multiopen failed", excs)


def xdgopen_generic(resource, name, mode, load_paths, save_path, **kwargs):
    """
    This generic open function is used for opening :mod:`xdg.BaseDirectory`
    related files.

    If the `mode` is a read-only mode, the paths obtained by calling
    `load_paths` are passed in reverse order to :func:`multiopen` (along with
    `name`, `mode` and the `kwargs`).

    If the `mode` is not a read-only mode, the path obtained by calling
    `save_path` is combined with `name` using :func:`os.path.join` and passed
    to :func:`open` (along with `mode` and the `kwargs`).

    The result of the respective function is returned.
    """
    if not mode.startswith("r") or "+" in mode:
        return open(os.path.join(save_path(*resource), name),
                    mode=mode,
                    **kwargs)
    paths = list(load_paths(*resource))
    paths.reverse()
    return multiopen(paths, name, mode=mode, **kwargs)


def xdgconfigopen(resource, name, mode="rb", **kwargs):
    """
    Open a configuration file. The `name` is the file name, the `resource` (see
    :func:`xdg.BaseDirectory.load_config_paths`) defines the XDG resource.

    This function calls :func:`xdgopen_generic` and returns its result. The
    :func:`xdg.BaseDirectory.load_config_paths` and
    :func:`xdg.BaseDirectory.save_config_path` functions are used as values for
    the `load_paths` and `save_path` arguments, respectively, to
    :func:`xdgopen_generic`. The `mode` and the `kwargs` are passed along, as
    well as the resource and the file name (as extracted from the positional
    arguments).

    To open the first matching config file ``fnord.xml`` for reading with a
    resource of ``zombofant.net/mlxc``, one would call::

        import mlxc.utils
        f = mlxc.utils.xdgconfigopen(("zombofant.net", "mlxc"), "fnord.xml")

    For writing, we would pass a different `mode`.
    """

    return xdgopen_generic(
        resource,
        name,
        mode,
        xdg.BaseDirectory.load_config_paths,
        xdg.BaseDirectory.save_config_path,
        **kwargs)


def xdgdataopen(resource, name, mode="rb", **kwargs):
    """
    Open a data file. The `name` is the file name, the `resource` (see
    :func:`xdg.BaseDirectory.load_data_paths`) defines the XDG resource.

    This function calls :func:`xdgopen_generic` and returns its result. The
    :func:`xdg.BaseDirectory.load_data_paths` and
    :func:`xdg.BaseDirectory.save_data_path` functions are used as values for
    the `load_paths` and `save_path` arguments, respectively, to
    :func:`xdgopen_generic`. The `mode` and the `kwargs` are passed along, as
    well as the resource and the file name (as extracted from the positional
    arguments).

    To open the first matching data file ``foo.xml`` for reading with a
    resource of ``zombofant.net/mlxc``, one would call::

        import mlxc.utils
        f = mlxc.utils.xdgdataopen(("zombofant.net", "mlxc"), "foo.xml")

    For writing, we would pass a different `mode`.
    """

    return xdgopen_generic(
        resource,
        name,
        mode,
        xdg.BaseDirectory.load_data_paths,
        xdg.BaseDirectory.save_data_path,
        **kwargs)


def write_xso(dest, xso):
    """
    Write a single XSO `xso` to a binary file-like output `dest`. By default,
    it adds whitespace before and after the top level element to make the
    document at least a bit more readable.
    """
    generator = aioxmpp.xml.XMPPXMLGenerator(
        out=dest,
        short_empty_elements=True)

    generator.startDocument()
    generator.characters("\n")
    xso.unparse_to_sax(generator)
    generator.characters("\n")
    generator.endDocument()


def read_xso(src, xsomap):
    """
    Read a single XSO from a binary file-like input `src` containing an XML
    document.

    `xsomap` must be a mapping which maps :class:`aioxmpp.xso.XSO` subclasses
    to callables. These will be registered at a newly created
    :class:`aioxmpp.xso.XSOParser` instance which will be used to parse the
    document in `src`.

    The `xsomap` is thus used to determine the class parsing the root element
    of the XML document. This can be used to support multiple versions.
    """

    xso_parser = aioxmpp.xso.XSOParser()

    for class_, cb in xsomap.items():
        xso_parser.add_class(class_, cb)

    driver = aioxmpp.xso.SAXDriver(xso_parser)

    parser = xml.sax.make_parser()
    parser.setFeature(
        xml.sax.handler.feature_namespaces,
        True)
    parser.setFeature(
        xml.sax.handler.feature_external_ges,
        False)
    parser.setContentHandler(driver)

    parser.parse(src)


def _logged_task_done(task, name):
    try:
        value = task.result()
    except asyncio.CancelledError:
        logger.debug("task %s cancelled", name)
    except Exception:
        logger.exception("task %s failed", name)
    else:
        logger.info("task %s returned a value: %r",
                    name, task.result())


def logged_async(coro, *, loop=None, name=None):
    """
    This is a wrapper around :func:`asyncio.async` which automatically installs
    a callback on the task created using that function. `coro` and `loop` are
    passed to :func:`asyncio.async` and the result is returned.

    The callback will log a message after the task finishes:

    * if the task got cancelled, it logs a debug level message
    * if the task returned successfully with a value, it logs an info level
      message including the :func:`repr` of the value which was returned by the
      task
    * if the task exits with an exception other than
      :class:`asyncio.CancelledError`, an exception level message is logged,
      including the traceback

    In all cases, the `name` argument is included in the message. If `name` is
    :data:`None`, the :func:`str` representation of the return value of this
    function, that is, the task which was created, is used.
    """
    loop = asyncio.get_event_loop() if loop is None else loop
    task = asyncio.async(coro, loop=loop)
    task.add_done_callback(functools.partial(
        _logged_task_done,
        name=name or task))
    return task
