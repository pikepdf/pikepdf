# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
#
# Copyright (C) 2017, James R. Barlow (https://github.com/jbarlow83/)

try:
    from . import _qpdf
except ImportError:
    raise ImportError("pikepdf's extension library failed to import")

from ._version import __version__
from ._qpdf import PdfError, Pdf, PasswordError, ObjectStreamMode, StreamDecodeLevel
from .objects import (
    Object,
    ObjectType,
    Name,
    String,
    Array,
    Dictionary,
    Stream,
    Operator,
)
from .models import (
    PdfImage,
    PdfInlineImage,
    UnsupportedImageTypeError,
    PdfMatrix,
    parse_content_stream,
)

from . import _methods

__libqpdf_version__ = _qpdf.qpdf_version()


def open(*args, **kwargs):  # pylint: disable=redefined-builtin
    """Alias for :func:`pikepdf.Pdf.open`. Open a PDF."""
    return Pdf.open(*args, **kwargs)


def new(*args, **kwargs):
    """Alias for :func:`pikepdf.Pdf.new`. Create a new empty PDF."""
    return Pdf.new(*args, **kwargs)
