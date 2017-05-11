from .backends import XDGBackend
from .frontends import (
    DatabaseFrontend,
    LargeBlobFrontend,
    SmallBlobFrontend,
)

UNIX_APPNAME = "mlxc.zombofant.net"

_backend = XDGBackend(UNIX_APPNAME)

databases = DatabaseFrontend(_backend)
large_blobs = LargeBlobFrontend(_backend)
small_blobs = SmallBlobFrontend(_backend)
