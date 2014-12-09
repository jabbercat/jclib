import asyncio

import gbulb

from gi.repository import Gtk

asyncio.set_event_loop_policy(gbulb.GApplicationEventLoopPolicy())

loop = asyncio.get_event_loop()

builder = Gtk.Builder()
builder.add_from_file("data/core.glade")

main_window = builder.get_object("roster")

def cb(*args, **kwargs):
    app.add_window(main_window)
    main_window.show_all()

app = Gtk.Application()
app.connect("activate", cb, None)

@asyncio.coroutine
def task():
    while True:
        yield from asyncio.sleep(1)

loop.run_until_complete(task(), application=app)
