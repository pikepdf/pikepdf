# SPDX-FileCopyrightText: 2022 James R. Barlow
# SPDX-License-Identifier: MPL-2.0

"""A library for manipulating PDFs."""

# isort:skip_file

from __future__ import annotations

from pikepdf._version import __version__

try:
    from pikepdf import _core
except ImportError as _e:  # pragma: no cover
    _msg = "pikepdf's extension library failed to import"
    raise ImportError(_msg) from _e

from pikepdf._core import (
    AccessMode,
    AcroForm,
    AcroFormField,
    Annotation,
    AnnotationFlag,
    AttachedFileSpec,
    ContentStreamInlineImage,
    ContentStreamInstruction,
    DataDecodingError,
    DeletedObjectError,
    ForeignObjectError,
    FormFieldFlag,
    Job,
    JobUsageError,
    Matrix,
    NameTree,
    NumberTree,
    ObjectHelper,
    ObjectStreamMode,
    Page,
    PasswordError,
    Pdf,
    PdfError,
    Rectangle,
    StreamDecodeLevel,
    Token,
    TokenFilter,
    TokenType,
)
from pikepdf.exceptions import (
    DependencyError,
    OutlineStructureError,
    UnsupportedImageTypeError,
)
from pikepdf.objects import (
    Array,
    Boolean,
    Dictionary,
    Integer,
    Name,
    NamePath,
    Object,
    ObjectType,
    Operator,
    Real,
    Stream,
    String,
)
from pikepdf.models import (
    Encryption,
    Outline,
    OutlineItem,
    PageLocation,
    PdfImage,
    PdfInlineImage,
    Permissions,
    make_page_destination,
    parse_content_stream,
    unparse_content_stream,
)

from pikepdf.models.ctm import (
    get_objects_with_ctm,
)


# Importing these will monkeypatch classes defined in C++ and register a new
# pdfdoc codec
# While _cpphelpers is intended to be called from our C++ code only, explicitly
# importing helps introspection tools like PyInstaller figure out that the module
# is necessary.
from pikepdf import _cpphelpers, _methods, codec  # noqa: F401, F841
from pikepdf import settings
from pikepdf import exceptions

__libqpdf_version__: str = _core.qpdf_version()

# Conversion mode API
from contextlib import contextmanager
from typing import Literal


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


# Provide pikepdf.{open, new} -> pikepdf.Pdf.{open, new}
open = Pdf.open  # pylint: disable=redefined-builtin
new = Pdf.new

# Exclude .open, .new here from to make sure from pikepdf import * does not clobber
# builtins.open()
# Exclude codec, objects, jbig2 because we import the interesting bits from them
# directly to here.
_exclude_from__all__ = {'open', 'new', 'codec', 'objects', 'jbig2'}

__all__ = [
    '__libqpdf_version__',
    '__version__',
    'AccessMode',
    'AcroForm',
    'AcroFormField',
    'Annotation',
    'AnnotationFlag',
    'Array',
    'AttachedFileSpec',
    'Boolean',
    'ContentStreamInlineImage',
    'ContentStreamInstruction',
    'DataDecodingError',
    'DeletedObjectError',
    'DependencyError',
    'Dictionary',
    'Encryption',
    'exceptions',
    'explicit_conversion',
    'ForeignObjectError',
    'FormFieldFlag',
    'get_object_conversion_mode',
    'get_objects_with_ctm',
    'HifiPrintImageNotTranscodableError',
    'Integer',
    'InvalidPdfImageError',
    'Job',
    'JobUsageError',
    'make_page_destination',
    'Matrix',
    'models',
    'Name',
    'NamePath',
    'NameTree',
    'NumberTree',
    'Object',
    'ObjectHelper',
    'ObjectStreamMode',
    'ObjectType',
    'Operator',
    'Outline',
    'OutlineItem',
    'OutlineStructureError',
    'Page',
    'PageLocation',
    'parse_content_stream',
    'PasswordError',
    'Pdf',
    'PdfError',
    'PdfImage',
    'PdfInlineImage',
    'Permissions',
    'Real',
    'Rectangle',
    'set_object_conversion_mode',
    'settings',
    'Stream',
    'StreamDecodeLevel',
    'String',
    'Token',
    'TokenFilter',
    'TokenType',
    'unparse_content_stream',
    'UnsupportedImageTypeError',
]
