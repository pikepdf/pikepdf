# SPDX-FileCopyrightText: 2024 James R. Barlow
# SPDX-License-Identifier: MPL-2.0

"""Organize all pikepdf exceptions.

See :doc:`/api/exceptions` for the hierarchy these form.
"""

from __future__ import annotations

from pikepdf._core import (
    DataDecodingError,
    DeletedObjectError,
    ForeignObjectError,
    JobUsageError,
    PasswordError,
    PdfError,
    PikepdfError,
    ReferenceCycleError,
)
from pikepdf._exceptions import (
    DependencyError,
    PageCopyWarning,
    PikepdfWarning,
    XmpTypeWarning,
)
from pikepdf.models._content_stream import PdfParsingError
from pikepdf.models.image import (
    HifiPrintImageNotTranscodableError,
    ImageDecompressionError,
    InvalidPdfImageError,
    NotExtractableError,
    UnsupportedImageTypeError,
)
from pikepdf.models.outlines import OutlineStructureError

__all__ = [
    'DataDecodingError',
    'DeletedObjectError',
    'DependencyError',
    'ForeignObjectError',
    'HifiPrintImageNotTranscodableError',
    'ImageDecompressionError',
    'InvalidPdfImageError',
    'JobUsageError',
    'NotExtractableError',
    'OutlineStructureError',
    'PageCopyWarning',
    'PasswordError',
    'PdfError',
    'PdfParsingError',
    'PikepdfError',
    'PikepdfWarning',
    'ReferenceCycleError',
    'UnsupportedImageTypeError',
    'XmpTypeWarning',
]
