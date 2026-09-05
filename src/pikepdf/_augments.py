# SPDX-FileCopyrightText: 2022 James R. Barlow
# SPDX-License-Identifier: MPL-2.0

"""A peculiar method of monkeypatching C++ binding classes with Python methods."""

from __future__ import annotations

import inspect
import platform
from collections.abc import Callable
from typing import Any, Protocol, TypeVar


class AugmentedCallable(Protocol):
    """Protocol for any method, with attached booleans."""

    _augment_if_no_cpp: bool

    def __call__(self, *args, **kwargs) -> Any:
        """Any function."""  # pragma: no cover


def augment_if_no_cpp(fn: AugmentedCallable) -> AugmentedCallable:
    """Provide a Python implementation if no C++ implementation exists."""
    fn._augment_if_no_cpp = True
    return fn


def _is_inherited_method(meth: Callable) -> bool:
    # Augmenting a C++ with a method that cls inherits from the Python
    # object is never what we want.
    return meth.__qualname__.startswith('object.')


def _is_augmentable(m: Any) -> bool:
    return (
        inspect.isfunction(m) and not _is_inherited_method(m)
    ) or inspect.isdatadescriptor(m)


Tcpp = TypeVar('Tcpp')
T = TypeVar('T')


def augments(cls_cpp: type[Tcpp]):
    """Attach methods of a Python support class to an existing class.

    This monkeypatches all methods defined in the support class onto an
    existing class. Example:

    .. code-block:: python

        @augments(ClassDefinedInCpp)
        class SupportClass:
            def foo(self):
                pass

    The Python method 'foo' will be monkeypatched on ClassDefinedInCpp. SupportClass
    has no meaning on its own and should not be used, but gets returned from
    this function so IDE code inspection doesn't get too confused.

    We don't subclass because it's much more convenient to monkeypatch Python
    methods onto the existing Python binding of the C++ class. For one thing,
    this allows the implementation to be moved from Python to C++ or vice
    versa. It saves having to implement an intermediate Python subclass and then
    ensures that the C++ superclass never 'leaks' to pikepdf users. Finally,
    wrapper classes and subclasses can become problematic if the call stack
    crosses the C++/Python boundary multiple times.

    A support class may not redefine a method the C++ class already provides;
    doing so raises RuntimeError. When a C++ implementation needs different
    behavior, change it in C++ rather than wrapping it from Python, so that the
    method has exactly one implementation.

    For data fields to work, the target class must be
    tagged ``nb::dynamic_attr`` in nanobind.

    Strictly, the target class does not have to be C++ or derived from nanobind.
    This works on pure Python classes too.

    THIS DOES NOT work for class methods.

    (Alternative ideas, originally raised against pybind11:
    https://github.com/pybind/pybind11/issues/1074)
    """
    OVERRIDE_WHITELIST = {'__eq__', '__hash__', '__repr__'}
    if platform.python_implementation() == 'PyPy':
        # Historical note: with pybind11 + PyPy we observed that either PyPy or
        # pybind11's PyPy interface automatically added a __getattr__, so we
        # whitelisted it here. nanobind does not target PyPy, so this branch is
        # currently dead code. If PyPy support is ever revived, review how the
        # binding library interacts with PyPy before relying on this.
        OVERRIDE_WHITELIST |= {'__getattr__'}  # pragma: no cover

    def class_augment(cls: type[T], cls_cpp: type[Tcpp] = cls_cpp) -> type[T]:
        # inspect.getmembers has different behavior on PyPy - in particular it seems
        # that a typical PyPy class like cls will have more methods that it considers
        # methods than CPython does. Our predicate should take care of this.
        for name, member in inspect.getmembers(cls, predicate=_is_augmentable):
            if name == '__weakref__':
                continue
            if hasattr(cls_cpp, name) and hasattr(cls, name):
                if name in getattr(cls, '__abstractmethods__', set()):
                    # The support class subclasses an ABC to pick up its mixin
                    # methods and leaves this one abstract, because C++ provides
                    # the implementation. Installing the abstract stub would
                    # replace a working method with one that raises.
                    continue
                if getattr(getattr(cls, name), '_augment_if_no_cpp', False):
                    # If tagged as "augment if no C++", we only want the binding to be
                    # applied when the primary class does not provide a C++
                    # implementation. Usually this would be a function that is not
                    # provided by nanobind in some template.
                    continue
                if name not in OVERRIDE_WHITELIST:
                    # If the original C++ class and Python support class both define
                    # the same name, we have a conflict, because this is augmentation
                    # not inheritance. The exception is that nanobind (like pybind11
                    # before it) provides defaults for __eq__, __hash__ and __repr__
                    # that we often do want to override directly.
                    raise RuntimeError(
                        f"C++ {cls_cpp} and Python {cls} both define the same "
                        f"non-abstract method {name}: "
                        f"{getattr(cls_cpp, name, '')!r}, "
                        f"{getattr(cls, name, '')!r}"
                    )
            if inspect.isfunction(member):
                setattr(cls_cpp, name, member)
                installed_member = getattr(cls_cpp, name)
                installed_member.__qualname__ = member.__qualname__.replace(
                    cls.__name__, cls_cpp.__name__
                )
            elif inspect.isdatadescriptor(member):
                setattr(cls_cpp, name, member)

        def disable_init(self):
            # Prevent initialization of the support class
            raise NotImplementedError(self.__class__.__name__ + '.__init__')

        cls.__init__ = disable_init  # type: ignore
        return cls

    return class_augment
