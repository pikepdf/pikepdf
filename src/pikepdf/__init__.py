# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
#
# Copyright (C) 2017, James R. Barlow (https://github.com/jbarlow83/)

"""A library for manipulating PDFs

isort:skip_file
"""

try:
    from . import _qpdf
except ImportError as _e:  # pragma: no cover
    _msg = "pikepdf's extension library failed to import"
    raise ImportError(_msg) from _e

try:
    from ._version import __version__
except ImportError as _e:  # pragma: no cover
    raise ImportError("Failed to determine version") from _e

from ._qpdf import (
    AccessMode,
    Annotation,
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

# While _cpphelpers is intended to be called from our C++ code only, explicitly
# importing helps introspection tools like PyInstaller figure out that the
# is necessary.
from . import _cpphelpers

__libqpdf_version__ = _qpdf.qpdf_version()


# Provide pikepdf.{open, new} -> pikepdf.Pdf.{open, new}
open = Pdf.open  # pylint: disable=redefined-builtin
new = Pdf.new

# Exclude .open, .new here from to make sure from pikepdf import * does not clobber
# builtins.open()
# Exclude codec, objects, jbig2 because we import the interesting bits from them
# directly to here.
_exclude_from__all__ = {'open', 'new', 'codec', 'objects', 'jbig2'}

__all__ = [
    k
    for k in locals().keys()
    if not k.startswith('_') and k not in _exclude_from__all__
]
