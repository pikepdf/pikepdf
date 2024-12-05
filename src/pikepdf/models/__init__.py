# SPDX-FileCopyrightText: 2022 James R. Barlow
# SPDX-License-Identifier: MPL-2.0

"""Python implementation of higher level PDF constructs."""

from __future__ import annotations

from pikepdf.models._content_stream import (
    ContentStreamInstructions,
    PdfParsingError,  # legacy
    UnparseableContentStreamInstructions,
    parse_content_stream,
    unparse_content_stream,
)
from pikepdf.models.encryption import Encryption, EncryptionInfo, Permissions
from pikepdf.models.image import (
    PdfImage,
    PdfInlineImage,
    UnsupportedImageTypeError,  # legacy
)
from pikepdf.models.metadata import PdfMetadata
from pikepdf.models.outlines import (
    Outline,
    OutlineItem,
    OutlineStructureError,
    PageLocation,
    make_page_destination,
)

__all__ = [
    'ContentStreamInstructions',
    'PdfParsingError',  # legacy
    'UnparseableContentStreamInstructions',
    'parse_content_stream',
    'unparse_content_stream',
    'Encryption',
    'EncryptionInfo',
    'Permissions',
    'PdfImage',
    'PdfInlineImage',
    'UnsupportedImageTypeError',  # legacy
    'PdfMetadata',
    'Outline',
    'OutlineItem',
    'OutlineStructureError',  # legacy
    'PageLocation',
    'make_page_destination',
]
