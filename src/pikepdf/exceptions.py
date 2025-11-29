# SPDX-FileCopyrightText: 2024 James R. Barlow
# SPDX-License-Identifier: MPL-2.0

"""Centralized import and export of all public pikepdf exceptions.

This module collects exceptions from different internal packages and re-exports
them under a unified namespace for easier access.
"""

from __future__ import annotations

# Core exceptions
from pikepdf._core import (
    DataDecodingError,
    DeletedObjectError,
    ForeignObjectError,
    PasswordError,
    PdfError,
)

# Dependency and parsing exceptions
from pikepdf._exceptions import DependencyError
from pikepdf.models._content_stream import PdfParsingError

# Image-related exceptions
from pikepdf.models.image import (
    HifiPrintImageNotTranscodableError,
    ImageDecompressionError,
    InvalidPdfImageError,
    UnsupportedImageTypeError,
)

# Outlines exceptions
from pikepdf.models.outlines import OutlineStructureError

# Public API
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
