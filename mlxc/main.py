import asyncio

import mlxc.roster

@asyncio.coroutine
def main():
    roster = mlxc.roster.Roster()
    roster.show()
    fut = asyncio.Future()
    yield from fut
