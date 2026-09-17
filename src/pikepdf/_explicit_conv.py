# SPDX-FileCopyrightText: 2025 James R. Barlow
# SPDX-License-Identifier: MPL-2.0


from __future__ import annotations

# Conversion mode API
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any, Literal

from pikepdf import _core

if TYPE_CHECKING:
    from pikepdf import Pdf


def unbox(value: Any) -> Any:
    """Return a PDF scalar as the native Python value implicit mode would give.

    Implicit conversion mode already hands back ``int``, ``bool`` or
    ``Decimal`` for a PDF number; explicit mode hands back a
    :class:`pikepdf.Integer`, :class:`pikepdf.Boolean` or :class:`pikepdf.Real`.
    Code that computes with a value rather than storing it needs the native form
    in both modes, and unlike :meth:`~pikepdf.Object.as_int` and friends this
    does not require knowing which of the three it is.

    ``Integer`` becomes ``int``, ``Boolean`` becomes ``bool`` and ``Real``
    becomes :class:`decimal.Decimal`. Anything else -- a native Python value,
    ``None``, a :class:`~pikepdf.Name`, :class:`~pikepdf.String`,
    :class:`~pikepdf.Array`, :class:`~pikepdf.Dictionary` or
    :class:`~pikepdf.Stream` -- is returned unchanged, so ``unbox`` can be
    applied to a value read in either mode.

    Arithmetic and comparisons on ``Integer`` and ``Real`` already produce
    native results, so ``unbox`` is needed only where Python offers no
    protocol for a foreign number: ``isinstance`` checks, ``is True``,
    :class:`decimal.Decimal` construction, JSON serialization, and returning
    a value from a function documented to give a native type.

    Example:
        >>> with pikepdf.explicit_conversion():
        ...     d = pikepdf.Dictionary(MaxLen=12, Marked=True)
        ...     pikepdf.unbox(d.MaxLen)
        12
        >>> pikepdf.unbox(d.Marked) is True
        True

    .. versionadded:: 10.14
    """
    if not isinstance(value, _core.Object):
        return value
    from pikepdf.objects import Boolean, Integer, Real

    if isinstance(value, Integer):
        return value.as_int()
    if isinstance(value, Boolean):
        return value.as_bool()
    if isinstance(value, Real):
        return value.as_decimal()
    return value


@contextmanager
def _thread_conversion_mode(explicit: bool):
    """Push a thread-local conversion mode override and undo it on exit.

    The push returns a token identifying the depth of the override stack before
    the push; the pop truncates the stack back to that depth. Truncating rather
    than popping means that context managers exited out of order cannot corrupt
    the stack -- exiting an outer one discards the inner ones with it, and the
    inner one's own exit then does nothing.
    """
    token = _core._push_thread_conversion_mode(explicit)
    try:
        yield
    finally:
        _core._pop_thread_conversion_mode(token)


def set_object_conversion_mode(mode: Literal['implicit', 'explicit']) -> None:
    """Set global object conversion mode.

    This controls how PDF scalar values (integers, booleans, reals) are
    returned when accessing PDF objects.

    Args:
        mode: ``'implicit'`` (the default) converts PDF integers to Python
            ``int``, booleans to ``bool``, and reals to ``Decimal``; this is
            the legacy behavior. ``'explicit'`` returns PDF scalars as
            ``pikepdf.Integer``, ``pikepdf.Boolean``, and ``pikepdf.Real``
            objects, which enables better type safety and static type checking.

    Example:
        >>> pikepdf.set_object_conversion_mode('explicit')
        >>> count = pikepdf.Dictionary(Count=5).Count
        >>> isinstance(count, pikepdf.Integer)  # True in explicit mode
        True
        >>> int(count)  # Convert to Python int
        5
        >>> pikepdf.set_object_conversion_mode('implicit')  # Restore the default

    .. versionadded:: 10.1

    .. versionchanged:: 10.14
        Raises :exc:`ValueError` if *mode* is not ``'implicit'`` or
        ``'explicit'``. Previously any value other than ``'explicit'`` was
        silently treated as ``'implicit'``.
    """
    if mode not in ('implicit', 'explicit'):
        raise ValueError("mode must be 'implicit' or 'explicit'")
    _core._set_explicit_conversion_mode(mode == 'explicit')


def get_object_conversion_mode(
    pdf: Pdf | None = None,
) -> Literal['implicit', 'explicit']:
    """Get current effective object conversion mode.

    This returns the mode that is currently in effect for the calling thread,
    taking into account the global setting, any active
    :func:`explicit_conversion` or :func:`implicit_conversion` context
    managers, and, if *pdf* is given, that document's own conversion mode.

    Args:
        pdf: If given, report the mode that applies to objects owned by this
            :class:`pikepdf.Pdf`. The resolution order is context manager,
            then the document's :attr:`pikepdf.Pdf.conversion_mode`, then the
            global setting.

    Returns:
        The current effective conversion mode: ``'implicit'`` or ``'explicit'``.

    .. versionadded:: 10.1

    .. versionchanged:: 10.2
        Now returns the effective mode, including thread-local context manager state.

    .. versionchanged:: 10.14
        Accepts an optional *pdf* argument.
    """
    if pdf is not None:
        return 'explicit' if _core._get_effective_explicit_mode_for(pdf) else 'implicit'
    return 'explicit' if _core._get_effective_explicit_mode() else 'implicit'


@contextmanager
def explicit_conversion():
    """Context manager for explicit conversion mode.

    Within this context, PDF scalar values will be returned as
    ``pikepdf.Integer``, ``pikepdf.Boolean``, and ``pikepdf.Real`` objects
    instead of being automatically converted to Python native types.

    This context manager is thread-local: it only affects the current thread
    and takes precedence over the global setting from
    :func:`set_object_conversion_mode`. Nested context managers are supported.

    Example:
        >>> with pikepdf.explicit_conversion():
        ...     count = pikepdf.Dictionary(Count=5).Count
        ...     isinstance(count, pikepdf.Integer)
        True

    .. versionadded:: 10.1

    .. versionchanged:: 10.2
        Now thread-local and takes precedence over global setting.
    """
    with _thread_conversion_mode(True):
        yield


@contextmanager
def implicit_conversion():
    """Context manager for implicit conversion mode.

    Within this context, PDF scalar values are automatically converted to
    Python native types: ``int``, ``bool`` and ``decimal.Decimal``. This is
    pikepdf's legacy behavior.

    This context manager is thread-local: it only affects the current thread,
    and it takes precedence over both a document's
    :attr:`pikepdf.Pdf.conversion_mode` and the global setting from
    :func:`set_object_conversion_mode`. It may be nested with
    :func:`explicit_conversion` in either order.

    Example:
        >>> with pikepdf.explicit_conversion():
        ...     with pikepdf.implicit_conversion():
        ...         isinstance(pikepdf.Dictionary(Value=42).Value, int)
        True

    .. versionadded:: 10.14
    """
    with _thread_conversion_mode(False):
        yield
