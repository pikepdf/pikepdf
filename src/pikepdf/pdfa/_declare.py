# SPDX-FileCopyrightText: 2026 James R. Barlow
# SPDX-License-Identifier: MPL-2.0

"""Declaring PDF/A conformance in the document metadata."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import pikepdf
from pikepdf import Dictionary, Name, Object, Pdf, Stream
from pikepdf.models.metadata import DateConverter
from pikepdf.pdfa._dates import assume_local_time_zone, assume_local_time_zone_iso
from pikepdf.pdfa._flavour import Flavour
from pikepdf.pdfa._xmp_rdf import (
    Reading,
    Value,
    is_date,
    read_packet,
    write_packet,
    xml_safe,
)

log = logging.getLogger(__name__)

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


def _xmp_value_from_docinfo(value: Object, form: str) -> Any:
    """Return the XMP value equivalent to a DocInfo entry, or None."""
    if not isinstance(value, pikepdf.String):
        return None
    text = xml_safe(str(value))
    if not text:
        return None
    if form == 'langalt':
        return Value('Alt', items=(text,), langs=('x-default',))
    if form == 'creator':
        return Value('Seq', items=(text,), langs=(None,))
    if form == 'date':
        try:
            text = DateConverter.xmp_from_docinfo(text)
        except (ValueError, IndexError, TypeError):
            return None
        if not is_date(text):
            return None
    return Value('simple', text=text)


@dataclass(frozen=True)
class XmpCanonicalization:
    """What `canonicalize_xmp` found in the XMP packet it replaced.

    Attributes:
        dropped: Labels (``prefix:name``) of the properties dropped, other
            than the PDF/A identification.
        unreadable: True if there was a packet that could not be read.
        problem: Why the packet could not be read, if it could not.
        declared: True if the packet already declared the PDF/A part of
            the flavour, with conformance level B.
    """

    dropped: tuple[str, ...] = ()
    unreadable: bool = False
    problem: str = ''
    declared: bool = False


@dataclass(frozen=True)
class MetadataDeclaration:
    """What `declare_pdfa_metadata` changed.

    Attributes:
        xmp_dropped: Labels (``prefix:name``) of the XMP properties dropped.
        xmp_unreadable: True if an XMP packet that could not be read was
            replaced.
        xmp_problem: Why the XMP packet could not be read, if it could not.
        dates_zoned: The number of dates given the local time zone.
        pdfa_declared: True if the metadata did not already declare the
            flavour's PDF/A part with conformance level B.
    """

    xmp_dropped: tuple[str, ...] = ()
    xmp_unreadable: bool = False
    xmp_problem: str | None = None
    dates_zoned: int = 0
    pdfa_declared: bool = False


def _declares(reading: Reading, flavour: Flavour) -> bool:
    part = reading.properties.get(f'{{{_PDFAID}}}part')
    conformance = reading.properties.get(f'{{{_PDFAID}}}conformance')
    return (
        part is not None
        and conformance is not None
        and part.text == str(flavour.part)
        and conformance.text == 'B'
    )


def canonicalize_xmp(pdf: Pdf, flavour: Flavour | str) -> list[str]:
    """Rewrite the XMP packet with only what the PDF/A flavour permits.

    The input packet is read with the validator's strict XMP reader. The
    properties it accepts, which are the properties of the XMP
    specification the PDF/A part is based on, with values of the right
    type, are written to a new packet, in the canonical form that the
    validator expects. Everything else is dropped: properties PDF/A does
    not predefine (such as Photoshop or PDF/X properties inherited from the
    input file, unless described by an extension schema, which pikepdf
    does not write), structured properties such as xmpMM:History, whose
    content the validator does not check, values of the wrong form or type,
    and Descriptions of resources other than the document. A Description
    whose ``rdf:about`` is not empty, such as the ``uuid:...`` Acrobat
    writes, describes the document if every Description has the same
    ``rdf:about``; if their values differ, only those with an empty
    ``rdf:about`` do. The new packet always has an empty ``rdf:about``. The
    PDF/A identification is dropped too, to be declared again with
    `add_pdfa_metadata`.

    DocInfo entries whose XMP equivalent is missing from the new packet are
    copied to it, so that the document's title and other information survive
    even if the input packet could not be used.

    Args:
        pdf: An open pikepdf.Pdf object
        flavour: PDF/A flavour, ``'1b'``, ``'2b'`` or ``'3b'``

    Returns:
        Labels (``prefix:name``) of the properties dropped, other than the
        PDF/A identification.
    """
    return list(_canonicalize_xmp(pdf, Flavour(flavour)).dropped)


def _canonicalize_xmp(pdf: Pdf, pdfa_flavour: Flavour) -> XmpCanonicalization:
    """Do the work of `canonicalize_xmp`, reporting what was found."""
    metadata = pdf.Root.get(Name.Metadata)
    reading = Reading()
    if isinstance(metadata, Stream):
        try:
            reading = read_packet(metadata.read_bytes(), pdfa_flavour)
        except pikepdf.PdfError as e:
            log.debug('Could not read the XMP metadata: %s', e)
    properties = {
        key: value
        for key, value in reading.properties.items()
        if not key.startswith(f'{{{_PDFAID}}}')
    }
    info = pdf.trailer.get(Name.Info)
    if isinstance(info, Dictionary):
        for info_key, xmp_key, form in _DOCINFO_XMP:
            if xmp_key in properties or info_key not in info:
                continue
            value = _xmp_value_from_docinfo(info[info_key], form)
            if value is not None:
                properties[xmp_key] = value

    pdf.Root.Metadata = pdf.make_stream(
        write_packet(properties), Type=Name.Metadata, Subtype=Name.XML
    )
    dropped = [
        label for label in reading.dropped_labels() if not label.startswith('pdfaid:')
    ]
    problem = ''
    unreadable = isinstance(metadata, Stream) and not reading.parsed
    if unreadable:
        problem = reading.problems[0].message if reading.problems else ''
        log.debug("Replacing XMP metadata that could not be read: %s", problem)
    if dropped:
        log.debug(
            "Removing XMP metadata that is not permitted in PDF/A-%s: %s",
            pdfa_flavour.value,
            ', '.join(dropped),
        )
    return XmpCanonicalization(
        dropped=tuple(dropped),
        unreadable=unreadable,
        problem=problem,
        declared=_declares(reading, pdfa_flavour),
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


_XMP_DATES = ('xmp:CreateDate', 'xmp:ModifyDate', 'xmp:MetadataDate')


def assume_local_time_zone_for_dates(pdf: Pdf) -> int:
    """Attach the local time zone to document dates that have none.

    PDF/A-1 requires the DocInfo dates to match their XMP equivalents, but
    validators differ on how dates without a time zone compare: veraPDF reads
    an XMP date without one in the local time zone of the machine it runs
    on, and a PDF date without one as UTC. Attaching the local time zone to
    DocInfo /CreationDate and /ModDate, and to xmp:CreateDate,
    xmp:ModifyDate and xmp:MetadataDate, removes the ambiguity.

    Args:
        pdf: An open pikepdf.Pdf object

    Returns:
        The number of dates changed.
    """
    changed = 0
    info = pdf.trailer.get(Name.Info)
    if isinstance(info, Dictionary):
        for key in (Name.CreationDate, Name.ModDate):
            value = info.get(key)
            if not isinstance(value, pikepdf.String):
                continue
            new_value, zone_assumed = assume_local_time_zone(str(value))
            if zone_assumed:
                info[key] = pikepdf.String(new_value)
                changed += 1

    if isinstance(pdf.Root.get(Name.Metadata), Stream):
        with pdf.open_metadata(
            set_pikepdf_as_editor=False, update_docinfo=False
        ) as meta:
            for xmp_key in _XMP_DATES:
                xmp_value = meta.get(xmp_key)
                if not isinstance(xmp_value, str):
                    continue
                new_value, zone_assumed = assume_local_time_zone_iso(xmp_value)
                if zone_assumed:
                    meta[xmp_key] = new_value
                    changed += 1

    if changed:
        log.debug('Assumed the local time zone for %d date(s) without one', changed)
    return changed


def declare_pdfa_metadata(pdf: Pdf, flavour: Flavour | str) -> MetadataDeclaration:
    """Write the canonical PDF/A metadata for a PDF/A flavour.

    The XMP packet is rewritten with only what the PDF/A flavour permits
    (`canonicalize_xmp`), the local time zone is attached to document dates
    without one, PDF/A conformance is declared, and the DocInfo entries with
    XMP equivalents are set from XMP (`add_pdfa_metadata`). The result is the
    packet the validator expects. Conformance is always declared as level B.

    Args:
        pdf: An open pikepdf.Pdf object
        flavour: PDF/A flavour, ``'1b'``, ``'2b'`` or ``'3b'``

    Returns:
        What was changed.
    """
    pdfa_flavour = Flavour(flavour)
    part = str(pdfa_flavour.part)
    canonical = _canonicalize_xmp(pdf, pdfa_flavour)
    dates_zoned = assume_local_time_zone_for_dates(pdf)
    add_pdfa_metadata(pdf, part, 'B')
    return MetadataDeclaration(
        xmp_dropped=canonical.dropped,
        xmp_unreadable=canonical.unreadable,
        xmp_problem=(canonical.problem or None) if canonical.unreadable else None,
        dates_zoned=dates_zoned,
        pdfa_declared=not canonical.declared,
    )
