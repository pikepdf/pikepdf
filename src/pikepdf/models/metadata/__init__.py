# SPDX-FileCopyrightText: 2022 James R. Barlow
# SPDX-License-Identifier: MPL-2.0

"""PDF metadata handling.

This module provides XMP and DocumentInfo metadata access for PDF files.
"""

from __future__ import annotations

from pikepdf.models.metadata._constants import (
    DEFAULT_NAMESPACES,
    XMP_CONTAINERS,
    XMP_EMPTY,
    XMP_NS_DC,
    XMP_NS_PDF,
    XMP_NS_PDFA_EXTENSION,
    XMP_NS_PDFA_ID,
    XMP_NS_PDFA_PROPERTY,
    XMP_NS_PDFA_SCHEMA,
    XMP_NS_PDFUA_ID,
    XMP_NS_PDFX_ID,
    XMP_NS_PHOTOSHOP,
    XMP_NS_PRISM,
    XMP_NS_PRISM2,
    XMP_NS_PRISM3,
    XMP_NS_RDF,
    XMP_NS_XML,
    XMP_NS_XMP,
    XMP_NS_XMP_MM,
    XMP_NS_XMP_RIGHTS,
    XPACKET_BEGIN,
    XPACKET_END,
    AltList,
    XmpContainer,
)
from pikepdf.models.metadata._converters import (
    DOCINFO_MAPPING,
    AuthorConverter,
    Converter,
    DateConverter,
    DocinfoMapping,
    decode_pdf_date,
    encode_pdf_date,
)
from pikepdf.models.metadata._core import PdfMetadata
from pikepdf.models.metadata._xmp import XmpDocument


def __getattr__(name):
    if name == 'LANG_ALTS':
        from pikepdf.models.metadata import _constants
        val = getattr(_constants, 'LANG_ALTS')
        globals()[name] = val
        return val
    raise AttributeError(f"module {__name__} has no attribute {name}")

__all__ = [
    # Main classes
    'PdfMetadata',
    'XmpDocument',
    # Converters
    'Converter',
    'AuthorConverter',
    'DateConverter',
    'DocinfoMapping',
    'DOCINFO_MAPPING',
    'decode_pdf_date',
    'encode_pdf_date',
    # Namespace constants
    'XMP_NS_DC',
    'XMP_NS_PDF',
    'XMP_NS_PDFA_ID',
    'XMP_NS_PDFA_EXTENSION',
    'XMP_NS_PDFA_PROPERTY',
    'XMP_NS_PDFA_SCHEMA',
    'XMP_NS_PDFUA_ID',
    'XMP_NS_PDFX_ID',
    'XMP_NS_PHOTOSHOP',
    'XMP_NS_PRISM',
    'XMP_NS_PRISM2',
    'XMP_NS_PRISM3',
    'XMP_NS_RDF',
    'XMP_NS_XML',
    'XMP_NS_XMP',
    'XMP_NS_XMP_MM',
    'XMP_NS_XMP_RIGHTS',
    # Other exports
    'DEFAULT_NAMESPACES',
    'LANG_ALTS',
    'XPACKET_BEGIN',
    'XPACKET_END',
    'XMP_CONTAINERS',
    'XMP_EMPTY',
    'AltList',
    'XmpContainer',
]
