# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
#
# Copyright (C) 2017, James R. Barlow (https://github.com/jbarlow83/)


from pkg_resources import (
    get_distribution as _get_distribution,
    DistributionNotFound
)

try:
    from . import _qpdf
except ImportError:
    raise ImportError("pikepdf's extension library failed to import")

from ._qpdf import (
    PdfError, Pdf, PasswordError, ObjectStreamMode, StreamDecodeLevel
)
from .objects import (
    Object, ObjectType, Name, String, Array, Dictionary, Stream, Operator
)
from .models import (
    PdfImage, PdfInlineImage, UnsupportedImageTypeError, PdfMatrix,
    parse_content_stream
)

from . import _methods

try:
    __version__ = _get_distribution(__name__).version
except DistributionNotFound:
    __version__ = "Not installed"

__libqpdf_version__ = _qpdf.qpdf_version()


def open(*args, **kwargs):  # pylint: disable=redefined-builtin
    "Alias for :func:`pikepdf.Pdf.open`."
    return Pdf.open(*args, **kwargs)
