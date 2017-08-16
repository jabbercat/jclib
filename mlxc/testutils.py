import unittest

import sqlalchemy
import sqlalchemy.pool

import aioxmpp.callbacks

from aioxmpp.testutils import (
    make_connected_client,
)


def inmemory_database(declarative_base):
    engine = sqlalchemy.create_engine(
        "sqlite:///:memory:",
        connect_args={'check_same_thread': False},
        poolclass=sqlalchemy.pool.StaticPool
    )

    # https://stackoverflow.com/questions/1654857/
    @sqlalchemy.event.listens_for(engine, "connect")
    def do_connect(dbapi_connection, connection_record):
        # disable pysqlite's emitting of the BEGIN statement entirely.
        # also stops it from emitting COMMIT before any DDL.
        dbapi_connection.isolation_level = None

    @sqlalchemy.event.listens_for(engine, "begin")
    def do_begin(conn):
        # emit our own BEGIN
        conn.execute("BEGIN")

    declarative_base.metadata.create_all(engine)
    sessionmaker = sqlalchemy.orm.sessionmaker(bind=engine)
    return sessionmaker


class MLXCTestCase(unittest.TestCase):
    def setUp(self):
        self.__patches = []
        self.app = unittest.mock.Mock()
        self.app.client = unittest.mock.Mock([
            "client_by_account"
        ])
        self.app.client.on_client_prepare = aioxmpp.callbacks.AdHocSignal()
        self.app.client.on_client_stopped = aioxmpp.callbacks.AdHocSignal()
        self.app.identities = unittest.mock.Mock([])
        self.app.identities.on_identity_added = aioxmpp.callbacks.AdHocSignal()
        self.app.identities.on_identity_removed = \
            aioxmpp.callbacks.AdHocSignal()
        self.app.conversations = unittest.mock.Mock([])

        self.aioxmpp_client = make_connected_client()
        self.app.client.client_by_account.return_value = self.aioxmpp_client

        for attr in ["client", "identities", "conversations"]:
            self.__patches.append(
                unittest.mock.patch(
                    "mlxc.app.{}".format(attr),
                    new=getattr(self.app, attr)
                )
            )

        for patch in self.__patches:
            patch.start()

    def tearDown(self):
        for patch in self.__patches:
            patch.stop()
