# SPDX-FileCopyrightText: 2022 James R. Barlow
# SPDX-License-Identifier: MPL-2.0

# Type stubs for the bindings in src/core/matrix.cpp.
# See pikepdf/_core/__init__.pyi for how this stub package is laid out.

# pylint: disable=no-method-argument,unused-argument,no-self-use,too-many-public-methods
# ruff: noqa: D418
# mypy: disable-error-code="misc"

from __future__ import annotations

from typing import TYPE_CHECKING, Any, overload

from pikepdf._core._object_construct import Array
from pikepdf._core._rectangle import Rectangle

if TYPE_CHECKING:
    import numpy as np

class Matrix:
    r"""A 2D affine matrix for PDF transformations.

    PDF uses matrices to transform document coordinates to screen/device
    coordinates.

    PDF matrices are encoded as :class:`pikepdf.Array` with exactly
    six numeric elements, ordered as ``a b c d e f``.

    .. math::

        \begin{bmatrix}
        a & b & 0 \\
        c & d & 0 \\
        e & f & 1 \\
        \end{bmatrix}

    The approximate interpretation of these six parameters is documented
    below. The values (0, 0, 1) in the third column are fixed, so a
    general 3×3 matrix cannot be converted to a PDF matrix.

    PDF transformation matrices are the transpose of most textbook
    treatments.  In a textbook, typically ``A × vc`` is used to
    transform a column vector ``vc=(x, y, 1)`` by the affine matrix ``A``.
    In PDF, the matrix is the transpose of that in the textbook,
    and ``vr × A'`` is used to transform a row vector ``vr=(x, y, 1)``.

    Transformation matrices specify the transformation from the new
    (transformed) coordinate system to the original (untransformed)
    coordinate system. x' and y' are the coordinates in the
    *untransformed* coordinate system, and x and y are the
    coordinates in the *transformed* coordinate system.

    PDF order:

    .. math::

        \begin{equation}
        \begin{bmatrix}
        x' & y' & 1
        \end{bmatrix}
        =
        \begin{bmatrix}
        x & y & 1
        \end{bmatrix}
        \begin{bmatrix}
        a & b & 0 \\
        c & d & 0 \\
        e & f & 1
        \end{bmatrix}
        \end{equation}

    To concatenate transformations, use the matrix multiple (``@``)
    operator to **pre**-multiply the next transformation onto existing
    transformations.

    Alternatively, use the .translated(), .scaled(), and .rotated()
    methods to chain transformation operations.

    Addition and other operations are not implemented because they're not
    that meaningful in a PDF context.

    Matrix objects are immutable. All transformation methods return
    new matrix objects.

    .. versionadded:: 8.7
    """

    @overload
    def __init__(self):
        """Construct an identity matrix."""
    @overload
    def __init__(
        self, a: float, b: float, c: float, d: float, e: float, f: float, /
    ): ...
    @overload
    def __init__(self, other: Matrix): ...
    @overload
    def __init__(self, values: tuple[float, float, float, float, float, float], /): ...
    @classmethod
    def identity(cls) -> Matrix:
        """Construct an identity matrix.

        More explicit than the constructor.

        .. versionadded:: 9.7.0
        """
    @property
    def a(self) -> float:
        """``a`` is the horizontal scaling factor."""
    @property
    def b(self) -> float:
        """``b`` is horizontal skewing."""
    @property
    def c(self) -> float:
        """``c`` is vertical skewing."""
    @property
    def d(self) -> float:
        """``d`` is the vertical scaling factor."""
    @property
    def e(self) -> float:
        """``e`` is the horizontal translation."""
    @property
    def f(self) -> float:
        """``f`` is the vertical translation."""
    @property
    def shorthand(self) -> tuple[float, float, float, float, float, float]:
        """Return the 6-tuple (a,b,c,d,e,f) that describes this matrix."""
    def encode(self) -> bytes:
        """Encode matrix to bytes suitable for including in a PDF content stream."""
    def translated(self, tx, ty) -> Matrix:
        """Return a translated copy of this matrix.

        Calculates ``Matrix(1, 0, 0, 1, tx, ty) @ self``.

        Args:
            tx: horizontal translation
            ty: vertical translation
        """
    def scaled(self, sx, sy) -> Matrix:
        """Return a scaled copy of this matrix.

        Calculates ``Matrix(sx, 0, 0, sy, 0, 0) @ self``.

        Args:
            sx: horizontal scaling
            sy: vertical scaling
        """
    def rotated(self, angle_degrees_ccw) -> Matrix:
        """Return a rotated copy of this matrix.

        Calculates
        ``Matrix(cos(angle), sin(angle), -sin(angle), cos(angle), 0, 0) @ self``.

        Args:
            angle_degrees_ccw: angle in degrees counterclockwise
        """
    def __matmul__(self, other: Matrix, /) -> Matrix:
        """Return the matrix product of two matrices.

        Can be used to concatenate transformations. Transformations should be
        composed by **pre**-multiplying matrices. For example, to apply a
        scaling transform, one could do::

            scale = pikepdf.Matrix(2, 0, 0, 2, 0, 0)
            scaled = scale @ matrix
        """
    def inverse(self) -> Matrix:
        """Return the inverse of the matrix.

        The inverse matrix reverses the transformation of the original matrix.

        In rare situations, the inverse may not exist. In that case, an
        exception is thrown. The PDF will likely have rendering problems.
        """
    def __array__(self, dtype: Any = None, copy: bool | None = True) -> np.ndarray:
        """Convert this matrix to a NumPy array of type dtype.

        If copy is True, a copy is made. If copy is False, an exception is raised.

        If numpy is not installed, this will throw an exception.
        """
    def as_array(self) -> Array:
        """Convert this matrix to a pikepdf.Array.

        A Matrix cannot be inserted into a PDF directly. Use this function
        to convert a Matrix to a pikepdf.Array, which can be inserted.
        """
    @overload
    def transform(self, point: tuple[float, float]) -> tuple[float, float]:
        """Transform a point by this matrix.

        Computes [x y 1] @ self.
        """
    @overload
    def transform(self, rect: Rectangle) -> Rectangle: ...
    def __repr__(self) -> str: ...
    def __eq__(self, other: Any, /) -> bool: ...
    def __getstate__(self) -> tuple[float, float, float, float, float, float]: ...
    def __setstate__(
        self, state: tuple[float, float, float, float, float, float], /
    ) -> None: ...
