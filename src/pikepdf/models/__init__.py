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
from pikepdf.models.actions import (
    Action,
    GoToAction,
    GoToDpAction,
    GoToEAction,
    GoToRAction,
    JavaScriptAction,
    LaunchAction,
    NamedAction,
    SetOCGStateAction,
    URIAction,
)
from pikepdf.models.encryption import (
    Encryption,
    EncryptionInfo,
    EncryptionMethod,
    Permissions,
)
from pikepdf.models.image import (
    PdfImage,
    PdfInlineImage,
    UnsupportedImageTypeError,  # legacy
)
from pikepdf.models.metadata import PdfMetadata, XmpDocument
from pikepdf.models.outlines import (
    Destination,
    Outline,
    OutlineItem,
    OutlineItemFlag,
    OutlineStructureError,
    PageLocation,
    make_page_destination,
)

__all__ = [
    'Action',
    'GoToAction',
    'GoToDpAction',
    'GoToEAction',
    'GoToRAction',
    'JavaScriptAction',
    'LaunchAction',
    'NamedAction',
    'SetOCGStateAction',
    'URIAction',
    'Destination',
    'ContentStreamInstructions',
    'PdfParsingError',  # legacy
    'UnparseableContentStreamInstructions',
    'parse_content_stream',
    'unparse_content_stream',
    'Encryption',
    'EncryptionInfo',
    'EncryptionMethod',
    'Permissions',
    'PdfImage',
    'PdfInlineImage',
    'UnsupportedImageTypeError',  # legacy
    'PdfMetadata',
    'XmpDocument',
    'Outline',
    'OutlineItem',
    'OutlineItemFlag',
    'OutlineStructureError',  # legacy
    'PageLocation',
    'make_page_destination',
]
