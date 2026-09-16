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

        If you are inserting a new name into a PDF (for example, a name for a
        new image), you can use this function to generate a cryptographically
        strong random name that is almost certainly not already in the PDF, and
        not colliding with other existing names.

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
    """Construct a PDF Dictionary object.

    Works from either a Python ``dict`` or keyword arguments.

    These two examples are equivalent:

    .. code-block:: python

        pikepdf.Dictionary({'/NameOne': 1, '/NameTwo': 'Two'})

        pikepdf.Dictionary(NameOne=1, NameTwo='Two')

    In either case, the keys must be strings, and the strings
    correspond to the desired Names in the PDF Dictionary. The values
    must all be convertible to `pikepdf.Object`.
    """

    object_type: ObjectType
    def __new__(cls, d: Mapping | None = None, **kwargs: Any) -> Dictionary: ...

class Stream(Object):
    """Construct a PDF Stream object.

    Streams stores arbitrary binary data and may or may not be compressed.
    It also may or may not be a page or Form XObject's content stream.

    A stream dictionary is like a pikepdf.Dictionary or Python dict, except
    it has a binary payload of data attached. The dictionary describes
    how the data is compressed or encoded.

    The dictionary may be initialized just like pikepdf.Dictionary is initialized,
    using a mapping object or keyword arguments.

    Args:
        owner: The Pdf to which this stream shall be attached.
        data: The data bytes for the stream.
        d: An optional mapping object that will be used to construct the stream's
            dictionary.
        kwargs: Keyword arguments that will define the stream dictionary. Do not set
            /Length here as pikepdf will manage this value. Set /Filter
            if the data is already encoded in some format.

    Examples:
        Using kwargs:
            >>> pdf = pikepdf.Pdf.new()
            >>> s1 = pikepdf.Stream(
            ...     pdf,
            ...     b"uncompressed image data",
            ...     BitsPerComponent=8,
            ...     ColorSpace=pikepdf.Name.DeviceRGB,
            ... )
        Using dict:
            >>> pdf = pikepdf.Pdf.new()
            >>> d = pikepdf.Dictionary(Key1=1, Key2=2)
            >>> s2 = pikepdf.Stream(
            ...     pdf,
            ...     b"data",
            ...     d
            ... )

    .. versionchanged:: 2.2
        Support creation of ``pikepdf.Stream`` from existing dictionary.

    .. versionchanged:: 3.0
        ``obj`` argument was removed; use ``data``.
    """

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
