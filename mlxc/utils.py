import asyncio
import binascii
import contextlib
import functools
import hashlib
import logging
import math
import os.path
import pathlib
import struct
import tempfile
import types
import unicodedata
import xml.sax.handler

import xdg.BaseDirectory

import aioxmpp.errors
import aioxmpp.xml
import aioxmpp.xso

from aioxmpp.utils import namespaces


mlxc_namespaces = types.SimpleNamespace()
mlxc_namespaces.core = "dns:mlxc.zombofant.net"
mlxc_namespaces.roster = "https://xmlns.zombofant.net/mlxc/core/roster/1.0"
mlxc_namespaces.account = "https://xmlns.zombofant.net/mlxc/core/account/1.0"
mlxc_namespaces.presence = "https://xmlns.zombofant.net/mlxc/core/presence/1.0"
mlxc_namespaces.identity = "https://xmlns.zombofant.net/mlxc/core/identity/1.0"

mlxc_uid = "dns:mlxc.zombofant.net"
mlxc_avatars_uid = "avatars"

KEYRING_SERVICE_NAME = "net.zombofant.mlxc"
KEYRING_JID_FORMAT = "xmpp:{bare!s}"

logger = logging.getLogger(__name__)


def is_write_mode(mode):
    if not mode.startswith("r") or "+" in mode:
        return True
    return False


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
    if is_write_mode(mode):
        return open(os.path.join(save_path(*resource), name),
                    mode=mode,
                    **kwargs)
    paths = list(load_paths(*resource))
    paths.reverse()
    return multiopen(paths, name, mode=mode, **kwargs)


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
                    name, value)


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


@functools.lru_cache()
def normalise_text_for_hash(text):
    return " ".join(unicodedata.normalize("NFKC", text).split()).casefold()


def hsva_to_rgba(h, s, v, a):
    if s == 0:
        return v, v, v, a

    h = h % (math.pi*2)

    indexf = h / (math.pi*2 / 6)
    index = math.floor(indexf)
    fractional = indexf - index

    p = v * (1.0 - s)
    q = v * (1.0 - (s * fractional))
    t = v * (1.0 - (s * (1.0 - fractional)))

    return [
        (v, t, p),
        (q, v, p),
        (p, v, t),
        (p, q, v),
        (t, p, v),
        (v, p, q)
    ][index] + (a, )


def rgba_to_hsva(r, g, b, a):
    deg_60 = math.pi / 3

    Cmin = min(r, g, b)
    Cmax = max(r, g, b)
    delta = Cmax - Cmin

    if r >= g and r >= b:
        h = (g-b)/delta
    elif g >= r and g >= b:
        h = (b-r)/delta + 2
    else:
        h = (r-g)/delta + 4

    h *= deg_60

    if Cmax == 0:
        s = 0
    else:
        s = delta / Cmax

    return h, s, Cmax, a


def luminance(r, g, b):
    return r*0.2126 + g*0.7152 + b*0.0722


def colour_distance_hsv(hsv_a, hsv_b):
    h_a, s_a, v_a = hsv_a
    h_b, s_b, v_b = hsv_b

    r_a, g_a, b_a, _ = hsva_to_rgba(h_a, s_a, v_a, 0)
    r_b, g_b, b_b, _ = hsva_to_rgba(h_b, s_b, v_b, 0)

    if r_a > 0.5:
        return math.sqrt(
            3*(r_a-r_b)**2 +
            4*(g_a-g_b)**2 +
            2*(b_a-b_b)**2
        )
    else:
        return math.sqrt(
            2*(r_a-r_b)**2 +
            4*(g_a-g_b)**2 +
            3*(b_a-b_b)**2
        )

    # lum_a = luminance(r_a, g_a, b_a)
    # lum_b = luminance(r_b, g_b, b_b)

    # h_dist = min(abs(h_a-h_b), abs(h_b-h_a))

    # return h_dist * abs(lum_a-lum_b) + abs(s_a-s_b) * abs(lum_a-lum_b)
    # return abs(lum_a-lum_b)

    return math.sqrt(
        (r_a-r_b)**2 +
        (g_a-g_b)**2 +
        (b_a-b_b)**2
    )


K_R = 0.299
K_G = 0.587
# K_R = 0.0593
# K_G = 0.2627
K_B = 1-K_R-K_G


def ycbcr_to_rgb(y, cb, cr):
    r = 2*(1 - K_R)*cr + y
    b = 2*(1 - K_B)*cb + y
    g = (y - K_R*r - K_B*b)/K_G
    return r, g, b


def clip_rgb(r, g, b):
    return (
        min(max(r, 0), 1),
        min(max(g, 0), 1),
        min(max(b, 0), 1),
    )


def angle_to_cbcr_edge(angle):
    cr = math.sin(angle)
    cb = math.cos(angle)
    if abs(cr) > abs(cb):
        factor = 0.5 / abs(cr)
    else:
        factor = 0.5 / abs(cb)
    # factor = 0.5
    return cb * factor, cr * factor


@functools.lru_cache()
def text_to_colour(text):
    # hash_ = hashlib.sha1()
    # hash_.update(text.encode("utf-8"))
    # # lets take four bytes of entropy
    # data = hash_.digest()
    # hue, = struct.unpack("<H", data[:2])

    MASK = 0xffff

    # data = binascii.crc32(text.encode("utf-8"))
    h = hashlib.sha1()
    h.update(text.encode("utf-8"))
    hue = (int.from_bytes(h.digest()[:2], "little") & MASK) / MASK
    # hue = data & 0xffff

    # first attempt, simply mix with the inverse of in_contrast_with
    # initial_color = Qt.QColor(*struct.unpack("<BBB", data), 255)
    # contrast_inverse = Qt.QColor(
    #     255 - in_contrast_with[0],
    #     255 - in_contrast_with[1],
    #     255 - in_contrast_with[2],
    #     255,
    # )
    # FACTOR = 0.4
    # INV_FACTOR = 1-FACTOR

    # return Qt.QColor(
    #     INV_FACTOR*initial_color.red() + FACTOR*contrast_inverse.red(),
    #     INV_FACTOR*initial_color.green() + FACTOR*contrast_inverse.green(),
    #     INV_FACTOR*initial_color.blue() + FACTOR*contrast_inverse.blue(),
    #     255,
    # )

    # if in_contrast_with is not None:
    #     *back, _ = rgba_to_hsva(*in_contrast_with, 1.0)
    # else:
    #     back = None

    # while len(data) > 3:
    #     h, s, v = struct.unpack("<BBB", data[:3])
    #     data = data[1:]
    #     h = h/255 * math.pi*2
    #     s = (s//64 + 4) / 7
    #     v_int = (v//128 + 6)
    #     if back is None:
    #         v = v_int/7
    #         break

    #     for v_base in [v_int, v_int ^ 1]:
    #         v = v_base/7
    #         dist = colour_distance_hsv((h, s, v), back)
    #         if dist >= 0.4:
    #             break
    #     else:
    #         continue
    #     break
    # else:
    #     print("out of options for", text)

    # r, g, b, _ = hsva_to_rgba(h, s, v, 1)
    # return r, g, b

    cb, cr = angle_to_cbcr_edge(hue * math.pi * 2)
    r, g, b = clip_rgb(*ycbcr_to_rgb(0.5**0.45, cb, cr))
    r *= 0.8
    g *= 0.8
    b *= 0.8
    return r, g, b


def mkdir_exist_ok(path):
    try:
        path.mkdir(parents=True)
    except FileExistsError:
        if not path.is_dir():
            raise


@contextlib.contextmanager
def safe_writer(destpath, mode="wb"):
    destpath = pathlib.Path(destpath)
    with tempfile.NamedTemporaryFile(
            mode=mode,
            dir=str(destpath.parent),
            delete=False) as tmpfile:
        try:
            yield tmpfile
        except:
            os.unlink(tmpfile.name)
            raise
        else:
            os.replace(tmpfile.name, str(destpath))
