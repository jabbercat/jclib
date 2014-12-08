import asyncio

import gbulb

from gi.repository import Gtk

asyncio.set_event_loop_policy(gbulb.GApplicationEventLoopPolicy())

loop = asyncio.get_event_loop()

builder = Gtk.Builder()
builder.add_from_file("data/core.glade")

def foo(window, event):
    # window.hide()
    # return True
    return False

main_window = builder.get_object("roster")
main_window.connect("delete_event", foo)

def cb(*args, **kwargs):
    app.add_window(main_window)
    main_window.show_all()


app = Gtk.Application()
app.connect("activate", cb, None)

@asyncio.coroutine
def foo():
    status_icon = builder.get_object("statusicon1")
    print(dir(status_icon))
    status_icon.set_from_stock(Gtk.STOCK_NEW)
    status_icon.set_visible(True)
    try:
        while True:
            # print("foo")
            # dlg = Gtk.MessageDialog(
            #     None,
            #     Gtk.DialogFlags.MODAL,
            #     Gtk.MessageType.INFO,
            #     Gtk.ButtonsType.YES_NO)
            # dlg.set_markup("Hello World!")
            # fut = gbulb.wait_signal(dlg, "response")
            # dlg.show_all()
            # yield from fut
            # print(fut.result())
            # dlg.close()
            yield from asyncio.sleep(1)
    except Exception as err:
        print("err: ", err)
        raise
    finally:
        print("exiting")

task = asyncio.async(foo())
try:
    loop.run_forever(application=app)
finally:
    task.cancel()
    loop.run_until_complete(task)
