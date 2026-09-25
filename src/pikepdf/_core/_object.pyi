# SPDX-FileCopyrightText: 2022 James R. Barlow
# SPDX-License-Identifier: MPL-2.0

# Type stubs for the bindings in src/core/object.cpp and object_methods.cpp.
# See pikepdf/_core/__init__.pyi for how this stub package is laid out.

# pylint: disable=no-method-argument,unused-argument,no-self-use,too-many-public-methods
# ruff: noqa: D418
# mypy: disable-error-code="misc"

from __future__ import annotations

from abc import abstractmethod
from collections.abc import Collection, Iterable, Iterator, KeysView, Mapping
from decimal import Decimal
from enum import Enum
from typing import TYPE_CHECKING, Any, overload

from pikepdf._core._namepath import NamePath
from pikepdf._core._object_construct import (
    Array,
    Dictionary,
    Name,
    Operator,
    Stream,
    String,
)
from pikepdf._core._qpdf import Pdf, StreamDecodeLevel
from pikepdf._core._typing import T, _Number, _NumberResult

if TYPE_CHECKING:
    from pikepdf.models.image import PdfInlineImage

class Buffer:
    """A Buffer for reading data from a PDF."""

    def __bytes__(self) -> bytes: ...
    def __len__(self) -> int: ...
    # Implements the C-level buffer protocol; declaring __buffer__ (PEP 688) lets
    # type checkers accept a Buffer wherever a read-only buffer is expected, e.g.
    # BytesIO(buffer) or memoryview(buffer).
    def __buffer__(self, flags: int, /) -> memoryview: ...

class ObjectType(Enum):
    """Enumeration of PDF object types.

    These values are used to implement
    pikepdf's instance type checking. In the vast majority of cases it is more
    pythonic to use ``isinstance(obj, pikepdf.Stream)`` or ``issubclass``.

    These values are low-level and documented for completeness. They are exposed
    through :attr:`pikepdf.Object._type_code`.
    """

    array: ...
    """A PDF array, meaning the object is a ``pikepdf.Array``."""
    boolean: ...
    """A PDF boolean. In most cases, booleans are automatically converted to
        ``bool``, so this should not appear."""
    dictionary: ...
    """A PDF dictionary, meaning the object is a ``pikepdf.Dictionary``."""
    inlineimage: ...
    """A PDF inline image, meaning the object is the data stream of an inline
        image. It would be necessary to combine this with the implicit
        dictionary to interpret the image correctly. pikepdf automatically
        packages inline images into a more useful class, so this will not
        generally appear."""
    integer: ...
    """A PDF integer. In most cases, integers are automatically converted to
        ``int``, so this should not appear. Unlike Python integers, PDF integers
        are 32-bit signed integers."""
    name_: ...
    """A PDF name, meaning the object is a ``pikepdf.Name``."""
    null: ...
    """A PDF null. In most cases, nulls are automatically converted to ``None``,
        so this should not appear."""
    operator: ...
    """A PDF operator, meaning the object is a ``pikepdf.Operator``."""
    real: ...
    """A PDF real. In most cases, reals are automatically convert to
        :class:`decimal.Decimal`."""
    reserved: ...
    """A temporary object used in creating circular references. Should not appear
        in most cases."""
    stream: ...
    """A PDF stream, meaning the object is a ``pikepdf.Stream`` (and it also
        has a dictionary)."""
    string: ...
    """A PDF string, meaning the object is a ``pikepdf.String``."""
    uninitialized: ...
    """An uninitialized object. If this appears, it is probably a bug."""

class Object:
    def _ipython_key_completions_(self) -> KeysView | None: ...
    def _inline_image_raw_bytes(self) -> bytes: ...
    def _parse_page_contents_grouped(
        self, whitelist: str
    ) -> list[tuple[Collection[Object | PdfInlineImage], Operator]]: ...
    @staticmethod
    def _parse_stream(stream: Object, parser: StreamParser) -> list:
        """Helper for parsing PDF content stream.

        Use ``pikepdf.parse_content_stream`` instead.
        """
    @staticmethod
    def _parse_stream_grouped(stream: Object, whitelist: str) -> list: ...
    def _repr_mimebundle_(self, include=None, exclude=None) -> dict | None: ...
    def _write(
        self,
        data: bytes,
        filter: Object,  # pylint: disable=redefined-builtin
        decode_parms: Object,
    ) -> None: ...
    def append(self, value: Any, /) -> None:
        """Append another object to an array; fails if the object is not an array."""
    @overload
    def as_dict(self) -> _ObjectMapping:
        """Return the dictionary's items, or return default if not a dictionary.

        For a :class:`pikepdf.Stream`, use :attr:`pikepdf.Object.stream_dict`;
        a Stream is not a dictionary here.

        Args:
            default: Value to return if this object is not a dictionary. If not
                provided and the object is not a dictionary, raises TypeError.

        Raises:
            TypeError: If object is not a dictionary and no default was provided.

        .. versionchanged:: 10.14
            Raises :exc:`TypeError` on other types, and accepts a *default*.
        """
    @overload
    def as_dict(self, default: T) -> _ObjectMapping | T: ...
    @overload
    def as_list(self) -> _ObjectList:
        """Return the array's items, or return default if not an array.

        Args:
            default: Value to return if this object is not an array. If not
                provided and the object is not an array, raises TypeError.

        Raises:
            TypeError: If object is not an array and no default was provided.

        .. versionchanged:: 10.14
            Raises :exc:`TypeError` on other types, and accepts a *default*.
        """
    @overload
    def as_list(self, default: T) -> _ObjectList | T: ...
    @overload
    def as_int(self, *, coerce: bool = False) -> int:
        """Convert to int, or return default if not an integer.

        In explicit conversion mode, this provides a safe way to convert
        pikepdf.Integer to Python int with proper type hints.

        Args:
            default: Value to return if this object is not an integer.
                If not provided and the object is not an integer,
                raises TypeError.
            coerce: If True, also accept a Real (truncated toward zero) and a
                String whose text is a number.

        Returns:
            The integer value, or the default if provided and object is
            not an integer.

        Raises:
            TypeError: If object is not an integer and no default was provided.
            OverflowError: If the value is out of range for a 64-bit integer
                and no default was provided. If a default was provided, it is
                returned instead.

        .. versionadded:: 10.1

        .. versionchanged:: 10.14
            Added the keyword-only *coerce* argument.

        .. versionchanged:: 10.14
            A value out of range for a 64-bit integer now returns *default*, if
            one was given, instead of raising OverflowError.
        """
    @overload
    def as_int(self, default: T, *, coerce: bool = False) -> int | T: ...
    @overload
    def as_bool(self, *, coerce: bool = False) -> bool:
        """Convert to bool, or return default if not a boolean.

        In explicit conversion mode, this provides a safe way to convert
        pikepdf.Boolean to Python bool with proper type hints.

        Args:
            default: Value to return if this object is not a boolean.
                If not provided and the object is not a boolean,
                raises TypeError.
            coerce: If True, also accept an Integer or Real, which are True
                when nonzero.

        Returns:
            The boolean value, or the default if provided and object is
            not a boolean.

        Raises:
            TypeError: If object is not a boolean and no default was provided.

        .. versionadded:: 10.1

        .. versionchanged:: 10.14
            Added the keyword-only *coerce* argument.
        """
    @overload
    def as_bool(self, default: T, *, coerce: bool = False) -> bool | T: ...
    @overload
    def as_float(self, *, coerce: bool = False) -> float:
        """Convert to float, or return default if not numeric.

        Works for both Integer and Real objects.

        Args:
            default: Value to return if this object is not numeric.
                If not provided and the object is not numeric,
                raises TypeError.
            coerce: If True, also accept a String whose text is a number,
                including exponential notation such as ``1e-5``.

        Returns:
            The float value, or the default if provided and object is
            not numeric.

        Raises:
            TypeError: If object is not numeric and no default was provided.

        .. versionadded:: 10.1

        .. versionchanged:: 10.14
            Added the keyword-only *coerce* argument.
        """
    @overload
    def as_float(self, default: T, *, coerce: bool = False) -> float | T: ...
    @overload
    def as_decimal(self, *, coerce: bool = False) -> Decimal:
        """Convert to Decimal, or return default if not a Real.

        Preferred over as_float() for PDF reals to preserve precision.
        Only works for Real objects, not Integer.

        Args:
            default: Value to return if this object is not a Real.
                If not provided and the object is not a Real,
                raises TypeError.
            coerce: If True, also accept an Integer and a String whose text is
                a number. The Decimal is built from the string as written, so
                all of its digits are preserved.

        Returns:
            The Decimal value, or the default if provided and object is
            not a Real.

        Raises:
            TypeError: If object is not a Real and no default was provided.

        .. versionadded:: 10.1

        .. versionchanged:: 10.14
            Added the keyword-only *coerce* argument.
        """
    @overload
    def as_decimal(self, default: T, *, coerce: bool = False) -> Decimal | T: ...
    @overload
    def as_str(self) -> str:
        """Return a String's text, or return default if not a String.

        The text is decoded as UTF-16 if the String begins with a UTF-16 byte
        order mark, and as PDFDocEncoding otherwise, exactly as ``str()`` does.
        Unlike ``str()``, which accepts any object, this raises for anything
        that is not a String, so a value of unexpected type is never silently
        rendered as text.

        Every sequence of bytes decodes as PDFDocEncoding, so binary data
        (such as a document ``/ID``) is also returned as a ``str``, without
        error. Use :meth:`as_bytes` for data that is not text.

        Args:
            default: Value to return if this object is not a String. If not
                provided and the object is not a String, raises TypeError.

        Raises:
            TypeError: If object is not a String and no default was provided.

        .. versionadded:: 10.14
        """
    @overload
    def as_str(self, default: T) -> str | T: ...
    @overload
    def as_bytes(self) -> bytes:
        """Return a String's raw bytes, or return default if not a String.

        The bytes are returned exactly as stored in the PDF, with no decoding:
        a UTF-16 String includes its byte order mark.

        Args:
            default: Value to return if this object is not a String. If not
                provided and the object is not a String, raises TypeError.

        Raises:
            TypeError: If object is not a String and no default was provided.

        .. versionadded:: 10.14
        """
    @overload
    def as_bytes(self, default: T) -> bytes | T: ...
    def copy(self) -> Object:
        """Create a shallow copy of the object."""
    def emplace(self, other: Object, retain: Iterable[Name] = ...) -> None:
        """Copy all items from other without making a new object.

        Particularly when working with pages, it may be desirable to remove all
        of the existing page's contents and emplace (insert) a new page on top
        of it, in a way that preserves all links and references to the original
        page. (Or similarly, for other Dictionary objects in a PDF.)

        Any Dictionary keys in the iterable *retain* are preserved. By default,
        /Parent is retained.

        When a page is assigned (``pdf.pages[0] = new_page``), only the
        application knows if references to the original the original page are
        still valid. For example, a PDF optimizer might restructure a page
        object into another visually similar one, and references would be valid;
        but for a program that reorganizes page contents such as a N-up
        compositor, references may not be valid anymore.

        This method takes precautions to ensure that child objects in common
        with ``self`` and ``other`` are not inadvertently deleted.

        Example:
            >>> pdf = pikepdf.Pdf.open('../tests/resources/fourpages.pdf')
            >>> pdf.pages[0].objgen
            (3, 0)
            >>> pdf.pages[0].emplace(pdf.pages[1])
            >>> pdf.pages[0].objgen
            (3, 0)
            >>> # Same object

        .. versionchanged:: 2.11.1
            Added the *retain* argument.
        """
    def extend(self, iter: Iterable[Object], /) -> None:
        """Extend a pikepdf.Array with an iterable of other pikepdf.Object."""
    def clear(self) -> None:
        """Remove all items from the array."""
    def count(self, value: Any, /) -> int:
        """Return the number of items in the array equal to *value*."""
    def index(self, value: Any, /) -> int:
        """Return the index of the first item equal to *value*."""
    def insert(self, index: int, value: Any, /) -> None:
        """Insert an object before the given index (Python list.insert semantics)."""
    def pop(self, index: int = -1, /) -> Object:
        """Remove and return the item at *index* (default last)."""
    def remove(self, value: Any, /) -> None:
        """Remove the first item in the array equal to *value*."""
    def reverse(self) -> None:
        """Reverse the elements of the array in place."""
    @overload
    def get(self, key: int | str | Name, /) -> Object | None:
        """Retrieve an attribute from the object.

        Only works if the object is a Dictionary, Array or Stream.
        """
    @overload
    def get(self, key: int | str | Name, default: T, /) -> Object | T: ...
    @overload
    def get(self, path: NamePath, /) -> Object | None:
        """Retrieve a nested value using a NamePath.

        Returns the default value if the path doesn't exist or encounters
        type mismatches (e.g., trying to traverse into a non-dict).
        """
    @overload
    def get(self, path: NamePath, default: T, /) -> Object | T: ...
    @overload
    def get_raw(self, key: str | Name, /) -> Object | None:
        """Retrieve a value without implicit conversion of scalars.

        Like :meth:`get`, except the result is always a :class:`pikepdf.Object`,
        regardless of the conversion mode in effect.

        A null stored inside an *array* comes back as a ``Null``-typed Object
        rather than ``None``. In a *dictionary*, qpdf treats a key whose value
        is null as absent, so ``get_raw`` returns the default for it, exactly
        as :meth:`get` does; ``None`` (or *default*) is likewise returned when
        the key or path does not exist at all.

        *key* may be a string, a :class:`pikepdf.Name`, or a
        :class:`pikepdf.NamePath`.

        .. versionadded:: 10.14
        """

    @overload
    def get_raw(self, key: str | Name, default: T, /) -> Object | T: ...
    @overload
    def get_raw(self, path: NamePath, /) -> Object | None: ...
    @overload
    def get_raw(self, path: NamePath, default: T, /) -> Object | T: ...
    @overload
    def get_int(
        self, key: str | Name | NamePath, *, coerce: bool = False
    ) -> int | None:
        """Get the value of *key* as a Python int.

        Returns *default* if the key is absent or its value is not an
        Integer. Unlike ``obj[key]``, the result is a Python int in both
        implicit and explicit conversion mode.

        Args:
            key: A string, :class:`pikepdf.Name` or :class:`pikepdf.NamePath`.
            default: Value to return if the key is absent or the wrong type.
            coerce: If True, also accept a Real (truncated toward zero) and a
                String whose text is a number. A coerced value that is out of
                range for a 64-bit integer yields *default*.

        .. versionadded:: 10.14
        """

    @overload
    def get_int(
        self, key: str | Name | NamePath, default: T, *, coerce: bool = False
    ) -> int | T: ...
    @overload
    def get_bool(
        self, key: str | Name | NamePath, *, coerce: bool = False
    ) -> bool | None:
        """Get the value of *key* as a Python bool.

        Returns *default* if the key is absent or its value is not a
        Boolean. Unlike ``obj[key]``, the result is a Python bool in both
        implicit and explicit conversion mode.

        Args:
            key: A string, :class:`pikepdf.Name` or :class:`pikepdf.NamePath`.
            default: Value to return if the key is absent or the wrong type.
            coerce: If True, also accept an Integer or Real, which are True
                when nonzero.

        .. versionadded:: 10.14
        """

    @overload
    def get_bool(
        self, key: str | Name | NamePath, default: T, *, coerce: bool = False
    ) -> bool | T: ...
    @overload
    def get_float(
        self, key: str | Name | NamePath, *, coerce: bool = False
    ) -> float | None:
        """Get the value of *key* as a Python float.

        Accepts both Integer and Real. Returns *default* if the key is
        absent or its value is not numeric. Unlike ``obj[key]``, the result is
        a Python float in both implicit and explicit conversion mode.

        Args:
            key: A string, :class:`pikepdf.Name` or :class:`pikepdf.NamePath`.
            default: Value to return if the key is absent or the wrong type.
            coerce: If True, also accept a String whose text is a number.

        .. versionadded:: 10.14
        """

    @overload
    def get_float(
        self, key: str | Name | NamePath, default: T, *, coerce: bool = False
    ) -> float | T: ...
    @overload
    def get_decimal(
        self, key: str | Name | NamePath, *, coerce: bool = False
    ) -> Decimal | None:
        """Get the value of *key* as a Python :class:`decimal.Decimal`.

        Preferred over :meth:`get_float` for PDF reals, since it preserves the
        digits as written. Returns *default* if the key is absent or its
        value is not a Real. Unlike ``obj[key]``, the result is a Decimal in
        both implicit and explicit conversion mode.

        Args:
            key: A string, :class:`pikepdf.Name` or :class:`pikepdf.NamePath`.
            default: Value to return if the key is absent or the wrong type.
            coerce: If True, also accept an Integer and a String whose text is
                a number.

        .. versionadded:: 10.14
        """

    @overload
    def get_decimal(
        self, key: str | Name | NamePath, default: T, *, coerce: bool = False
    ) -> Decimal | T: ...
    @overload
    def get_dict(self, key: str | Name | NamePath) -> _ObjectMapping | None:
        """Get the value of *key* as a mapping of its dictionary entries.

        Returns *default* if the key is absent or its value is not a
        Dictionary. A Stream is not a Dictionary here; use
        :attr:`pikepdf.Object.stream_dict`.

        Args:
            key: A string, :class:`pikepdf.Name` or :class:`pikepdf.NamePath`.
            default: Value to return if the key is absent or the wrong type.

        .. versionadded:: 10.14
        """

    @overload
    def get_dict(
        self, key: str | Name | NamePath, default: T
    ) -> _ObjectMapping | T: ...
    @overload
    def get_list(self, key: str | Name | NamePath) -> _ObjectList | None:
        """Get the value of *key* as a sequence of its array items.

        Returns *default* if the key is absent or its value is not an Array.

        Args:
            key: A string, :class:`pikepdf.Name` or :class:`pikepdf.NamePath`.
            default: Value to return if the key is absent or the wrong type.

        .. versionadded:: 10.14
        """

    @overload
    def get_list(self, key: str | Name | NamePath, default: T) -> _ObjectList | T: ...
    @overload
    def get_str(self, key: str | Name | NamePath) -> str | None:
        """Get the value of *key* as the text of a String.

        Returns *default* if the key is absent or its value is not a String.
        See :meth:`as_str` for how the text is decoded.

        Args:
            key: A string, :class:`pikepdf.Name` or :class:`pikepdf.NamePath`.
            default: Value to return if the key is absent or the wrong type.

        .. versionadded:: 10.14
        """

    @overload
    def get_str(self, key: str | Name | NamePath, default: T) -> str | T: ...
    @overload
    def get_bytes(self, key: str | Name | NamePath) -> bytes | None:
        """Get the value of *key* as the raw bytes of a String.

        Returns *default* if the key is absent or its value is not a String.

        Args:
            key: A string, :class:`pikepdf.Name` or :class:`pikepdf.NamePath`.
            default: Value to return if the key is absent or the wrong type.

        .. versionadded:: 10.14
        """

    @overload
    def get_bytes(self, key: str | Name | NamePath, default: T) -> bytes | T: ...
    def get_raw_stream_buffer(self) -> Buffer:
        """Return a buffer protocol buffer describing the raw, encoded stream."""
    def get_stream_buffer(self, decode_level: StreamDecodeLevel = ...) -> Buffer:
        """Return a buffer protocol buffer describing the decoded stream."""
    def is_owned_by(self, possible_owner: Pdf) -> bool:
        """Test if this object is owned by the indicated *possible_owner*."""
    def items(self) -> Iterable[tuple[str, Object]]: ...
    def values(self) -> Iterable[Object]: ...
    def keys(self) -> set[str]:
        """Get the keys of the object, if it is a Dictionary or Stream."""
    @staticmethod
    def parse(stream: bytes, description: str = ...) -> Object:
        """Parse PDF binary representation into PDF objects."""
    def read_bytes(self, decode_level: StreamDecodeLevel = ...) -> bytes:
        """Decode and read the content stream associated with this object."""
    def read_raw_bytes(self) -> bytes:
        """Read the content stream associated with a Stream, without decoding."""
    def same_owner_as(self, other: Object) -> bool:
        """Test if two objects are owned by the same :class:`pikepdf.Pdf`."""
    def to_json(self, dereference: bool = ..., schema_version: int = ...) -> bytes:
        r"""Convert to a qpdf JSON representation of the object.

        See the qpdf manual for a description of its JSON representation.
        https://qpdf.readthedocs.io/en/stable/json.html#qpdf-json-format

        Not necessarily compatible with other PDF-JSON representations that
        exist in the wild.

        * Names are encoded as UTF-8 strings
        * Indirect references are encoded as strings containing ``obj gen R``
        * Strings are encoded as UTF-8 strings with unrepresentable binary
            characters encoded as ``\uHHHH``
        * Encoding streams just encodes the stream's dictionary; the stream
            data is not represented
        * Object types that are only valid in content streams (inline
            image, operator) as well as "reserved" objects are not
            representable and will be serialized as ``null``.

        Args:
            dereference (bool): If True, dereference the object if this is an
                indirect object.
            schema_version (int): The version of the JSON schema. Defaults to 2.

        Returns:
            JSON bytestring of object. The object is UTF-8 encoded
            and may be decoded to a Python str that represents the binary
            values ``\x00-\xFF`` as ``U+0000`` to ``U+00FF``; that is,
            it may contain mojibake.

        .. versionchanged:: 6.0
            Added *schema_version*.
        """
    def unparse(self, resolved: bool = ...) -> bytes:
        """Convert PDF objects into their binary representation.

        Set resolved=True to deference indirect objects where possible.

        If you want to unparse content streams, which are a collection of
        objects that need special treatment, use
        :func:`pikepdf.unparse_content_stream` instead.

        Returns ``bytes()`` that can be used with :meth:`Object.parse`
        to reconstruct the ``pikepdf.Object``. If reconstruction is not possible,
        a relative object reference is returned, such as ``4 0 R``.

        Args:
            resolved: If True, deference indirect objects where possible.
        """
    def update(self, other: Mapping[Any, Any] | Object) -> None:
        """Update the dictionary with key/value pairs from another dictionary.

        *other* may be a Python mapping or another pikepdf Dictionary.
        """
    def with_same_owner_as(self, arg0: Object) -> Object:
        """Returns an object that is owned by the same Pdf that owns *other* object.

        If the objects already have the same owner, this object is returned.
        If the *other* object has a different owner, then a copy is created
        that is owned by *other*'s owner. If this object is a direct object
        (no owner), then an indirect object is created that is owned by
        *other*. An exception is thrown if *other* is a direct object.
        As with :meth:`pikepdf.Pdf.make_indirect`, a direct scalar is copied
        before it is made indirect, so this object is left unchanged.

        This method may be convenient when a reference to the Pdf is not
        available.

        .. versionadded:: 2.14

        .. versionchanged:: 10.14
            Direct scalars are copied rather than made indirect in place.
        """
    def wrap_in_array(self) -> Array:
        """Return the object wrapped in an array if not already an array."""
    def write(
        self,
        data: bytes,
        *,
        filter: Name | Array | list[Name] | None = ...,  # pylint: disable=redefined-builtin
        decode_parms: Dictionary | Array | None = ...,
        type_check: bool = ...,
    ) -> None:
        """Replace stream object's data with new (possibly compressed) `data`.

        `filter` and `decode_parms` describe any compression that is already
        present on the input `data`. For example, if your data is already
        compressed with the Deflate algorithm, you would set
        ``filter=Name.FlateDecode``.

        When writing the PDF in :meth:`pikepdf.Pdf.save`,
        pikepdf may change the compression or apply compression to data that was
        not compressed, depending on the parameters given to that function. It
        will never change lossless to lossy encoding.

        PNG and TIFF images, even if compressed, cannot be directly inserted
        into a PDF and displayed as images.

        Args:
            data: the new data to use for replacement
            filter: The filter(s) with which the
                data is (already) encoded
            decode_parms: Parameters for the
                filters with which the object is encode
            type_check: Check arguments; use False only if you want to
                intentionally create malformed PDFs.

        If only one `filter` is specified, it may be a name such as
        `Name('/FlateDecode')`. If there are multiple filters, then array
        of names should be given.

        If there is only one filter, `decode_parms` is a Dictionary of
        parameters for that filter. If there are multiple filters, then
        `decode_parms` is an Array of Dictionary, where each array index
        is corresponds to the filter.
        """
    def __bool__(self) -> bool: ...
    def __bytes__(self) -> bytes: ...
    @overload
    def __contains__(self, obj: Object | str, /) -> bool: ...
    @overload
    def __contains__(self, path: NamePath, /) -> bool: ...
    def __copy__(self) -> Object: ...
    def __delattr__(self, name: str, /) -> None: ...
    @overload
    def __delitem__(self, name: str | Name | int, /) -> None: ...
    @overload
    def __delitem__(self, path: NamePath, /) -> None: ...
    @overload
    def __delitem__(self, index: slice, /) -> None: ...
    def __dir__(self) -> list: ...
    def __eq__(self, other: Any, /) -> bool: ...
    def __float__(self) -> float: ...
    def __index__(self) -> int: ...
    def __getattr__(self, name: str, /) -> Object: ...
    @overload
    def __getitem__(self, name: str | Name | int, /) -> Object: ...
    @overload
    def __getitem__(self, path: NamePath, /) -> Object: ...
    @overload
    def __getitem__(self, index: slice, /) -> Object: ...
    def __hash__(self) -> int: ...
    def __int__(self) -> int: ...
    def __add__(self, other: _Number, /) -> _NumberResult: ...
    def __radd__(self, other: _Number, /) -> _NumberResult: ...
    def __sub__(self, other: _Number, /) -> _NumberResult: ...
    def __rsub__(self, other: _Number, /) -> _NumberResult: ...
    def __mul__(self, other: _Number, /) -> _NumberResult: ...
    def __rmul__(self, other: _Number, /) -> _NumberResult: ...
    def __truediv__(self, other: _Number, /) -> float | Decimal: ...
    def __rtruediv__(self, other: _Number, /) -> float | Decimal: ...
    def __floordiv__(self, other: _Number, /) -> _NumberResult: ...
    def __rfloordiv__(self, other: _Number, /) -> _NumberResult: ...
    def __mod__(self, other: _Number, /) -> _NumberResult: ...
    def __rmod__(self, other: _Number, /) -> _NumberResult: ...
    def __pow__(self, other: _Number, /) -> _NumberResult: ...
    def __rpow__(self, other: _Number, /) -> _NumberResult: ...
    def __neg__(self) -> int | Decimal: ...
    def __pos__(self) -> int | Decimal: ...
    def __abs__(self) -> int | Decimal: ...
    def __lt__(self, other: _Number, /) -> bool: ...
    def __le__(self, other: _Number, /) -> bool: ...
    def __gt__(self, other: _Number, /) -> bool: ...
    def __ge__(self, other: _Number, /) -> bool: ...
    def __iter__(self) -> Iterator[Object]: ...
    def __len__(self) -> int: ...
    def __setattr__(self, name: str, value: Any, /) -> None: ...
    @overload
    def __setitem__(self, name: str | Name | int, value: Any, /) -> None: ...
    @overload
    def __setitem__(self, path: NamePath, value: Any, /) -> None: ...
    @overload
    def __setitem__(self, index: slice, value: Iterable[Any], /) -> None: ...
    @property
    def _objgen(self) -> tuple[int, int]: ...
    @property
    def _type_code(self) -> ObjectType: ...
    @property
    def _type_code_int(self) -> int: ...
    @property
    def _type_name(self) -> str: ...
    @property
    def images(self) -> _ObjectMapping: ...
    @property
    def is_indirect(self) -> bool:
        """Returns True if the object is an indirect object."""
    @property
    def is_rectangle(self) -> bool:
        """Returns True if the object is a rectangle (an array of 4 numbers)."""
    @property
    def objgen(self) -> tuple[int, int]:
        """Return the object-generation number pair for this object.

        If this is a direct object, then the returned value is ``(0, 0)``.
        By definition, if this is an indirect object, it has a "objgen",
        and can be looked up using this in the cross-reference (xref) table.
        Direct objects cannot necessarily be looked up.

        The generation number is usually 0, except for PDFs that have been
        incrementally updated. Incrementally updated PDFs are now uncommon,
        since it does not take too long for modern CPUs to reconstruct an
        entire PDF. pikepdf will consolidate all incremental updates
        when saving.
        """
    @property
    def stream_dict(self) -> Dictionary:
        """Access the dictionary key-values for a :class:`pikepdf.Stream`."""
    @stream_dict.setter
    def stream_dict(self, val: Dictionary) -> None: ...

# The classes below are facade types for constructing and type-checking PDF
# objects. At runtime they are implemented in C++ (pikepdf._core) and re-exported
# by pikepdf.objects. They do not truly inherit from Object at runtime (a custom
# metaclass overrides __instancecheck__), but for type-checking purposes they are
# declared as Object subclasses so that the type checker knows about __getattr__,
# __getitem__, __contains__, and the rest of the Object interface.

class ObjectHelper:
    """Base class for wrapper/helper around an Object.

    Used to expose additional functionality specific to that object type.

    :class:`pikepdf.Page` is an example of an object helper. The actual
    page object is a PDF is a Dictionary. The helper provides additional
    methods specific to pages.
    """

    def __eq__(self, other: Any, /) -> bool: ...
    @property
    def obj(self) -> Dictionary:
        """Get the underlying PDF object (typically a Dictionary)."""

class _ObjectList:
    """A list whose elements are always pikepdf.Object.

    Values are encoded to pikepdf.Object on the way in, and numeric objects
    are decoded to int/bool/Decimal on the way out, so the methods below
    accept any value that pikepdf can encode. In all other respects, this
    object behaves like a standard Python list.
    """

    @overload
    def __init__(self) -> None: ...
    @overload
    def __init__(self, arg0: _ObjectList, /) -> None: ...
    @overload
    def __init__(self, arg0: Iterable, /) -> None: ...
    @overload
    def __init__(*args, **kwargs) -> None: ...
    def append(self, value: Any, /) -> None: ...
    def clear(self) -> None: ...
    def count(self, value: Any, /) -> int: ...
    @overload
    def extend(self, L: _ObjectList, /) -> None: ...
    @overload
    def extend(self, L: Iterable[Any], /) -> None: ...
    def insert(self, index: int, value: Any, /) -> None: ...
    @overload
    def pop(self) -> Object: ...
    @overload
    def pop(self, i: int, /) -> Object: ...
    def remove(self, value: Any, /) -> None: ...
    def __bool__(self) -> bool: ...
    def __contains__(self, value: Any, /) -> bool: ...
    @overload
    def __delitem__(self, arg0: int, /) -> None: ...
    @overload
    def __delitem__(self, arg0: slice, /) -> None: ...
    def __eq__(self, other: Any, /) -> bool: ...
    @overload
    def __getitem__(self, s: slice, /) -> _ObjectList: ...
    @overload
    def __getitem__(self, arg0: int, /) -> Object: ...
    def __iter__(self) -> Iterator[Object]: ...
    def __len__(self) -> int: ...
    def __ne__(self, other: Any, /) -> bool: ...
    @overload
    def __setitem__(self, arg0: int, arg1: Any, /) -> None: ...
    @overload
    def __setitem__(self, arg0: slice, arg1: _ObjectList, /) -> None: ...
    @overload
    def __setitem__(self, arg0: slice, arg1: Iterable[Any], /) -> None: ...

class _ObjectMapping:
    """A mapping whose keys and values are always pikepdf.Name and pikepdf.Object.

    Values are encoded to pikepdf.Object on the way in, and numeric objects are
    decoded to int/bool/Decimal on the way out, so the methods below accept any
    value that pikepdf can encode.
    """

    @overload
    def get(self, key: Name | str) -> Object | None: ...
    @overload
    def get(self, key: Name | str, default: T) -> Object | T: ...
    def keys(self) -> Iterator[Name]: ...
    def values(self) -> Iterator[Object]: ...
    def clear(self) -> None: ...
    def update(self, other: _ObjectMapping | dict[Name | str, Any], /) -> None: ...
    def __contains__(self, key: Name | str, /) -> bool: ...
    def __init__(self) -> None: ...
    def items(self) -> Iterator: ...
    def __bool__(self) -> bool: ...
    def __delitem__(self, key: Name | str, /) -> None: ...
    def __eq__(self, other: Any, /) -> bool: ...
    def __getitem__(self, key: Name | str, /) -> Object: ...
    def __iter__(self) -> Iterator: ...
    def __len__(self) -> int: ...
    def __ne__(self, other: Any, /) -> bool: ...
    def __setitem__(self, key: Name | str, value: Any, /) -> None: ...

class StreamParser:
    """A simple content stream parser, which must be subclassed to be used.

    Pass an instance of a subclass to :meth:`pikepdf.Page.parse_contents`,
    which calls :meth:`handle_object` once per object parsed from the
    content stream. Because objects are handled one at a time, the content
    stream is never materialized as a list of instructions, so memory use
    stays bounded regardless of stream length.

    In practice, the performance of this class may be quite poor on long
    content streams because it creates objects and involves multiple
    function calls for every object in a content stream, some of which
    may be only a single byte long.

    Consider instead using :func:`pikepdf.parse_content_stream`.
    """

    def __init__(self) -> None:
        """You must call ``super().__init__()`` in subclasses."""
    @abstractmethod
    def handle_eof(self) -> None:
        """An abstract method that may be overloaded in a subclass.

        Called at the end of a content stream.
        """
    @abstractmethod
    def handle_object(self, obj: Object, offset: int, length: int) -> None:
        """An abstract method that must be overloaded in a subclass.

        This function will be called back once for each object that is
        parsed in the content stream.
        """

def _Null() -> Any:
    """Construct a PDF Null object."""

def _encode(handle: Any) -> Object: ...
def _new_array(arg0: Iterable) -> Array:
    """Low-level function to construct a PDF Array.

    Construct a PDF Array object from an iterable of PDF objects or types
    that can be coerced to PDF objects.
    """

def _new_boolean(arg0: bool) -> Object:
    """Low-level function to construct a PDF Boolean.

    pikepdf automatically converts PDF booleans to Python booleans and
    vice versa. This function serves no purpose other than to test
    that functionality.
    """

def _new_dictionary(arg0: Mapping[Any, Any]) -> Dictionary:
    """Low-level function to construct a PDF Dictionary.

    Construct a PDF Dictionary from a mapping of PDF objects or Python types
    that can be coerced to PDF objects."
    """

def _new_integer(arg0: int) -> int:
    """Low-level function to construct a PDF Integer.

    pikepdf automatically converts PDF integers to Python integers and
    vice versa. This function serves no purpose other than to test
    that functionality.
    """

def _new_name(s: str | bytes) -> Name:
    """Low-level function to construct a PDF Name.

    Must begin with '/'. Certain characters are escaped according to
    the PDF specification.
    """

def _new_operator(op: str) -> Operator:
    """Low-level function to construct a PDF Operator."""

@overload
def _new_real(s: str) -> Decimal:  # noqa: D418
    """Low-level function to construct a PDF Real.

    pikepdf automatically PDF real numbers to Python Decimals.
    This function serves no purpose other than to test that
    functionality.
    """

@overload
def _new_real(value: float, places: int = ...) -> Decimal:  # noqa: D418
    """Low-level function to construct a PDF Real.

    pikepdf automatically PDF real numbers to Python Decimals.
    This function serves no purpose other than to test that
    functionality.
    """

def _new_stream(owner: Pdf, data: bytes) -> Stream:
    """Low-level function to construct a PDF Stream.

    Construct a PDF Stream object from binary data.
    """

def _new_string(s: str | bytes) -> String:
    """Low-level function to construct a PDF String object."""

def _new_string_utf8(s: str) -> String:
    """Low-level function to construct a PDF String object from UTF-8 bytes."""

def unparse(obj: Any) -> bytes: ...

# Module-level typed conversions, defined in object_methods.cpp. Each is the
# value-side twin of an Object.as_*(default) method and Object.get_*() getter:
# it takes any Python value, so a value read in implicit mode (a native int,
# bool or Decimal) and the same value read in explicit mode (an Object) give
# the same answer.

@overload
def as_int(value: Any, default: None = None, *, coerce: bool = False) -> int | None:
    """Return *value* as a Python int, or *default* if it is not an integer.

    The value-side twin of :meth:`Object.get_int`, for a value already in
    hand -- an array element, a content stream operand, a value from
    ``.items()``, or a parameter of unknown provenance -- that may have been
    read in either conversion mode.

    A :class:`pikepdf.Object` is converted exactly as
    ``value.as_int(default, coerce=coerce)`` would. A native Python value is
    accepted if it is the type implicit conversion would have produced for a
    PDF Integer, that is an ``int``. ``bool`` is *not* accepted, although it
    is a subclass of ``int``, because implicit mode produces ``bool`` for a
    PDF Boolean, and a Boolean is not an Integer. ``None`` and any other value
    give *default*.

    Args:
        value: Any Python value.
        default: Returned, by identity, when *value* is not an integer.
        coerce: If True, apply the same coercions as
            :meth:`Object.as_int`, treating a native ``float`` or
            :class:`decimal.Decimal` as a Real (truncated toward zero) and a
            native ``str`` or ``bytes`` as a String whose text may be a number.
            ``bool`` is still not accepted.

    An ``int`` or coerced value out of range for a 64-bit PDF integer gives
    *default*.

    Example:
        >>> [pikepdf.as_int(v, 0) for v in pikepdf.Array([1, True, 2.5])]
        [1, 0, 0]

    .. versionadded:: 10.14
    """

@overload
def as_int(value: Any, default: T, *, coerce: bool = False) -> int | T: ...
@overload
def as_bool(value: Any, default: None = None, *, coerce: bool = False) -> bool | None:
    """Return *value* as a Python bool, or *default* if it is not a boolean.

    The value-side twin of :meth:`Object.get_bool`. A
    :class:`pikepdf.Object` is converted exactly as
    ``value.as_bool(default, coerce=coerce)`` would. A native Python value is
    accepted if it is the type implicit conversion would have produced for a
    PDF Boolean, that is a ``bool``. ``None`` and any other value give
    *default*.

    Args:
        value: Any Python value.
        default: Returned, by identity, when *value* is not a boolean.
        coerce: If True, also accept a number -- an Integer or Real, or a
            native ``int``, ``float`` or :class:`decimal.Decimal` -- which is
            True when nonzero, as :meth:`Object.as_bool` does.

    .. versionadded:: 10.14
    """

@overload
def as_bool(value: Any, default: T, *, coerce: bool = False) -> bool | T: ...
@overload
def as_float(value: Any, default: None = None, *, coerce: bool = False) -> float | None:
    """Return *value* as a Python float, or *default* if it is not numeric.

    The value-side twin of :meth:`Object.get_float`. A
    :class:`pikepdf.Object` is converted exactly as
    ``value.as_float(default, coerce=coerce)`` would, accepting Integer and
    Real. A native Python value is accepted if it is a type implicit
    conversion would have produced for a PDF number -- ``int`` for an Integer,
    :class:`decimal.Decimal` for a Real -- or a ``float``, which pikepdf
    writes as a Real. ``bool`` is not accepted, because implicit mode
    produces it for a PDF Boolean. A non-finite ``float`` or ``Decimal`` gives
    *default*, as does ``None`` and any other value.

    Args:
        value: Any Python value.
        default: Returned, by identity, when *value* is not numeric.
        coerce: If True, also accept a String, or a native ``str`` or
            ``bytes``, whose text is a number, as :meth:`Object.as_float`
            does.

    .. versionadded:: 10.14
    """

@overload
def as_float(value: Any, default: T, *, coerce: bool = False) -> float | T: ...
@overload
def as_decimal(
    value: Any, default: None = None, *, coerce: bool = False
) -> Decimal | None:
    """Return *value* as a :class:`decimal.Decimal`, or *default* if not a Real.

    The value-side twin of :meth:`Object.get_decimal`. A
    :class:`pikepdf.Object` is converted exactly as
    ``value.as_decimal(default, coerce=coerce)`` would, which accepts only a
    Real unless *coerce* is given. A native Python value is accepted if it is
    the type implicit conversion would have produced for a PDF Real, that is a
    ``Decimal`` (returned with every digit), or a ``float``, which pikepdf
    writes as a Real and which is converted by its shortest ``repr``. An
    ``int`` gives *default*, as an Integer does, because implicit mode
    produces ``int`` for a PDF Integer. A non-finite ``float`` or ``Decimal``
    gives *default*, as does ``bool``, ``None`` and any other value.

    Args:
        value: Any Python value.
        default: Returned, by identity, when *value* is not a Real.
        coerce: If True, also accept an Integer or native ``int``, and a
            String, or a native ``str`` or ``bytes``, whose text is a number,
            as :meth:`Object.as_decimal` does.

    .. versionadded:: 10.14
    """

@overload
def as_decimal(value: Any, default: T, *, coerce: bool = False) -> Decimal | T: ...
@overload
def as_dict(value: Any, default: None = None) -> _ObjectMapping | None:
    """Return a Dictionary's contents as a mapping, or *default*.

    The value-side twin of :meth:`Object.get_dict`. A
    :class:`pikepdf.Dictionary` is converted exactly as
    ``value.as_dict(default)`` would. Implicit conversion never produces a
    native ``dict`` for a PDF object, so a native ``dict`` gives *default*,
    as does a Stream (use ``stream.stream_dict``), ``None`` and any other
    value.

    Args:
        value: Any Python value.
        default: Returned, by identity, when *value* is not a Dictionary.

    .. versionadded:: 10.14
    """

@overload
def as_dict(value: Any, default: T) -> _ObjectMapping | T: ...
@overload
def as_list(value: Any, default: None = None) -> _ObjectList | None:
    """Return an Array's items as a list, or *default*.

    The value-side twin of :meth:`Object.get_list`. A
    :class:`pikepdf.Array` is converted exactly as ``value.as_list(default)``
    would. Implicit conversion never produces a native ``list`` for a PDF
    object, so a native ``list`` gives *default*, as does ``None`` and any
    other value.

    Args:
        value: Any Python value.
        default: Returned, by identity, when *value* is not an Array.

    .. versionadded:: 10.14
    """

@overload
def as_list(value: Any, default: T) -> _ObjectList | T: ...
@overload
def as_str(value: Any, default: None = None) -> str | None:
    """Return a String's text, or *default* if *value* is not a String.

    The value-side twin of :meth:`Object.get_str`. A
    :class:`pikepdf.String` is decoded exactly as ``value.as_str(default)``
    would. Implicit conversion returns a String as a :class:`pikepdf.String`
    in both modes, so the only native value accepted is a ``str``, which is
    already the text and is returned as is. A native ``bytes`` gives
    *default*: which encoding it holds is unknown. So do a
    :class:`pikepdf.Name`, ``None`` and any other value.

    Args:
        value: Any Python value.
        default: Returned, by identity, when *value* is not a String.

    .. versionadded:: 10.14
    """

@overload
def as_str(value: Any, default: T) -> str | T: ...
@overload
def as_bytes(value: Any, default: None = None) -> bytes | None:
    """Return a String's raw bytes, or *default* if *value* is not a String.

    The value-side twin of :meth:`Object.get_bytes`. A
    :class:`pikepdf.String` is converted exactly as
    ``value.as_bytes(default)`` would. Implicit conversion returns a String as
    a :class:`pikepdf.String` in both modes, so the only native value accepted
    is a ``bytes``, which is already the data and is returned as is. A native
    ``str`` gives *default*: which encoding to apply is unknown. So do
    ``None`` and any other value.

    Args:
        value: Any Python value.
        default: Returned, by identity, when *value* is not a String.

    .. versionadded:: 10.14
    """

@overload
def as_bytes(value: Any, default: T) -> bytes | T: ...
