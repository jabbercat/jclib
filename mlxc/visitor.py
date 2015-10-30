import abc
import collections
import functools


def for_class(class_):
    def wrap(fun):
        fun.roster_visited_class = class_
        return fun
    return wrap


class VisitorMeta(abc.ABCMeta):
    """
    Metaclass for :class:`Visitor`. Normally, it is sufficient and more
    convenient to inherit from :class:`Visitor`.

    This metaclass collects methods which have been decorated with
    :func:`for_class` as visitors for the respective class.

    .. seealso::

       For an example and usage guide see :class:`Visitor`.

    .. automethod:: visitor

    """

    @staticmethod
    def _issubclass_cmp(clsa, clsb):
        if issubclass(clsa, clsb):
            return -1
        elif issubclass(clsb, clsa):
            return 1
        return 0

    def __new__(mcls, name, bases, namespace):
        visitors = collections.OrderedDict()

        for base in reversed(bases):
            if hasattr(base, "VISITOR_HANDLERS"):
                visitors.update(base.VISITOR_HANDLERS)

        for key, value in namespace.items():
            if hasattr(value, "roster_visited_class"):
                visitors[value.roster_visited_class] = value
                del value.roster_visited_class
                continue

        visitors = sorted(
            visitors.items(),
            key=lambda x: functools.cmp_to_key(mcls._issubclass_cmp)(x[0])
        )

        namespace["VISITOR_HANDLERS"] = visitors

        return super().__new__(mcls, name, bases, namespace)

    def __prepare__(name, bases):
        return collections.OrderedDict()

    def visitor(cls, object_to_visit):
        """
        Find the method handling the most specific base class of the class of
        `object_to_visit`. The class of `object_to_visit` itself is the most
        specific base class.

        If no such base class is found, :class:`KeyError` is raised.
        """
        for cls, visitor in cls.VISITOR_HANDLERS:
            if isinstance(object_to_visit, cls):
                return visitor
        raise KeyError(type(object_to_visit))


class Visitor(metaclass=VisitorMeta):
    """
    Base class to implement generic visitors. This uses :class:`VisitorMeta`.

    The idea is to use :meth:`visit` to send an object to the
    visitor. Subclasses can declare methods which handle different object
    types:

    .. code-block:: python

       class Foo(visitor.Visitor):
           @visitor.for_class(SomeType)
           def visit_some_type(self, obj):
               pass

           @visitor.for_class(AnotherType)
           def visit_another_type(self, obj):
               pass

    Calling ``Foo().visit`` with an instance of ``AnotherType`` would invoke
    ``visit_another_type``, as would calling it with an instance of a subclass
    of ``AnotherType``. The same holds for ``SomeType`` and
    ``visit_some_type``.

    If an object has both ``SomeType`` and ``AnotherType`` as bases and
    ``AnotherType`` is a base of ``SomeType``, the handler of ``SomeType``
    wins (most specific rule).

    .. warning::

       If an object has both ``AnotherType`` and ``SomeType`` as base classes
       and ``AnotherType`` and ``SomeType`` have no inheritance relationship,
       which method gets called depends on the following rules:

       * If one of the handler methods was declared in a superclass but not in
         the current class, as in the following example::

           class Foo(visitor.Visitor):
               @visitor.for_class(SomeType)
               def visit_some_type(self, obj):
                   pass

           class Bar(Foo):
               @visitor.for_class(AnotherType)
               def visit_another_type(self, obj):
                   pass

         the handler declared in the subclass wins. In this case that would be
         the handler for ``AnotherType``.

       * If both methods are declared in the same class (like in the first
         example), the one first declared is called (this is implemented by
         using a :class:`collections.OrderedDict` as namespace for the class).

         Do **not** rely on this behaviour before the release of version 1.0;
         a possible alternative which might be implemented is using the order
         of inheritance of the class doing the multi-inheritance to decide
         which handler to call.

    When implementing visitors (using the :func:`for_class`) decorator, you
    might want to call the visitors of a superclass. This is currently only
    possible if you know the method name used by that handler. In future
    versions, support for calling visitors using the object being visited and
    something like ``super()`` might be added.

    .. automethod:: visit

    """
    def visit(self, object_to_visit):
        """
        Pass the `object_to_visit` to the responsible visitor.
        """
        try:
            visitor = type(self).visitor(object_to_visit)
        except KeyError:
            raise TypeError("unhandled type in visitor: {}".format(
                type(object_to_visit)
            )) from None
        visitor(self, object_to_visit)
