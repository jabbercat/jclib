#!/usr/bin/python3
import asyncio
import aioxmpp
import uuid
import jclib.storage.frontends as frontends
import jclib.storage.backends as backends
from jclib.storage.common import StorageLevel, StorageType
from jclib.storage.frontends import PeerLevel, GlobalLevel, AccountLevel
b = backends.XDGBackend("jabbercat.org")
smallblobs = frontends.SmallBlobFrontend(b)
append = frontends.AppendFrontend(b)
xml = frontends.XMLFrontend(b)
peer = aioxmpp.JID.fromstr("romeo@montague.lit")
account = aioxmpp.JID.fromstr("juliet@capulet.lit")

def await_(fut):
    return asyncio.get_event_loop().run_until_complete(fut)
