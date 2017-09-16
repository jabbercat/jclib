from .backends import XDGBackend
from .frontends import (
    DatabaseFrontend,
    LargeBlobFrontend,
    SmallBlobFrontend,
    XMLFrontend,
    GlobalLevel,
    AccountLevel,
    PeerLevel,
)
from .common import StorageLevel, StorageType

UNIX_APPNAME = "mlxc.zombofant.net"

_backend = XDGBackend(UNIX_APPNAME)

databases = DatabaseFrontend(_backend)
large_blobs = LargeBlobFrontend(_backend)
small_blobs = SmallBlobFrontend(_backend)
xml = XMLFrontend(_backend)

from .manager import WriteManager
