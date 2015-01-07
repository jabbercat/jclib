import abc
import functools
import logging

logger = logging.getLogger(__name__)

CATCHALL = object()

def _test_fn(fn):
    if not hasattr(fn, "__call__"):
        raise TypeError("event handler must be callable")

def _annotate_function(fn, event_types):
    fn._mlxc__event_handler_for = frozenset(event_types)
    return fn

def handler_for(*event_types):
    def wrap(fn):
        _test_fn(fn)
        return _annotate_function(fn, event_types)
    return wrap

def handler(fn):
    if not hasattr(fn, "__name__"):
        raise TypeError("event handler must have a name (use event_handler_for"
                        " to override)")
    return handler_for(fn.__name__)(fn)

def catchall(fn):
    return handler_for(CATCHALL)(fn)

class _EventHandlingMeta(abc.ABCMeta):
    def __new__(mcls, name, bases, namespace):
        handlers = {}
        for base in reversed(bases):
            if isinstance(base, _EventHandlingMeta):
                handlers.update(base._EventHandler__event_handlers)

        for fn in namespace.values():
            if not hasattr(fn, "_mlxc__event_handler_for"):
                continue
            event_types = fn._mlxc__event_handler_for
            for event_type in event_types:
                if event_type in handlers:
                    raise TypeError("multiple handlers for same event type")
                handlers[event_type] = fn

        namespace["_EventHandler__event_handlers".format(name)] = handlers

        return abc.ABCMeta.__new__(mcls, name, bases, namespace)

class Event:
    def __init__(self, type_):
        self.__type = type_

    @property
    def type_(self):
        return self.__type

    def __repr__(self):
        return "<{} (type={}) object at 0x{:x}>".format(
            type(self).__name__,
            self.type_,
            id(self))

class EventHandler(metaclass=_EventHandlingMeta):
    def dispatch_event(self, ev):
        """
        Dispatch the given event object *ev*.

        If no handler is able to handle *ev* and no handler for the event type
        :attr:`CATCHALL` exists, a :class:`TypeError` is raised.
        """

        try:
            handler = self.__event_handlers[ev.type_]
        except KeyError:
            try:
                handler = self.__event_handlers[CATCHALL]
            except KeyError:
                raise TypeError("{!r} does not support event {!r}".format(
                    self,
                    ev.type_)) from None

        return handler(self, ev)

def accepts_event(obj, event_type):
    return (event_type in obj._EventHandler__event_handlers or
            CATCHALL in obj._EventHandler__event_handlers)
