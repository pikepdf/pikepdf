# SPDX-FileCopyrightText: 2022 James R. Barlow
# SPDX-License-Identifier: MPL-2.0

# Type stubs for the bindings in src/core/rectangle.cpp.
# See pikepdf/_core/__init__.pyi for how this stub package is laid out.

# pylint: disable=no-method-argument,unused-argument,no-self-use,too-many-public-methods
# ruff: noqa: D418
# mypy: disable-error-code="misc"

from __future__ import annotations

from typing import Any, overload

from pikepdf._core._object_construct import Array

class Rectangle:
    """A PDF rectangle.

    Typically this will be a rectangle in PDF units (points, 1/72").
    Unlike raster graphics, the rectangle is defined by the **lower**
    left and upper right points.

    Rectangles in PDF are encoded as :class:`pikepdf.Array` with exactly
    four numeric elements, ordered as ``llx lly urx ury``.
    See {{ pdfrm }} section 7.9.5.

    The rectangle may be considered degenerate if the lower left corner
    is not strictly less than the upper right corner.

    .. versionadded:: 2.14

    .. versionchanged:: 8.5
        Added operators to test whether rectangle ``a`` is contained in
        rectangle ``b`` (``a <= b``) and to calculate their intersection
        (``a & b``).
    """

    llx: float = ...
    """The lower left corner on the x-axis."""
    lly: float = ...
    """The lower left corner on the y-axis."""
    urx: float = ...
    """The upper right corner on the x-axis."""
    ury: float = ...
    """The upper right corner on the y-axis."""
    @overload
    def __init__(self, llx: float, lly: float, urx: float, ury: float, /) -> None: ...
    @overload
    def __init__(self, other: Rectangle, /) -> None: ...
    @overload
    def __init__(self, other: Array, /) -> None: ...
    def __init__(self, *args) -> None:
        """Construct a new rectangle."""
    def __and__(self, other: Rectangle, /) -> Rectangle:
        """Return the bounding Rectangle of the common area of self and other."""
    def __le__(self, other: Rectangle, /) -> bool:
        """Return True if self is contained in other or equal to other."""
    @property
    def width(self) -> float:
        """The width of the rectangle."""
    @property
    def height(self) -> float:
        """The height of the rectangle."""
    @property
    def lower_left(self) -> tuple[float, float]:
        """A point for the lower left corner."""
    @property
    def lower_right(self) -> tuple[float, float]:
        """A point for the lower right corner."""
    @property
    def upper_left(self) -> tuple[float, float]:
        """A point for the upper left corner."""
    @property
    def upper_right(self) -> tuple[float, float]:
        """A point for the upper right corner."""
    def as_array(self) -> Array:
        """Returns this rectangle as a :class:`pikepdf.Array`."""
    def to_bbox(self) -> Rectangle:
        """Returns the origin-centred bounding box that encloses this rectangle.

        Create a new rectangle with the same width and height as this one, but
        located at the origin (0, 0).

        Bounding boxes represent independent coordinate systems, such as for
        Form XObjects.
        """
    def __eq__(self, other: Any, /) -> bool: ...
    def __repr__(self) -> str: ...
