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
