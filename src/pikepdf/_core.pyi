# SPDX-FileCopyrightText: 2022 James R. Barlow
# SPDX-License-Identifier: MPL-2.0

from __future__ import annotations

# pybind11 does not generate type annotations yet, and mypy doesn't understand
# the way we're augmenting C++ classes with Python methods as in
# pikepdf/_methods.py. Thus, we need to manually spell out the resulting types
# after augmenting.
import datetime
from abc import abstractmethod
from decimal import Decimal
from enum import Enum
from pathlib import Path
from typing import (
    TYPE_CHECKING,
    Any,
    BinaryIO,
    Callable,
    ClassVar,
    Collection,
    Iterable,
    Iterator,
    KeysView,
    Literal,
    Mapping,
    MutableMapping,
    Sequence,
    TypeVar,
    overload,
)

if TYPE_CHECKING:
    import numpy as np

    from pikepdf.models.encryption import Encryption, EncryptionInfo, Permissions
    from pikepdf.models.image import PdfInlineImage
    from pikepdf.models.metadata import PdfMetadata
    from pikepdf.models.outlines import Outline
    from pikepdf.objects import Array, Dictionary, Name, Stream, String

# This is the whole point of stub files, but apparently we have to do this...
# pylint: disable=no-method-argument,unused-argument,no-self-use,too-many-public-methods

# Rule: Function decorated with `@overload` shouldn't contain a docstring
# ruff: noqa: D418
# Seems to be no alternative for the moment.

# mypy: disable-error-code="misc"

T = TypeVar('T', bound='Object')
Numeric = TypeVar('Numeric', int, float, Decimal)

class Buffer: ...

# Exceptions

class DataDecodingError(Exception): ...
class JobUsageError(Exception): ...
class PasswordError(Exception): ...
class PdfError(Exception): ...
class ForeignObjectError(Exception): ...
class DeletedObjectError(Exception): ...

# Enums
class AccessMode(Enum):
    default: int = ...
    mmap: int = ...
    mmap_only: int = ...
    stream: int = ...

class EncryptionMethod(Enum):
    none: int = ...
    unknown: int = ...
    rc4: int = ...
    aes: int = ...
    aesv3: int = ...

class ObjectStreamMode(Enum):
    disable: int = ...
    generate: int = ...
    preserve: int = ...

class ObjectType(Enum):
    array: int = ...
    boolean: int = ...
    dictionary: int = ...
    inlineimage: int = ...
    integer: int = ...
    name_: int = ...
    null: int = ...
    operator: int = ...
    real: int = ...
    reserved: int = ...
    stream: int = ...
    string: int = ...
    uninitialized: int = ...

class StreamDecodeLevel(Enum):
    """Options for decoding streams within PDFs."""

    all: int = ...
    generalized: int = ...
    none: int = ...
    specialized: int = ...

class TokenType(Enum):
    array_close: int = ...
    array_open: int = ...
    bad: int = ...
    bool: int = ...
    brace_close: int = ...
    brace_open: int = ...
    comment: int = ...
    dict_close: int = ...
    dict_open: int = ...
    eof: int = ...
    inline_image: int = ...
    integer: int = ...
    name_: int = ...
    null: int = ...
    real: int = ...
    space: int = ...
    string: int = ...
    word: int = ...

class Object:
    def _ipython_key_completions_(self) -> KeysView | None: ...
    def _inline_image_raw_bytes(self) -> bytes: ...
    def _parse_page_contents(self, callbacks: Callable) -> None: ...
    def _parse_page_contents_grouped(
        self, whitelist: str
    ) -> list[tuple[Collection[Object | PdfInlineImage], Operator]]: ...
    @staticmethod
    def _parse_stream(stream: Object, parser: StreamParser) -> list: ...
    @staticmethod
    def _parse_stream_grouped(stream: Object, whitelist: str) -> list: ...
    def _repr_mimebundle_(self, include=None, exclude=None) -> dict | None: ...
    def _write(
        self,
        data: bytes,
        filter: Object,  # pylint: disable=redefined-builtin
        decode_parms: Object,
    ) -> None: ...
    def append(self, pyitem: Any) -> None:
        """Append another object to an array; fails if the object is not an array."""
    def as_dict(self) -> _ObjectMapping: ...
    def as_list(self) -> _ObjectList: ...
    def emplace(self, other: Object, retain: Iterable[Name] = ...) -> None: ...
    def extend(self, iter: Iterable[Object]) -> None:
        """Extend a pikepdf.Array with an iterable of other pikepdf.Object."""
    def get(self, key: int | str | Name, default: T | None = ...) -> Object | T | None:
        """Retrieve an attribute from the object.

        Only works if the object is a Dictionary, Array or Stream.
        """
    def get_raw_stream_buffer(self) -> Buffer:
        """Return a buffer protocol buffer describing the raw, encoded stream."""
    def get_stream_buffer(self, decode_level: StreamDecodeLevel = ...) -> Buffer:
        """Return a buffer protocol buffer describing the decoded stream."""
    def is_owned_by(self, possible_owner: Pdf) -> bool:
        """Test if this object is owned by the indicated *possible_owner*."""
    def items(self) -> Iterable[tuple[str, Object]]: ...
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
        r"""Convert to a QPDF JSON representation of the object.

        See the QPDF manual for a description of its JSON representation.
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
    def with_same_owner_as(self, arg0: Object) -> Object:
        """Returns an object that is owned by the same Pdf that owns *other* object.

        If the objects already have the same owner, this object is returned.
        If the *other* object has a different owner, then a copy is created
        that is owned by *other*'s owner. If this object is a direct object
        (no owner), then an indirect object is created that is owned by
        *other*. An exception is thrown if *other* is a direct object.

        This method may be convenient when a reference to the Pdf is not
        available.

        .. versionadded:: 2.14
        """
    def wrap_in_array(self) -> Array:
        """Return the object wrapped in an array if not already an array."""
    def write(
        self,
        data: bytes,
        *,
        filter: Name | Array | None = ...,  # pylint: disable=redefined-builtin
        decode_parms: Dictionary | Array | None = ...,
        type_check: bool = ...,
    ) -> None: ...
    def __bool__(self) -> bool: ...
    def __bytes__(self) -> bytes: ...
    def __contains__(self, obj: Object | str) -> bool: ...
    def __copy__(self) -> Object: ...
    def __delattr__(self, name: str) -> None: ...
    @overload
    def __delitem__(self, name: str | Name) -> None: ...
    @overload
    def __delitem__(self, n: int) -> None: ...
    def __dir__(self) -> list: ...
    def __eq__(self, other: Any) -> bool: ...
    def __getattr__(self, name: str) -> Object: ...
    @overload
    def __getitem__(self, name: str | Name) -> Object: ...
    @overload
    def __getitem__(self, n: int) -> Object: ...
    def __hash__(self) -> int: ...
    def __iter__(self) -> Iterable[Object]: ...
    def __len__(self) -> int: ...
    def __setattr__(self, name: str, value: Any) -> None: ...
    @overload
    def __setitem__(self, name: str | Name, value: Any) -> None: ...
    @overload
    def __setitem__(self, n: int, value: Any) -> None: ...
    @property
    def _objgen(self) -> tuple[int, int]: ...
    @property
    def _type_code(self) -> ObjectType: ...
    @property
    def _type_name(self) -> str: ...
    @property
    def images(self) -> _ObjectMapping: ...
    @property
    def is_indirect(self) -> bool: ...
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

class ObjectHelper:
    """Base class for wrapper/helper around an Object.

    Used to expose additional functionality specific to that object type.

    :class:`pikepdf.Page` is an example of an object helper. The actual
    page object is a PDF is a Dictionary. The helper provides additional
    methods specific to pages.
    """

    def __eq__(self, other: Any) -> bool: ...
    @property
    def obj(self) -> Dictionary:
        """Get the underlying PDF object (typically a Dictionary)."""

class _ObjectList:
    @overload
    def __init__(self) -> None: ...
    @overload
    def __init__(self, arg0: _ObjectList) -> None: ...
    @overload
    def __init__(self, arg0: Iterable) -> None: ...
    @overload
    def __init__(*args, **kwargs) -> None: ...
    def append(self, x: Object) -> None: ...
    def clear(self) -> None: ...
    def count(self, x: Object) -> int: ...
    @overload
    def extend(self, L: _ObjectList) -> None: ...
    @overload
    def extend(self, L: Iterable[Object]) -> None: ...
    def insert(self, i: int, x: Object) -> None: ...
    @overload
    def pop(self) -> Object: ...
    @overload
    def pop(self, i: int) -> Object: ...
    @overload
    def pop(*args, **kwargs) -> Any: ...
    def remove(self, x: Object) -> None: ...
    def __bool__(self) -> bool: ...
    def __contains__(self, x: Object) -> bool: ...
    @overload
    def __delitem__(self, arg0: int) -> None: ...
    @overload
    def __delitem__(self, arg0: slice) -> None: ...
    @overload
    def __delitem__(*args, **kwargs) -> Any: ...
    def __eq__(self, other: Any) -> bool: ...
    @overload
    def __getitem__(self, s: slice) -> _ObjectList: ...
    @overload
    def __getitem__(self, arg0: int) -> Object: ...
    @overload
    def __getitem__(*args, **kwargs) -> Any: ...
    def __iter__(self) -> Iterator[Object]: ...
    def __len__(self) -> int: ...
    def __ne__(self, other: Any) -> bool: ...
    @overload
    def __setitem__(self, arg0: int, arg1: Object) -> None: ...
    @overload
    def __setitem__(self, arg0: slice, arg1: _ObjectList) -> None: ...
    @overload
    def __setitem__(*args, **kwargs) -> Any: ...

class _ObjectMapping:
    get: Any = ...
    keys: Any = ...
    values: Any = ...
    def __contains__(self, arg0: Name | str) -> bool: ...
    def __init__(self) -> None: ...
    def items(self) -> Iterator: ...
    def __bool__(self) -> bool: ...
    def __delitem__(self, arg0: str) -> None: ...
    def __getitem__(self, arg0: Name | str) -> Object: ...
    def __iter__(self) -> Iterator: ...
    def __len__(self) -> int: ...
    def __setitem__(self, arg0: str, arg1: Object) -> None: ...

class Operator(Object): ...

class Annotation:
    def __init__(self, arg0: Object) -> None: ...
    def get_appearance_stream(
        self, which: Object, state: Object | None = ...
    ) -> Object:
        """Returns one of the appearance streams associated with an annotation.

        Args:
            which: Usually one of ``pikepdf.Name.N``, ``pikepdf.Name.R`` or
                ``pikepdf.Name.D``, indicating the normal, rollover or down
                appearance stream, respectively. If any other name is passed,
                an appearance stream with that name is returned.
            state: The appearance state. For checkboxes or radio buttons, the
                appearance state is usually whether the button is on or off.
        """
    def get_page_content_for_appearance(
        self,
        name: Name,
        rotate: int,
        required_flags: int = ...,
        forbidden_flags: int = ...,
    ) -> bytes:
        """Generate content stream text that draws this annotation as a Form XObject.

        Args:
            name: What to call the object we create.
            rotate: Should be set to the page's /Rotate value or 0.
            required_flags: The required appearance flags. See PDF reference manual.
            forbidden_flags: The forbidden appearance flags. See PDF reference manual.

        Note:
            This method is done mainly with QPDF. Its behavior may change when
            different QPDF versions are used.
        """
    @property
    def appearance_dict(self) -> Object:
        """Returns the annotations appearance dictionary."""
    @property
    def appearance_state(self) -> Object:
        """Returns the annotation's appearance state (or None).

        For a checkbox or radio button, the appearance state may be ``pikepdf.Name.On``
        or ``pikepdf.Name.Off``.
        """
    @property
    def flags(self) -> int:
        """Returns the annotation's flags."""
    @property
    def obj(self) -> Object: ...
    @property
    def subtype(self) -> str:
        """Returns the subtype of this annotation."""

class AttachedFile:
    _creation_date: str
    _mod_date: str
    creation_date: datetime.datetime | None
    mime_type: str
    """Get the MIME type of the attached file according to the PDF creator."""
    mod_date: datetime.datetime | None
    @property
    def md5(self) -> bytes:
        """Get the MD5 checksum of attached file according to the PDF creator."""
    @property
    def obj(self) -> Object: ...
    def read_bytes(self) -> bytes: ...
    @property
    def size(self) -> int:
        """Get length of the attached file in bytes according to the PDF creator."""

class AttachedFileSpec(ObjectHelper):
    def __init__(
        self,
        data: bytes,
        *,
        description: str,
        filename: str,
        mime_type: str,
        creation_date: str,
        mod_date: str,
    ) -> None:
        """Construct a attached file spec from data in memory.

        To construct a file spec from a file on the computer's file system,
        use :meth:`from_filepath`.

        Args:
            data: Resource to load.
            description: Any description text for the attachment. May be
                shown in PDF viewers.
            filename: Filename to display in PDF viewers.
            mime_type: Helps PDF viewers decide how to display the information.
            creation_date: PDF date string for when this file was created.
            mod_date: PDF date string for when this file was last modified.
            relationship: A :class:`pikepdf.Name` indicating the relationship
                of this file to the document. Canonically, this should be a name
                from the PDF specification:
                Source, Data, Alternative, Supplement, EncryptedPayload, FormData,
                Schema, Unspecified. If omitted, Unspecified is used.
        """
    def get_all_filenames(self) -> dict:
        """Return a Python dictionary that describes all filenames.

        The returned dictionary is not a pikepdf Object.

        Multiple filenames are generally a holdover from the pre-Unicode era.
        Modern PDFs can generally set UTF-8 filenames and avoid using
        punctuation or other marks that are forbidden in filenames.
        """
    def get_file(self, name: Name = ...) -> AttachedFile:
        """Return an attached file.

        Typically, only one file is attached to an attached file spec.
        When multiple files are attached, use the ``name`` parameter to
        specify which one to return.

        Args:
            name: Typical names would be ``/UF`` and ``/F``. See |pdfrm|
                for other obsolete names.
        """
    @staticmethod
    def from_filepath(
        pdf: Pdf, path: Path | str, *, description: str = ''
    ) -> AttachedFileSpec:
        """Construct a file specification from a file path.

        This function will automatically add a creation and modified date
        using the file system, and a MIME type inferred from the file's extension.

        If the data required for the attach is in memory, use
        :meth:`pikepdf.AttachedFileSpec` instead.

        Args:
            pdf: The Pdf to attach this file specification to.
            path: A file path for the file to attach to this Pdf.
            description: An optional description. May be shown to the user in
                PDF viewers.
            relationship: An optional relationship type. May be used to
                indicate the type of attachment, e.g. Name.Source or Name.Data.
                Canonically, this should be a name from the PDF specification:
                Source, Data, Alternative, Supplement, EncryptedPayload, FormData,
                Schema, Unspecified. If omitted, Unspecified is used.
        """
    @property
    def description(self) -> str:
        """Description text associated with the embedded file."""
    @property
    def filename(self) -> str:
        """The main filename for this file spec.

        In priority order, getting this returns the first of /UF, /F, /Unix,
        /DOS, /Mac if multiple filenames are set. Setting this will set a UTF-8
        encoded Unicode filename and write it to /UF.
        """
    @property
    def relationship(self) -> Name | None:
        """Describes the relationship of this attached file to the PDF."""
    @relationship.setter
    def relationship(self, value: Name | None) -> None: ...

class Attachments(MutableMapping[str, AttachedFileSpec]):
    def __contains__(self, k: object) -> bool: ...
    def __delitem__(self, k: str) -> None: ...
    def __eq__(self, other: Any) -> bool: ...
    def __getitem__(self, k: str) -> AttachedFileSpec: ...
    def __iter__(self) -> Iterator[str]: ...
    def __len__(self) -> int: ...
    def __setitem__(self, k: str, v: AttachedFileSpec): ...
    def __init__(self, *args, **kwargs) -> None: ...
    def _add_replace_filespec(self, arg0: str, arg1: AttachedFileSpec) -> None: ...
    def _get_all_filespecs(self) -> dict[str, AttachedFileSpec]: ...
    def _get_filespec(self, arg0: str) -> AttachedFileSpec: ...
    def _remove_filespec(self, arg0: str) -> bool: ...
    @property
    def _has_embedded_files(self) -> bool: ...

class Token:
    def __init__(self, arg0: TokenType, arg1: bytes) -> None: ...
    def __eq__(self, other: Any) -> bool: ...
    @property
    def error_msg(self) -> str:
        """If the token is an error, this returns the error message."""
    @property
    def raw_value(self) -> bytes:
        """The binary representation of a token."""
    @property
    def type_(self) -> TokenType:
        """Returns the type of token."""
    @property
    def value(self) -> str:
        """Interprets the token as a string."""

class _QPDFTokenFilter: ...

class TokenFilter(_QPDFTokenFilter):
    def __init__(self) -> None: ...
    def handle_token(self, token: Token = ...) -> None | Token | Iterable[Token]:
        """Handle a :class:`pikepdf.Token`.

        This is an abstract method that must be defined in a subclass
        of ``TokenFilter``. The method will be called for each token.
        The implementation may return either ``None`` to discard the
        token, the original token to include it, a new token, or an
        iterable containing zero or more tokens. An implementation may
        also buffer tokens and release them in groups (for example, it
        could collect an entire PDF command with all of its operands,
        and then return all of it).

        The final token will always be a token of type ``TokenType.eof``,
        (unless an exception is raised).

        If this method raises an exception, the exception will be
        caught by C++, consumed, and replaced with a less informative
        exception. Use :meth:`pikepdf.Pdf.get_warnings` to view the
        original.
        """

class StreamParser:
    """A simple content stream parser, which must be subclassed to be used.

    In practice, the performance of this class may be quite poor on long
    content streams because it creates objects and involves multiple
    function calls for every object in a content stream, some of which
    may be only a single byte long.

    Consider instead using :func:`pikepdf.parse_content_stream`.
    """

    def __init__(self) -> None: ...
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

class Page:
    _repr_mimebundle_: Any = ...
    @overload
    def __init__(self, arg0: Object) -> None: ...
    @overload
    def __init__(self, arg0: Page) -> None: ...
    def __contains__(self, key: Any) -> bool: ...
    def __delattr__(self, name: Any) -> None: ...
    def __eq__(self, other: Any) -> bool: ...
    def __getattr__(self, name: Any) -> Object: ...
    def __getitem__(self, name: Any) -> Object: ...
    def __setattr__(self, name: Any, value: Any): ...
    def __setitem__(self, name: Any, value: Any): ...
    def _get_artbox(self, arg0: bool, arg1: bool) -> Object: ...
    def _get_bleedbox(self, arg0: bool, arg1: bool) -> Object: ...
    def _get_cropbox(self, arg0: bool, arg1: bool) -> Object: ...
    def _get_mediabox(self, arg0: bool) -> Object: ...
    def _get_trimbox(self, arg0: bool, arg1: bool) -> Object: ...
    def add_content_token_filter(self, tf: TokenFilter) -> None:
        """Attach a :class:`pikepdf.TokenFilter` to a page's content stream.

        This function applies token filters lazily, if/when the page's
        content stream is read for any reason, such as when the PDF is
        saved. If never access, the token filter is not applied.

        Multiple token filters may be added to a page/content stream.

        Token filters may not be removed after being attached to a Pdf.
        Close and reopen the Pdf to remove token filters.

        If the page's contents is an array of streams, it is coalesced.

        Args:
            tf: The token filter to attach.
        """
    def add_overlay(
        self,
        other: Object | Page,
        rect: Rectangle | None,
        *,
        push_stack: bool | None = ...,
    ): ...
    def add_underlay(self, other: Object | Page, rect: Rectangle | None): ...
    def as_form_xobject(self, handle_transformations: bool = ...) -> Object:
        """Return a form XObject that draws this page.

        This is useful for
        n-up operations, underlay, overlay, thumbnail generation, or
        any other case in which it is useful to replicate the contents
        of a page in some other context. The dictionaries are shallow
        copies of the original page dictionary, and the contents are
        coalesced from the page's contents. The resulting object handle
        is not referenced anywhere.

        Args:
            handle_transformations: If True (default), the resulting form
                XObject's ``/Matrix`` will be set to replicate rotation
                (``/Rotate``) and scaling (``/UserUnit``) in the page's
                dictionary. In this way, the page's transformations will
                be preserved when placing this object on another page.
        """
    def calc_form_xobject_placement(
        self,
        formx: Object,
        name: Name,
        rect: Rectangle,
        *,
        invert_transformations: bool,
        allow_shrink: bool,
        allow_expand: bool,
    ) -> bytes:
        """Generate content stream segment to place a Form XObject on this page.

        The content stream segment must then be added to the page's
        content stream.

        The default keyword parameters will preserve the aspect ratio.

        Args:
            formx: The Form XObject to place.
            name: The name of the Form XObject in this page's /Resources
                dictionary.
            rect: Rectangle describing the desired placement of the Form
                XObject.
            invert_transformations: Apply /Rotate and /UserUnit scaling
                when determining FormX Object placement.
            allow_shrink: Allow the Form XObject to take less than the
                full dimensions of rect.
            allow_expand: Expand the Form XObject to occupy all of rect.

        .. versionadded:: 2.14
        """
    def contents_add(
        self, contents: Stream | bytes, *, prepend: bool = ...
    ) -> None: ...
    def contents_coalesce(self) -> None:
        """Coalesce a page's content streams.

        A page's content may be a
        stream or an array of streams. If this page's content is an
        array, concatenate the streams into a single stream. This can
        be useful when working with files that split content streams in
        arbitrary spots, such as in the middle of a token, as that can
        confuse some software.
        """
    def emplace(self, other: Page, retain: Iterable[Name] = ...) -> None: ...
    def externalize_inline_images(
        self, min_size: int = ..., shallow: bool = ...
    ) -> None:
        """Convert inline image to normal (external) images.

        Args:
            min_size: minimum size in bytes
            shallow: If False, recurse into nested Form XObjects.
                If True, do not recurse.
        """
    def get(self, key: str | Name, default: T | None = ...) -> T | None | Object: ...
    def get_filtered_contents(self, tf: TokenFilter) -> bytes:
        """Apply a :class:`pikepdf.TokenFilter` to a content stream.

        This may be used when the results of a token filter do not need
        to be applied, such as when filtering is being used to retrieve
        information rather than edit the content stream.

        Note that it is possible to create a subclassed ``TokenFilter``
        that saves information of interest to its object attributes; it
        is not necessary to return data in the content stream.

        To modify the content stream, use :meth:`pikepdf.Page.add_content_token_filter`.

        Returns:
            The result of modifying the content stream with ``tf``.
            The existing content stream is not modified.
        """
    def index(self) -> int:
        """Returns the zero-based index of this page in the pages list.

        That is, returns ``n`` such that ``pdf.pages[n] == this_page``.
        A ``ValueError`` exception is thrown if the page is not attached
        to this ``Pdf``.

        .. versionadded:: 2.2
        """
    def label(self) -> str:
        """Returns the page label for this page, accounting for section numbers.

        For example, if the PDF defines a preface with lower case Roman
        numerals (i, ii, iii...), followed by standard numbers, followed
        by an appendix (A-1, A-2, ...), this function returns the appropriate
        label as a string.

        It is possible for a PDF to define page labels such that multiple
        pages have the same labels. Labels are not guaranteed to
        be unique.

        .. versionadded:: 2.2

        .. versionchanged:: 2.9
            Returns the ordinary page number if no special rules for page
            numbers are defined.
        """
    def parse_contents(self, stream_parser: StreamParser) -> None:
        """Parse a page's content streams using a :class:`pikepdf.StreamParser`.

        The content stream may be interpreted by the StreamParser but is
        not altered.

        If the page's contents is an array of streams, it is coalesced.

        Args:
            stream_parser: A :class:`pikepdf.StreamParser` instance.
        """
    def remove_unreferenced_resources(self) -> None:
        """Removes resources not referenced by content stream.

        A page's resources (``page.resources``) dictionary maps names to objects.
        This method walks through a page's contents and
        keeps tracks of which resources are referenced somewhere in the
        contents. Then it removes from the resources dictionary any
        object that is not referenced in the contents. This
        method is used by page splitting code to avoid copying unused
        objects in files that use shared resource dictionaries across
        multiple pages.
        """
    def rotate(self, angle: int, relative: bool) -> None:
        """Rotate a page.

        If ``relative`` is ``False``, set the rotation of the
        page to angle. Otherwise, add angle to the rotation of the
        page. ``angle`` must be a multiple of ``90``. Adding ``90`` to
        the rotation rotates clockwise by ``90`` degrees.

        Args:
            angle: Rotation angle in degrees.
            relative: If ``True``, add ``angle`` to the current
                rotation. If ``False``, set the rotation of the page
                to ``angle``.
        """
    @property
    def images(self) -> _ObjectMapping: ...
    @property
    def cropbox(self) -> Array: ...
    @cropbox.setter
    def cropbox(self, val: Array) -> None: ...
    @property
    def mediabox(self) -> Array: ...
    @mediabox.setter
    def mediabox(self, val: Array) -> None: ...
    @property
    def obj(self) -> Dictionary: ...
    @property
    def trimbox(self) -> Array: ...
    @trimbox.setter
    def trimbox(self, val: Array) -> None: ...
    @property
    def resources(self) -> Dictionary: ...
    def add_resource(
        self,
        res: Object,
        res_type: Name,
        name: Name | None = None,
        *,
        prefix: str = '',
        replace_existing: bool = True,
    ) -> Name: ...

class PageList:
    def __init__(self, *args, **kwargs) -> None: ...
    def append(self, page: Page) -> None:
        """Add another page to the end.

        While this method copies pages from one document to another, it does not
        copy certain metadata such as annotations, form fields, bookmarks or
        structural tree elements. Copying these is a more complex, application
        specific operation.
        """
    @overload
    def extend(self, other: PageList) -> None:
        """Extend the ``Pdf`` by adding pages from another ``Pdf.pages``.

        While this method copies pages from one document to another, it does not
        copy certain metadata such as annotations, form fields, bookmarks or
        structural tree elements. Copying these is a more complex, application
        specific operation.
        """
    @overload
    def extend(self, iterable: Iterable[Page]) -> None:
        """Extend the ``Pdf`` by adding pages from an iterable of pages.

        While this method copies pages from one document to another, it does not
        copy certain metadata such as annotations, form fields, bookmarks or
        structural tree elements. Copying these is a more complex, application
        specific operation.
        """
    @overload
    def from_objgen(self, objgen: tuple[int, int]) -> Page:
        """Given an "objgen" (object ID, generation), return the page.

        Raises an exception if no page matches.
        """
    @overload
    def from_objgen(self, objid: int, gen: int) -> Page:
        """Given an "objgen" (object ID, generation), return the page.

        Raises an exception if no page matches.
        """
    def index(self, page: Page | Object) -> int:
        """Given a page, find the index.

        That is, returns ``n`` such that ``pdf.pages[n] == this_page``.
        A ``ValueError`` exception is thrown if the page does not belong to
        to this ``Pdf``. The first page has index 0.
        """
    def insert(self, index: int, obj: Page) -> None:
        """Insert a page at the specified location.

        Args:
            index: location at which to insert page, 0-based indexing
            obj: page object to insert
        """
    def p(self, pnum: int) -> Page:
        """Look up page number in ordinal numbering, where 1 is the first page.

        This is provided for convenience in situations where ordinal numbering
        is more natural. It is equivalent to ``.pages[pnum - 1]``. ``.p(0)``
        is an error and negative indexing is not supported.

        If the PDF defines custom page labels (such as labeling front matter
        with Roman numerals and the main body with Arabic numerals), this
        function does not account for that. Use :attr:`pikepdf.Page.label`
        to get the page label for a page.
        """
    def remove(self, *, p: int) -> None:
        """Remove a page (using 1-based numbering).

        Args:
            p: 1-based page number
        """
    def reverse(self) -> None:
        """Reverse the order of pages."""
    @overload
    def __delitem__(self, arg0: int) -> None: ...
    @overload
    def __delitem__(self, arg0: slice) -> None: ...
    @overload
    def __getitem__(self, arg0: int) -> Page: ...
    @overload
    def __getitem__(self, arg0: slice) -> list[Page]: ...
    def __iter__(self) -> PageList: ...
    def __len__(self) -> int: ...
    def __next__(self) -> Page: ...
    @overload
    def __setitem__(self, arg0: int, arg1: Page) -> None: ...
    @overload
    def __setitem__(self, arg0: slice, arg1: Iterable[Page]) -> None: ...

class Pdf:
    _repr_mimebundle_: Any = ...
    def add_blank_page(self, *, page_size: tuple[Numeric, Numeric] = ...) -> Page: ...
    def __enter__(self) -> Pdf: ...
    def __exit__(self, exc_type, exc_value, traceback) -> None: ...
    def __init__(self, *args, **kwargs) -> None: ...
    def _add_page(self, page: Object, first: bool = ...) -> None:
        """Low-level private method to attach a page to this PDF.

        The page can be either be a newly constructed PDF object or it can
        be obtained from another PDF.

        Args:
            page: The page object to attach.
            first: If True, prepend this before the first page;
                if False append after last page.
        """
    def _decode_all_streams_and_discard(self) -> None: ...
    def _get_object_id(self, arg0: int, arg1: int) -> Object: ...
    def _process(self, arg0: str, arg1: bytes) -> None: ...
    def _remove_page(self, arg0: Object) -> None: ...
    def _replace_object(self, arg0: tuple[int, int], arg1: Object) -> None: ...
    def _swap_objects(self, arg0: tuple[int, int], arg1: tuple[int, int]) -> None: ...
    def check(self) -> list[str]: ...
    def check_linearization(self, stream: object = ...) -> bool:
        """Reports information on the PDF's linearization.

        Args:
            stream: A stream to write this information too; must
                implement ``.write()`` and ``.flush()`` method. Defaults to
                :data:`sys.stderr`.

        Returns:
            ``True`` if the file is correctly linearized, and ``False`` if
            the file is linearized but the linearization data contains errors
            or was incorrectly generated.

        Raises:
            RuntimeError: If the PDF in question is not linearized at all.
        """
    def close(self) -> None: ...
    def copy_foreign(self, h: Object) -> Object:
        """Copy an ``Object`` from a foreign ``Pdf`` and return a copy.

        The object must be owned by a different ``Pdf`` from this one.

        If the object has previously been copied, return a reference to
        the existing copy, even if that copy has been modified in the meantime.

        If you want to copy a page from one PDF to another, use:
        ``pdf_b.pages[0] = pdf_a.pages[0]``. That interface accounts for the
        complexity of copying pages.

        This function is used to copy a :class:`pikepdf.Object` that is owned by
        some other ``Pdf`` into this one. This is performs a deep (recursive) copy
        and preserves all references that may exist in the foreign object. For
        example, if

            >>> object_a = pdf.copy_foreign(object_x)
            >>> object_b = pdf.copy_foreign(object_y)
            >>> object_c = pdf.copy_foreign(object_z)

        and ``object_z`` is a shared descendant of both ``object_x`` and ``object_y``
        in the foreign PDF, then ``object_c`` is a shared descendant of both
        ``object_a`` and ``object_b`` in this PDF. If ``object_x`` and ``object_y``
        refer to the same object, then ``object_a`` and ``object_b`` are the
        same object.

        It also copies all :class:`pikepdf.Stream` objects. Since this may copy
        a large amount of data, it is not done implicitly. This function does
        not copy references to pages in the foreign PDF - it stops at page
        boundaries. Thus, if you use ``copy_foreign()`` on a table of contents
        (``/Outlines`` dictionary), you may have to update references to pages.

        Direct objects, including dictionaries, do not need ``copy_foreign()``.
        pikepdf will automatically convert and construct them.

        Note:
            pikepdf automatically treats incoming pages from a foreign PDF as
            foreign objects, so :attr:`Pdf.pages` does not require this treatment.

        See Also:
            `QPDF::copyForeignObject <https://qpdf.readthedocs.io/en/stable/design.html#copying-objects-from-other-pdf-files>`_

        .. versionchanged:: 2.1
            Error messages improved.
        """
    @overload
    def get_object(self, objgen: tuple[int, int]) -> Object:
        """Retrieve an object from the PDF.

        Args:
            objgen: A tuple containing the object ID and generation.
        """
    @overload
    def get_object(self, objid: int, gen: int) -> Object:
        """Retrieve an object from the PDF.

        Args:
            objid: The object ID of the object to retrieve.
            gen: The generation number of the object to retrieve.
        """
    def get_warnings(self) -> list: ...
    @overload
    def make_indirect(self, obj: T) -> T: ...
    def make_indirect(self, obj: Any) -> Object:
        """Attach an object to the Pdf as an indirect object.

        Direct objects appear inline in the binary encoding of the PDF.
        Indirect objects appear inline as references (in English, "look
        up object 4 generation 0") and then read from another location in
        the file. The PDF specification requires that certain objects
        are indirect - consult the PDF specification to confirm.

        Generally a resource that is shared should be attached as an
        indirect object. :class:`pikepdf.Stream` objects are always
        indirect, and creating them will automatically attach it to the
        Pdf.

        Args:
            obj: The object to attach. If this a :class:`pikepdf.Object`,
                it will be attached as an indirect object. If it is
                any other Python object, we attempt conversion to
                :class:`pikepdf.Object` attach the result. If the
                object is already an indirect object, a reference to
                the existing object is returned. If the ``pikepdf.Object``
                is owned by a different Pdf, an exception is raised; use
                :meth:`pikepdf.Object.copy_foreign` instead.

        See Also:
            :meth:`pikepdf.Object.is_indirect`
        """
    def make_stream(self, data: bytes, d=None, **kwargs) -> Stream: ...
    @classmethod
    def new(cls) -> Pdf:
        """Create a new, empty PDF.

        This is best when you are constructing a PDF from scratch.

        In most cases, if you are working from an existing PDF, you should open the
        PDF using :meth:`pikepdf.Pdf.open` and transform it, instead of a creating
        a new one, to preserve metadata and structural information. For example,
        if you want to split a PDF into two parts, you should open the PDF and
        transform it into the desired parts, rather than creating a new PDF and
        copying pages into it.
        """
    @staticmethod
    def open(
        filename_or_stream: Path | str | BinaryIO,
        *,
        password: str | bytes = '',
        hex_password: bool = False,
        ignore_xref_streams: bool = False,
        suppress_warnings: bool = True,
        attempt_recovery: bool = True,
        inherit_page_attributes: bool = True,
        access_mode: AccessMode = AccessMode.default,
        allow_overwriting_input: bool = False,
    ) -> Pdf: ...
    def open_metadata(
        self,
        set_pikepdf_as_editor: bool = True,
        update_docinfo: bool = True,
        strict: bool = False,
    ) -> PdfMetadata: ...
    def open_outline(self, max_depth: int = 15, strict: bool = False) -> Outline: ...
    def remove_unreferenced_resources(self) -> None:
        """Remove from /Resources any object not referenced in page's contents.

        PDF pages may share resource dictionaries with other pages. If
        pikepdf is used for page splitting, pages may reference resources
        in their /Resources dictionary that are not actually required.
        This purges all unnecessary resource entries.

        For clarity, if all references to any type of object are removed, that
        object will be excluded from the output PDF on save. (Conversely, only
        objects that are discoverable from the PDF's root object are included.)
        This function removes objects that are referenced from the page /Resources
        dictionary, but never called for in the content stream, making them
        unnecessary.

        Suggested before saving, if content streams or /Resources dictionaries
        are edited.
        """
    def save(
        self,
        filename_or_stream: Path | str | BinaryIO | None = None,
        *,
        static_id: bool = False,
        preserve_pdfa: bool = True,
        min_version: str | tuple[str, int] = '',
        force_version: str | tuple[str, int] = '',
        fix_metadata_version: bool = True,
        compress_streams: bool = True,
        stream_decode_level: StreamDecodeLevel | None = None,
        object_stream_mode: ObjectStreamMode = ObjectStreamMode.preserve,
        normalize_content: bool = False,
        linearize: bool = False,
        qdf: bool = False,
        progress: Callable[[int], None] | None = None,
        encryption: Encryption | bool | None = None,
        recompress_flate: bool = False,
        deterministic_id: bool = False,
    ) -> None: ...
    def show_xref_table(self) -> None:
        """Pretty-print the Pdf's xref (cross-reference table)."""
    @property
    def Root(self) -> Object: ...
    @property
    def _allow_accessibility(self) -> bool: ...
    @property
    def _allow_extract(self) -> bool: ...
    @property
    def _allow_modify_all(self) -> bool: ...
    @property
    def _allow_modify_annotation(self) -> bool: ...
    @property
    def _allow_modify_assembly(self) -> bool: ...
    @property
    def _allow_modify_form(self) -> bool: ...
    @property
    def _allow_modify_other(self) -> bool: ...
    @property
    def _allow_print_highres(self) -> bool: ...
    @property
    def _allow_print_lowres(self) -> bool: ...
    @property
    def _encryption_data(self) -> dict: ...
    @property
    def _pages(self) -> Any: ...
    @property
    def allow(self) -> Permissions: ...
    @property
    def docinfo(self) -> Object: ...
    @docinfo.setter
    def docinfo(self, val: Object) -> None: ...
    @property
    def encryption(self) -> EncryptionInfo: ...
    @property
    def extension_level(self) -> int:
        """Returns the extension level of this PDF.

        If a developer has released multiple extensions of a PDF version against
        the same base version value, they shall increase the extension level
        by 1. To be interpreted with :attr:`pdf_version`.
        """
    @property
    def filename(self) -> str:
        """The source filename of an existing PDF, when available.

        When the Pdf was created from scratch, this returns 'empty PDF'.
        When the Pdf was created from a stream, the return value is the
        word 'stream' followed by some information about the stream, if
        available.
        """
    @property
    def is_encrypted(self) -> bool:
        """Returns True if the PDF is encrypted.

        For information about the nature of the encryption, see
        :attr:`Pdf.encryption`.
        """
    @property
    def is_linearized(self) -> bool:
        """Returns True if the PDF is linearized.

        Specifically returns True iff the file starts with a linearization
        parameter dictionary.  Does no additional validation.
        """
    @property
    def objects(self) -> _ObjectList:
        """Return an iterable list of all objects in the PDF.

        After deleting content from a PDF such as pages, objects related
        to that page, such as images on the page, may still be present in
        this list.
        """
    @property
    def pages(self) -> PageList:
        """Returns the list of pages."""
    @property
    def pdf_version(self) -> str:
        """The version of the PDF specification used for this file, such as '1.7'.

        More precise information about the PDF version can be opened from the
        Pdf's XMP metadata.
        """
    @property
    def root(self) -> Object:
        """The /Root object of the PDF."""
    @property
    def trailer(self) -> Object:
        """Provides access to the PDF trailer object.

        See |pdfrm| section 7.5.5. Generally speaking,
        the trailer should not be modified with pikepdf, and modifying it
        may not work. Some of the values in the trailer are automatically
        changed when a file is saved.
        """
    @property
    def user_password_matched(self) -> bool:
        """Returns True if the user password matched when the ``Pdf`` was opened.

        It is possible for both the user and owner passwords to match.

        .. versionadded:: 2.10
        """
    @property
    def owner_password_matched(self) -> bool:
        """Returns True if the owner password matched when the ``Pdf`` was opened.

        It is possible for both the user and owner passwords to match.

        .. versionadded:: 2.10
        """
    def generate_appearance_streams(self) -> None:
        """Generates appearance streams for AcroForm forms and form fields.

        Appearance streams describe exactly how annotations and form fields
        should appear to the user. If omitted, the PDF viewer is free to
        render the annotations and form fields according to its own settings,
        as needed.

        For every form field in the document, this generates appearance
        streams, subject to the limitations of QPDF's ability to create
        appearance streams.

        When invoked, this method will modify the ``Pdf`` in memory. It may be
        best to do this after the ``Pdf`` is opened, or before it is saved,
        because it may modify objects that the user does not expect to be
        modified.

        If ``Pdf.Root.AcroForm.NeedAppearances`` is ``False`` or not present, no
        action is taken (because no appearance streams need to be generated).
        If ``True``, the appearance streams are generated, and the NeedAppearances
        flag is set to ``False``.

        See:
            https://github.com/qpdf/qpdf/blob/bf6b9ba1c681a6fac6d585c6262fb2778d4bb9d2/include/qpdf/QPDFFormFieldObjectHelper.hh#L216

        .. versionadded:: 2.11
        """
    def flatten_annotations(self, mode: str) -> None:
        """Flattens all PDF annotations into regular PDF content.

        Annotations are markup such as review comments, highlights, proofreading
        marks. User data entered into interactive form fields also counts as an
        annotation.

        When annotations are flattened, they are "burned into" the regular
        content stream of the document and the fact that they were once annotations
        is deleted. This can be useful when preparing a document for printing,
        to ensure annotations are printed, or to finalize a form that should
        no longer be changed.

        Args:
            mode: One of the strings ``'all'``, ``'screen'``, ``'print'``. If
                omitted or  set to empty, treated as ``'all'``. ``'screen'``
                flattens all except those marked with the PDF flag /NoView.
                ``'print'`` flattens only those marked for printing.
                Default is ``'all'``.

        .. versionadded:: 2.11
        """
    @property
    def attachments(self) -> Attachments:
        """Returns a mapping that provides access to all files attached to this PDF.

        PDF supports attaching (or embedding, if you prefer) any other type of file,
        including other PDFs. This property provides read and write access to
        these objects by filename.
        """

class Rectangle:
    """A PDF rectangle.

    Typically this will be a rectangle in PDF units (points, 1/72").
    Unlike raster graphics, the rectangle is defined by the **lower**
    left and upper right points.

    Rectangles in PDF are encoded as :class:`pikepdf.Array` with exactly
    four numeric elements, ordered as ``llx lly urx ury``.
    See |pdfrm| section 7.9.5.

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
    def __init__(self, other: Rectangle): ...
    @overload
    def __init__(self, other: Array) -> None: ...
    def __and__(self, other: Rectangle) -> Rectangle:
        """Return the bounding Rectangle of the common area of self and other."""
    def __le__(self, other: Rectangle) -> bool:
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
    def __eq__(self, other: Any) -> bool: ...
    def __repr__(self) -> str: ...

class NameTree(MutableMapping[str | bytes, Object]):
    @staticmethod
    def new(pdf: Pdf, *, auto_repair: bool = True) -> NameTree:
        """Create a new NameTree in the provided Pdf.

        You will probably need to insert the name tree in the PDF's
        catalog. For example, to insert this name tree in
        /Root /Names /Dests:

        .. code-block:: python

            nt = NameTree.new(pdf)
            pdf.Root.Names.Dests = nt.obj
        """
    def __contains__(self, name: object) -> bool: ...
    def __delitem__(self, name: str | bytes) -> None: ...
    def __eq__(self, other: Any) -> bool: ...
    def __getitem__(self, name: str | bytes) -> Object: ...
    def __iter__(self) -> Iterator[bytes]: ...
    def __len__(self) -> int: ...
    def __setitem__(self, name: str | bytes, o: Object) -> None: ...
    def __init__(self, obj: Object, *, auto_repair: bool = ...) -> None: ...
    def _as_map(self) -> _ObjectMapping: ...
    @property
    def obj(self) -> Object:
        """Returns the underlying root object for this name tree."""

class NumberTree(MutableMapping[int, Object]):
    @staticmethod
    def new(pdf: Pdf, *, auto_repair: bool = True) -> NumberTree:
        """Create a new NumberTree in the provided Pdf.

        You will probably need to insert the number tree in the PDF's
        catalog. For example, to insert this number tree in
        /Root /PageLabels:

        .. code-block:: python

            nt = NumberTree.new(pdf)
            pdf.Root.PageLabels = nt.obj
        """
    def __contains__(self, key: object) -> bool: ...
    def __delitem__(self, key: int) -> None: ...
    def __eq__(self, other: Any) -> bool: ...
    def __getitem__(self, key: int) -> Object: ...
    def __iter__(self) -> Iterator[int]: ...
    def __len__(self) -> int: ...
    def __setitem__(self, key: int, o: Object) -> None: ...
    def __init__(self, obj: Object, *, auto_repair: bool = ...) -> None: ...
    def _as_map(self) -> _ObjectMapping: ...
    @property
    def obj(self) -> Object: ...

class ContentStreamInstruction:
    def __init__(self, *args) -> None: ...
    @property
    def operands(self) -> _ObjectList: ...
    @property
    def operator(self) -> Operator: ...
    def __getitem__(self, index: int) -> _ObjectList | Operator: ...
    def __len__(self) -> int: ...

class ContentStreamInlineImage:
    @property
    def operands(self) -> _ObjectList: ...
    @property
    def operator(self) -> Operator: ...
    def __getitem__(self, index: int) -> _ObjectList | Operator: ...
    def __len__(self) -> int: ...
    @property
    def iimage(self) -> PdfInlineImage: ...

class Job:
    """Provides access to the QPDF job interface.

    All of the functionality of the ``qpdf`` command line program
    is now available to pikepdf through jobs.

    For further details:
        https://qpdf.readthedocs.io/en/stable/qpdf-job.html
    """

    EXIT_ERROR: ClassVar[int] = 2
    """Exit code for a job that had an error."""
    EXIT_WARNING: ClassVar[int] = 3
    """Exit code for a job that had a warning."""
    EXIT_IS_NOT_ENCRYPTED: ClassVar[int] = 2
    """Exit code for a job that provide a password when the input was not encrypted."""
    EXIT_CORRECT_PASSWORD: ClassVar[int] = 3
    LATEST_JOB_JSON: ClassVar[int]
    """Version number of the most recent job-JSON schema."""
    LATEST_JSON: ClassVar[int]
    """Version number of the most recent QPDF-JSON schema."""

    @staticmethod
    def json_out_schema(*, schema: int) -> str:
        """For reference, the QPDF JSON output schema is built-in."""
    @staticmethod
    def job_json_schema(*, schema: int) -> str:
        """For reference, the QPDF job command line schema is built-in."""
    @overload
    def __init__(self, json: str) -> None: ...
    @overload
    def __init__(self, json_dict: Mapping) -> None: ...
    @overload
    def __init__(
        self, args: Sequence[str | bytes], *, progname: str = 'pikepdf'
    ) -> None: ...
    def __init__(self, *args, **kwargs) -> None:
        """Create a Job from command line arguments to the qpdf program.

        The first item in the ``args`` list should be equal to ``progname``,
        whose default is ``"pikepdf"``.

        Example:
            job = Job(['pikepdf', '--check', 'input.pdf'])
            job.run()
        """
    def check_configuration(self) -> None:
        """Checks if the configuration is valid; raises an exception if not."""
    @property
    def creates_output(self) -> bool:
        """Returns True if the Job will create some sort of output file."""
    @property
    def message_prefix(self) -> str:
        """Allows manipulation of the prefix in front of all output messages."""
    def run(self) -> None: ...
    def create_pdf(self):
        """Executes the first stage of the job."""
    def write_pdf(self, pdf: Pdf):
        """Executes the second stage of the job."""
    @property
    def has_warnings(self) -> bool:
        """After run(), returns True if there were warnings."""
    @property
    def exit_code(self) -> int:
        """After run(), returns an integer exit code.

        The meaning of exit code depends on the details of the Job that was run.
        Details are subject to change in libqpdf. Use properties ``has_warnings``
        and ``encryption_status`` instead.
        """
    @property
    def encryption_status(self) -> dict[str, bool]:
        """Returns a Python dictionary describing the encryption status."""

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
    def __matmul__(self, other: Matrix) -> Matrix:
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
    def __array__(self) -> np.ndarray:
        """Convert this matrix to a NumPy array.

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
    def __eq__(self, other: Any) -> bool: ...
    def __getstate__(self) -> tuple[float, float, float, float, float, float]: ...
    def __setstate__(
        self, state: tuple[float, float, float, float, float, float]
    ) -> None: ...

def _Null() -> Any: ...
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

def _test_file_not_found(*args, **kwargs) -> Any: ...
def _translate_qpdf_logic_error(arg0: str) -> str: ...
def get_decimal_precision() -> int:
    """Set the number of decimal digits to use when converting floats."""

def pdf_doc_to_utf8(pdfdoc: bytes) -> str:
    """Low-level function to convert PDFDocEncoding to UTF-8.

    Use the pdfdoc codec instead of using this directly.
    """

def qpdf_version() -> str: ...
def set_access_default_mmap(mmap: bool) -> bool: ...
def get_access_default_mmap() -> bool: ...
def set_decimal_precision(prec: int) -> int:
    """Get the number of decimal digits to use when converting floats."""

def unparse(obj: Any) -> bytes: ...
def utf8_to_pdf_doc(utf8: str, unknown: bytes) -> tuple[bool, bytes]: ...
def _unparse_content_stream(contentstream: Iterable[Any]) -> bytes: ...
def set_flate_compression_level(
    level: Literal[-1, 0, 1, 2, 3, 4, 5, 6, 7, 8, 9]
) -> int:
    """Set compression level whenever Flate compression is used.

    Args:
        level: -1 (default), 0 (no compression), 1 to 9 (increasing compression)
    """
