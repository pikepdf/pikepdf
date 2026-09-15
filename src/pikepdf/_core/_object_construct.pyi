# SPDX-FileCopyrightText: 2022 James R. Barlow
# SPDX-License-Identifier: MPL-2.0

# Type stubs for the bindings in src/core/object_construct.cpp.
# See pikepdf/_core/__init__.pyi for how this stub package is laid out.

# pylint: disable=no-method-argument,unused-argument,no-self-use,too-many-public-methods
# ruff: noqa: D418
# mypy: disable-error-code="misc"

from __future__ import annotations

from collections.abc import Iterable, Mapping
from decimal import Decimal
from typing import Any

from pikepdf._core._matrix import Matrix
from pikepdf._core._object import Object, ObjectType
from pikepdf._core._qpdf import Pdf
from pikepdf._core._rectangle import Rectangle

class _ObjectMeta(type):
    object_type: ObjectType

class _NameObjectMeta(_ObjectMeta):
    def __getattr__(cls, attr: str) -> Name: ...

class Name(Object, metaclass=_NameObjectMeta):
    """Construct a PDF Name object.

    Names can be constructed with two notations:

        1. ``Name.Resources``

        2. ``Name('/Resources')``

    The two are semantically equivalent. The former is preferred for names
    that are normally expected to be in a PDF. The latter is preferred for
    dynamic names and attributes.
    """

    object_type: ObjectType
    def __new__(cls, name: str | Name) -> Name: ...
    @classmethod
    def random(cls, len_: int = 16, prefix: str = '') -> Name:
        """Generate a cryptographically strong, random, valid PDF Name.

        If you are inserting a new name into a PDF (for example,
        name for a new image), you can use this function to generate a
        cryptographically strong random name that is almost certainly already
        not already in the PDF, and not colliding with other existing names.

        This function uses Python's secrets.token_urlsafe, which returns a
        URL-safe encoded random number of the desired length. An optional
        *prefix* may be prepended. (The encoding is ultimately done with
        :func:`base64.urlsafe_b64encode`.) Serendipitously, URL-safe is also
        PDF-safe.

        When the length parameter is 16 (16 random bytes or 128 bits), the result
        is probably globally unique and can be treated as never colliding with
        other names.

        The length of the returned string may vary because it is encoded,
        but will always have ``8 * len_`` random bits.

        Args:
            len_: The length of the random string.
            prefix: A prefix to prepend to the random string.
        """

class Operator(Object):
    """Construct an operator for use in a content stream.

    An Operator is one of a limited set of commands that can appear in PDF content
    streams (roughly the mini-language that draws objects, lines and text on a
    virtual PDF canvas). The commands :func:`parse_content_stream` and
    :func:`unparse_content_stream` create and expect Operators respectively, along
    with their operands.

    pikepdf uses the special Operator "INLINE IMAGE" to denote an inline image
    in a content stream.
    """

    object_type: ObjectType
    def __new__(cls, name: str) -> Operator: ...

class String(Object):
    """Construct a PDF String object."""

    object_type: ObjectType
    def __new__(cls, s: str | bytes) -> String: ...

class Array(Object):
    """Construct a PDF Array object."""

    object_type: ObjectType
    def __new__(cls, a: Iterable | Rectangle | Matrix | None = None) -> Array: ...

class Dictionary(Object):
    """Construct a PDF Dictionary object."""

    object_type: ObjectType
    def __new__(cls, d: Mapping | None = None, **kwargs: Any) -> Dictionary: ...

class Stream(Object):
    """Construct a PDF Stream object."""

    object_type: ObjectType
    def __new__(
        cls, owner: Pdf, data: bytes | None = None, d: Any = None, **kwargs: Any
    ) -> Stream: ...

class Integer(Object):
    """A PDF integer object.

    In explicit conversion mode, PDF integers are returned as this type instead
    of being automatically converted to Python ``int``.

    Supports ``int()`` conversion, indexing operations (via ``__index__``),
    arithmetic, and ordering comparisons (``<``, ``<=``, ``>``, ``>=``)
    against Python ``int``, ``float``, ``bool``, ``Decimal``, ``Integer`` and
    ``Real``. Arithmetic returns a native Python number, never a pikepdf
    object: ``int`` with an ``int``, ``bool`` or ``Integer`` operand,
    ``float`` with a ``float``, and ``Decimal`` with a ``Decimal`` or
    ``Real``. A number computed from a document is not itself in the
    document, so there is nothing to box; assign the result to a dictionary
    or array to store it.

    .. versionadded:: 10.1
    .. versionchanged:: 10.14
        Added ordering comparisons, and arithmetic with ``Integer``, ``Real``,
        ``Decimal`` and ``bool`` operands.
    """

    object_type: ObjectType
    def __new__(cls, val: int | Integer) -> Integer: ...

class Boolean(Object):
    """A PDF boolean object.

    In explicit conversion mode, PDF booleans are returned as this type instead
    of being automatically converted to Python ``bool``.

    Supports ``bool()`` conversion via ``__bool__``.

    .. versionadded:: 10.1
    """

    object_type: ObjectType
    def __new__(cls, val: bool | Boolean) -> Boolean: ...

class Real(Object):
    """A PDF real (floating-point) object.

    In explicit conversion mode, PDF reals are returned as this type instead
    of being automatically converted to Python ``Decimal``.

    Supports ``float()`` conversion, arithmetic, and ordering comparisons
    (``<``, ``<=``, ``>``, ``>=``) against Python ``int``, ``float``,
    ``bool``, ``Decimal``, ``Integer`` and ``Real``. Arithmetic and
    comparisons use the exact decimal value of the PDF token, as
    ``as_decimal()`` returns it, and arithmetic returns a native Python
    number, never a pikepdf object: a ``Decimal``, except with a ``float``
    operand, which ``Decimal`` would refuse, where the result is a ``float``.
    Use ``as_decimal()`` for lossless conversion.

    .. versionadded:: 10.1
    .. versionchanged:: 10.14
        Added ordering comparisons, and arithmetic with ``Integer``, ``Real``,
        ``Decimal``, ``int`` and ``bool`` operands.
    """

    object_type: ObjectType
    def __new__(cls, val: float | Decimal | Real, places: int = 6) -> Real: ...
