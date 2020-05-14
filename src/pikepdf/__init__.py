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
    if os.name == 'nt':
        msg += """
You may need to install the Microsoft Visual C++ runtime.
* x86: https://aka.ms/vs/16/release/vc_redist.x86.exe
* x64: https://aka.ms/vs/16/release/vc_redist.x64.exe
"""
    raise ImportError(msg) from _e

try:
    from ._version import __version__
except ImportError as _e:
    raise ImportError("Failed to determine version") from _e

from ._qpdf import (
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
    PdfImage,
    PdfInlineImage,
    PdfMatrix,
    Permissions,
    UnsupportedImageTypeError,
    parse_content_stream,
    unparse_content_stream,
)

from . import _methods, codec

__libqpdf_version__ = _qpdf.qpdf_version()


def open(*args, **kwargs):  # pylint: disable=redefined-builtin
    """Alias for :func:`pikepdf.Pdf.open`. Open a PDF."""
    return Pdf.open(*args, **kwargs)


def new(*args, **kwargs):
    """Alias for :func:`pikepdf.Pdf.new`. Create a new empty PDF."""
    return Pdf.new(*args, **kwargs)
