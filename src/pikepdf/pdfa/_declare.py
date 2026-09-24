# SPDX-FileCopyrightText: 2026 James R. Barlow
# SPDX-License-Identifier: MPL-2.0

"""Declaring PDF/A conformance in the document metadata."""

from __future__ import annotations

import pikepdf
from pikepdf import Name, Pdf, Stream
from pikepdf.models.metadata import DateConverter
from pikepdf.pdfa._flavour import Flavour
from pikepdf.pdfa._xmp_rdf import read_packet

_DC = 'http://purl.org/dc/elements/1.1/'
_XMP = 'http://ns.adobe.com/xap/1.0/'
_PDF = 'http://ns.adobe.com/pdf/1.3/'
_PDFAID = 'http://www.aiim.org/pdfa/ns/id/'

# DocInfo entries with an XMP equivalent: (DocInfo key, XMP property, form)
_DOCINFO_XMP = (
    ('/Title', f'{{{_DC}}}title', 'langalt'),
    ('/Author', f'{{{_DC}}}creator', 'creator'),
    ('/Subject', f'{{{_DC}}}description', 'langalt'),
    ('/Keywords', f'{{{_PDF}}}Keywords', 'text'),
    ('/Creator', f'{{{_XMP}}}CreatorTool', 'text'),
    ('/Producer', f'{{{_PDF}}}Producer', 'text'),
    ('/CreationDate', f'{{{_XMP}}}CreateDate', 'date'),
    ('/ModDate', f'{{{_XMP}}}ModifyDate', 'date'),
)


def add_pdfa_metadata(pdf: Pdf, part: str, conformance: str) -> None:
    """Add PDF/A XMP metadata declaration to a PDF.

    pikepdf records itself as the producer and the metadata date. The
    DocInfo entries that have XMP equivalents are then set from the XMP
    packet, with `sync_docinfo_from_xmp`.

    Args:
        pdf: An open pikepdf.Pdf object
        part: PDF/A part number ('1', '2', or '3')
        conformance: Conformance level ('A', 'B', or 'U')
    """
    with pdf.open_metadata(update_docinfo=False) as meta:
        meta['pdfaid:part'] = part
        meta['pdfaid:conformance'] = conformance
    sync_docinfo_from_xmp(pdf, f'{part}b')


def sync_docinfo_from_xmp(pdf: Pdf, flavour: str) -> None:
    """Set the DocInfo entries that have XMP equivalents from the XMP packet.

    PDF/A-1 requires DocInfo to agree with XMP. The values are read with the
    validator's strict XMP reader, so they are the values it compares:
    /Title and /Subject from the ``x-default`` item, /Author from
    dc:creator. An entry is removed if its XMP equivalent is missing or
    cannot be represented, and /Author is removed from PDF/A-1 when there is
    more than one creator. Where there is, other flavours join the creators
    with semicolons, as pikepdf does.

    Nothing is changed if the packet is not well-formed.

    Args:
        pdf: An open pikepdf.Pdf object
        flavour: PDF/A flavour, ``'1b'``, ``'2b'`` or ``'3b'``
    """
    pdfa_flavour = Flavour(flavour)
    metadata = pdf.Root.get(Name.Metadata)
    if not isinstance(metadata, Stream):
        return
    reading = read_packet(metadata.read_bytes(), pdfa_flavour)
    if not reading.parsed:
        return
    info = pdf.docinfo
    for info_key, xmp_key, form in _DOCINFO_XMP:
        value = reading.properties.get(xmp_key)
        text: str | None = None
        if value is None:
            pass
        elif form == 'langalt':
            text = value.x_default()
        elif form == 'creator':
            if len(value.items) == 1 or (value.items and pdfa_flavour.part != 1):
                text = '; '.join(value.items)
        elif form == 'date':
            try:
                text = DateConverter.docinfo_from_xmp(value.text)
            except (ValueError, TypeError):
                text = None
        else:
            text = value.text
        if text is None:
            if info_key in info:
                del info[info_key]
        else:
            info[info_key] = pikepdf.String(text)
