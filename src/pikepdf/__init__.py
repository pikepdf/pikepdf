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

from pikepdf._explicit_conv import (
    explicit_conversion,
    get_object_conversion_mode,
    set_object_conversion_mode,
)

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
