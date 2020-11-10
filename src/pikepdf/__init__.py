# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
#
# Copyright (C) 2017, James R. Barlow (https://github.com/jbarlow83/)

"""A library for manipulating PDFs

isort:skip_file
"""

import os

try:
    from . import _qpdf
except ImportError as _e:
    msg = "pikepdf's extension library failed to import"
    raise ImportError(msg) from _e

try:
    from ._version import __version__
except ImportError as _e:
    raise ImportError("Failed to determine version") from _e

from ._qpdf import (
    AccessMode,
    ForeignObjectError,
    ObjectStreamMode,
    Page,
    PasswordError,
    Pdf,
    PdfError,
    StreamDecodeLevel,
    Token,
    TokenFilter,
    TokenType,
)

from .objects import (
    Array,
    Dictionary,
    Name,
    Object,
    ObjectType,
    Operator,
    Stream,
    String,
)

from .models import (
    Encryption,
    Outline,
    OutlineItem,
    OutlineStructureError,
    PageLocation,
    PdfImage,
    PdfInlineImage,
    PdfMatrix,
    Permissions,
    UnsupportedImageTypeError,
    make_page_destination,
    parse_content_stream,
    unparse_content_stream,
)

from . import _methods, codec

__libqpdf_version__ = _qpdf.qpdf_version()


# Provide pikepdf.{open, new} -> pikepdf.Pdf.open
open = Pdf.open  # pylint: disable=redefined-builtin
new = Pdf.new

# Exclude .open, .new here from to make sure from pikepdf import * does not clobber
# builtins.open()
__all__ = [
    'AccessMode',
    'Array',
    'Dictionary',
    'Encryption',
    'Name',
    'Object',
    'ObjectStreamMode',
    'ObjectType',
    'Operator',
    'Outline',
    'OutlineItem',
    'OutlineStructureError',
    'Page',
    'PageLocation',
    'PasswordError',
    'Pdf',
    'PdfError',
    'PdfImage',
    'PdfInlineImage',
    'PdfMatrix',
    'Permissions',
    'Stream',
    'StreamDecodeLevel',
    'String',
    'Token',
    'TokenFilter',
    'TokenType',
    'UnsupportedImageTypeError',
    'make_page_destination',
    'models',
    'parse_content_stream',
    'unparse_content_stream',
]
