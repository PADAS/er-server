import functools
import inspect
import logging
import time
from typing import Callable

from .interfaces import SharedResourceHandler


class reify(object):
    """Use as a class method decorator.  It operates almost exactly like the
    Python ``@property`` decorator, but it puts the result of the method it
    decorates into the instance dict after the first call, effectively
    replacing the function it decorates with an instance variable.  It is, in
    Python parlance, a non-data descriptor.  An example:
    .. code-block:: python
       class Foo(object):
           @reify
           def jammy(self):
               print('jammy called')
               return 1
    And usage of Foo:
    >>> f = Foo()
    >>> v = f.jammy
    'jammy called'
    >>> print(v)
    1
    >>> f.jammy
    1
    >>> # jammy func not called the second time; it replaced itself with 1

    Source: https://github.com/Pylons/pyramid/blob/master/pyramid/decorator.py
    """

    def __init__(self, wrapped):
        self.wrapped = wrapped
        functools.update_wrapper(self, wrapped)

    def __get__(self, inst, objtype=None):
        if inst is None:
            return self
        val = self.wrapped(inst)
        setattr(inst, self.wrapped.__name__, val)
        return val


def retry_on_exception(exception_type, retry_forever=False, max_retries=3, delay=1):
    """Decorator to retry a function when a specified exception occurs. If the
    retries are exausted, the exception is raised anyway.

    :param exception_type: Exception
    :param loop_forever: bool
    :param max_retries: int
    :param delay: int
    :return: decorated function
    :rtype: Callable
    """

    def decorator(func):
        logger = logging.getLogger(func.__module__)

        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            retries = 0
            exception = None
            while retry_forever or retries < max_retries:
                try:
                    return func(*args, **kwargs)
                except exception_type as exc:
                    exception = exc
                    retries += 1
                    logger.warning(
                        "Caught %s: %s. Retrying %s.", exception_type.__name__, str(exception), func.__name__
                    )
                    time.sleep(delay)

            if exception:
                raise exception

        return wrapper

    return decorator


def use_shared_resource(method: Callable):
    """Decorator to execute a method class using a shared resource.
    It ensures the connection is locked before and properly released after the
    operation is complete.

    :param method: Callable
    :rtype: Callable
    """

    @functools.wraps(method)
    def method_using_shared_resource(instance: SharedResourceHandler, *args, **kwargs):
        failure = None
        result = None
        try:
            instance.aquire_resource()
            result = method(instance, *args, **kwargs)
        except Exception as exc:
            failure = exc
            instance.report_error(failure)

        finally:
            instance.release_resource()

        if failure:
            raise failure

        return result

    return method_using_shared_resource


def apply_decorator_to_public_methods(decorator):
    @functools.wraps(decorator)
    def class_decorator(cls):
        for attr_name, attr_value in inspect.getmembers(cls, inspect.isfunction):
            if callable(attr_value) and not attr_name.startswith("_"):
                setattr(cls, attr_name, decorator(attr_value))
        return cls

    return class_decorator
