# SPDX-FileCopyrightText: 2025 James R. Barlow
# SPDX-License-Identifier: MPL-2.0


from __future__ import annotations

# Conversion mode API
from contextlib import contextmanager
from typing import Literal

from pikepdf import _core


def set_object_conversion_mode(mode: Literal['implicit', 'explicit']) -> None:
    """Set global object conversion mode.

    This controls how PDF scalar values (integers, booleans, reals) are
    returned when accessing PDF objects.

    Args:
        mode: Conversion mode.
            - ``'implicit'`` (default): Automatically convert PDF integers to
              Python ``int``, booleans to ``bool``, and reals to ``Decimal``.
              This is the legacy behavior.
            - ``'explicit'``: Return PDF scalars as ``pikepdf.Integer``,
              ``pikepdf.Boolean``, and ``pikepdf.Real`` objects. This enables
              better type safety and static type checking.

    Example:
        >>> pikepdf.set_object_conversion_mode('explicit')
        >>> pdf = pikepdf.open('test.pdf')
        >>> count = pdf.Root.Count
        >>> isinstance(count, pikepdf.Integer)  # True in explicit mode
        True
        >>> int(count)  # Convert to Python int
        5

    .. versionadded:: 10.1
    """
    _core._set_explicit_conversion_mode(mode == 'explicit')


def get_object_conversion_mode() -> Literal['implicit', 'explicit']:
    """Get current object conversion mode.

    Returns:
        The current conversion mode: ``'implicit'`` or ``'explicit'``.

    .. versionadded:: 10.1
    """
    return 'explicit' if _core._get_explicit_conversion_mode() else 'implicit'


@contextmanager
def explicit_conversion():
    """Context manager for explicit conversion mode.

    Within this context, PDF scalar values will be returned as
    ``pikepdf.Integer``, ``pikepdf.Boolean``, and ``pikepdf.Real`` objects
    instead of being automatically converted to Python native types.

    Example:
        >>> with pikepdf.explicit_conversion():
        ...     pdf = pikepdf.open('test.pdf')
        ...     count = pdf.Root.Count
        ...     isinstance(count, pikepdf.Integer)
        True

    .. versionadded:: 10.1
    """
    old = _core._get_explicit_conversion_mode()
    _core._set_explicit_conversion_mode(True)
    try:
        yield
    finally:
        _core._set_explicit_conversion_mode(old)
