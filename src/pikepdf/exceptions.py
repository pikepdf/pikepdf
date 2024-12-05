# SPDX-FileCopyrightText: 2024 James R. Barlow
# SPDX-License-Identifier: MPL-2.0

"""Organize all pikepdf exceptions."""

from __future__ import annotations

from pikepdf._core import (
    DataDecodingError,
    DeletedObjectError,
    ForeignObjectError,
    PasswordError,
    PdfError,
)
from pikepdf._exceptions import DependencyError
from pikepdf.models._content_stream import PdfParsingError
from pikepdf.models.image import (
    HifiPrintImageNotTranscodableError,
    ImageDecompressionError,
    InvalidPdfImageError,
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
    'OutlineStructureError',
    'PasswordError',
    'PdfError',
    'PdfParsingError',
    'UnsupportedImageTypeError',
]
