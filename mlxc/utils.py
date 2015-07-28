import os.path
import types
import xdg.BaseDirectory

import aioxmpp.errors

from aioxmpp.utils import namespaces


mlxc_namespaces = types.SimpleNamespace()
mlxc_namespaces.roster = "https://xmlns.zombofant.net/mlxc/core/roster/1.0"
mlxc_namespaces.account = "https://xmlns.zombofant.net/mlxc/core/account/1.0"


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


def xdgconfigopen(*args, mode="rb", **kwargs):
    """
    Open a configuration file. The last of the positional arguments is used as
    a file name, the others are taken as resource (see
    :mod:`xdg.BaseDirectory`).

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
        f = mlxc.utils.xdgconfigopen("zombofant.net", "mlxc", "fnord.xml")

    For writing, we would pass a different `mode`.
    """

    *resource, name = args
    return xdgopen_generic(
        resource,
        name,
        mode,
        xdg.BaseDirectory.load_config_paths,
        xdg.BaseDirectory.save_config_path,
        **kwargs)


def xdgdataopen(*args, mode="rb", **kwargs):
    """
    Open a data file. The last of the positional arguments is used as a file
    name, the others are taken as resource (see :mod:`xdg.BaseDirectory`).

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
        f = mlxc.utils.xdgdataopen("zombofant.net", "mlxc", "foo.xml")

    For writing, we would pass a different `mode`.
    """

    *resource, name = args
    return xdgopen_generic(
        resource,
        name,
        mode,
        xdg.BaseDirectory.load_data_paths,
        xdg.BaseDirectory.save_data_path,
        **kwargs)
