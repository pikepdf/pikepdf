# SPDX-FileCopyrightText: 2026 James R. Barlow
# SPDX-License-Identifier: MPL-2.0

"""Checks of the document XMP metadata packet.

The raw packet is checked with regular expressions (encoding, packet header,
namespace declarations) and its properties with the strict reader in
`pikepdf.pdfa._xmp_rdf`, against the allowlists in
``data/xmp_properties.json``.
"""

from __future__ import annotations

import datetime as dt
import re

import pikepdf
from pikepdf.models.metadata import decode_pdf_date
from pikepdf.models.metadata._converters import parse_xmp_date
from pikepdf.pdfa._context import ValidationContext
from pikepdf.pdfa._flavour import Flavour
from pikepdf.pdfa._xmp_rdf import Reading, read_packet, tables

_PACKET_HEADER = re.compile(r'<\?xpacket\s+(?!end\s*=)(.*?)\?>', re.DOTALL)
_XMLNS = re.compile(r'''xmlns:([A-Za-z0-9_.-]+)\s*=\s*(["'])(.*?)\2''', re.DOTALL)
_DEFAULT_XMLNS = re.compile(r'''\sxmlns\s*=''')

PDFAID = 'http://www.aiim.org/pdfa/ns/id/'
DC = 'http://purl.org/dc/elements/1.1/'
XMP = 'http://ns.adobe.com/xap/1.0/'
PDF = 'http://ns.adobe.com/pdf/1.3/'

# Document information entries that PDF/A-1 requires to agree with XMP:
# (Info key, XMP property, ISO 19005-1 rule, comparison)
_INFO_EQUIVALENTS = (
    ('/CreationDate', f'{{{XMP}}}CreateDate', '6.7.3-1', 'date'),
    ('/Title', f'{{{DC}}}title', '6.7.3-2', 'langalt'),
    ('/Author', f'{{{DC}}}creator', '6.7.3-3', 'creator'),
    ('/Subject', f'{{{DC}}}description', '6.7.3-4', 'langalt'),
    ('/Keywords', f'{{{PDF}}}Keywords', '6.7.3-5', 'text'),
    ('/Creator', f'{{{XMP}}}CreatorTool', '6.7.3-6', 'text'),
    ('/Producer', f'{{{PDF}}}Producer', '6.7.3-7', 'text'),
    ('/ModDate', f'{{{XMP}}}ModifyDate', '6.7.3-8', 'date'),
)


def check_metadata(ctx: ValidationContext) -> None:
    """Check the document catalog's XMP metadata stream."""
    metadata = ctx.pdf.Root.get('/Metadata')
    if not isinstance(metadata, pikepdf.Stream):
        ctx.deny(
            ctx.rule('6.7.2-1', '6.6.2.1-1'),
            'catalog',
            "the catalog has no /Metadata stream",
        )
        return
    where = f'{ctx.describe(metadata)} (MetadataStream)'
    try:
        raw = metadata.read_bytes()
    except pikepdf.PdfError as e:
        ctx.deny('pikepdf:xmp', where, f"cannot read metadata: {e}", 'unsupported')
        return
    try:
        text = raw.decode('utf-8')
    except UnicodeDecodeError:
        ctx.deny(
            ctx.rule('6.7.9-1', '6.6.2.1-5'), where, "XMP packet is not valid UTF-8"
        )
        return

    _check_packet_header(ctx, text, where)
    _check_namespaces(ctx, text, where)
    reading = read_packet(raw, ctx.flavour)
    _report_problems(ctx, reading, where)
    if not reading.parsed:
        return
    _check_identification(ctx, reading, where)
    if ctx.flavour.part == 1:
        _check_info_agreement(ctx, reading)


def _check_packet_header(ctx: ValidationContext, text: str, where: str) -> None:
    match = _PACKET_HEADER.search(text)
    if match is None:
        return
    attributes = match.group(1)
    if re.search(r'\bbytes\s*=', attributes):
        ctx.deny(
            ctx.rule('6.7.5-1', '6.6.2.1-2'),
            where,
            "the XMP packet header uses the bytes attribute",
        )
    if re.search(r'\bencoding\s*=', attributes):
        ctx.deny(
            ctx.rule('6.7.5-2', '6.6.2.1-3'),
            where,
            "the XMP packet header uses the encoding attribute",
        )


def permitted_namespaces(flavour: Flavour) -> frozenset[str]:
    """Return the namespace URIs an XMP packet may declare for *flavour*."""
    known = tables()['namespaces']
    return frozenset(
        known[prefix] for prefix in tables()['flavour_namespaces'][flavour]
    )


def namespace_used(text: str, prefix: str) -> bool:
    """Return True if an element or attribute name in *text* uses *prefix*."""
    return bool(re.search(rf'[<\s/]{re.escape(prefix)}:[A-Za-z_]', text))


def disallowed_namespaces(text: str, flavour: Flavour) -> list[tuple[str, str]]:
    """Return the ``(prefix, uri)`` declarations in an XMP packet not permitted.

    Declarations of permitted namespaces, and unused declarations of
    namespaces that may only be declared, are not returned.
    """
    allowed = permitted_namespaces(flavour)
    declaration_only = {
        uri
        for prefix, uri in tables()['declaration_only'].items()
        if not prefix.startswith('$')
    }
    result = []
    for prefix, _quote, uri in _XMLNS.findall(text):
        if uri in allowed:
            continue
        if uri in declaration_only and not namespace_used(text, prefix):
            continue
        result.append((prefix, uri))
    return result


def _check_namespaces(ctx: ValidationContext, text: str, where: str) -> None:
    rule = ctx.rule('6.7.9-2', '6.6.2.3.1-1')
    if _DEFAULT_XMLNS.search(text):
        ctx.deny(
            'pikepdf:xmp-default-namespace',
            where,
            "XMP uses a default namespace",
            'unsupported',
        )
    for prefix, _quote, uri in _XMLNS.findall(text):
        if uri == PDFAID and prefix != 'pdfaid':
            ctx.deny(
                ctx.rule('6.7.11-4', '6.6.4-4'),
                where,
                f"PDF/A identification namespace uses prefix {prefix!r}",
            )
    for prefix, uri in disallowed_namespaces(text, ctx.flavour):
        ctx.deny(rule, where, f"XMP namespace {prefix}={uri} is not permitted")


def _report_problems(ctx: ValidationContext, reading: Reading, where: str) -> None:
    syntax_rule = ctx.rule('6.7.9-1', '6.6.2.1-4')
    type_rule = ctx.rule('6.7.9-3', '6.6.2.3.1-2')
    for problem in reading.problems:
        if problem.category == 'syntax':
            ctx.deny(syntax_rule, where, problem.message)
        elif problem.category == 'about':
            # veraPDF reads a Description about another resource, as long as
            # every Description is about the same one
            ctx.deny(syntax_rule, where, problem.message, 'unsupported')
        elif problem.category == 'unknown':
            ctx.deny(ctx.rule('6.7.9-2', '6.6.2.3.1-1'), where, problem.message)
        elif problem.category == 'type':
            ctx.deny(type_rule, where, problem.message)
        else:
            ctx.deny(type_rule, where, problem.message, 'unsupported')


def _check_identification(ctx: ValidationContext, reading: Reading, where: str) -> None:
    part = reading.text(f'{{{PDFAID}}}part')
    conformance = reading.text(f'{{{PDFAID}}}conformance')
    if part is None:
        ctx.deny(
            ctx.rule('6.7.11-1', '6.6.4-1'),
            where,
            "XMP has no PDF/A identification (pdfaid:part)",
        )
        return
    if part != str(ctx.flavour.part):
        ctx.deny(
            ctx.rule('6.7.11-2', '6.6.4-2'),
            where,
            f"pdfaid:part is {part!r}, expected {ctx.flavour.part}",
        )
    if conformance != 'B':
        ctx.deny(
            ctx.rule('6.7.11-3', '6.6.4-3'),
            where,
            f"pdfaid:conformance is {conformance!r}, expected 'B'",
        )


# Dates before the Gregorian calendar was adopted are compared in the Julian
# calendar by veraPDF
_FIRST_GREGORIAN_YEAR = 1583


def _parse_xmp_date(value: str | None) -> dt.datetime | None:
    if value is None:
        return None
    try:
        return parse_xmp_date(value)
    except ValueError:
        return None


def _parse_pdf_date(value: str) -> dt.datetime | None:
    try:
        return decode_pdf_date(value)
    except (ValueError, TypeError):
        return None


def _date_unsupported(info: str, xmp: str | None) -> str | None:
    """Return why a date pair cannot be compared the way veraPDF does."""
    a, b = _parse_pdf_date(info), _parse_xmp_date(xmp)
    if (a is not None and a.tzinfo is None) or (b is not None and b.tzinfo is None):
        # veraPDF reads an unzoned XMP date in the local time zone of the
        # machine it runs on, and an unzoned PDF date as UTC, so whether it
        # accepts such a pair depends on where it runs.
        return 'has no time zone'
    if any(d is not None and d.year < _FIRST_GREGORIAN_YEAR for d in (a, b)):
        return 'is before the Gregorian calendar'
    return None


def _dates_equal(info: str, xmp: str | None) -> bool:
    a, b = _parse_pdf_date(info), _parse_xmp_date(xmp)
    if a is None or b is None:
        return False
    return a == b


def _xmp_equivalent(reading: Reading, key: str, comparison: str) -> str | None:
    value = reading.properties.get(key)
    if value is None:
        return None
    if comparison == 'langalt':
        return value.x_default()
    if comparison == 'creator':
        return value.items[0] if value.form == 'Seq' and len(value.items) == 1 else None
    return value.text if value.form == 'simple' else None


def _check_info_agreement(ctx: ValidationContext, reading: Reading) -> None:
    info = ctx.pdf.trailer.get('/Info')
    if not isinstance(info, pikepdf.Dictionary):
        return
    where = f'{ctx.describe(info)} (Info)'
    for info_key, xmp_key, clause, comparison in _INFO_EQUIVALENTS:
        if info_key not in info:
            continue
        value = info.get(info_key)
        xmp_value = _xmp_equivalent(reading, xmp_key, comparison)
        if not isinstance(value, pikepdf.String):
            ctx.deny(f'ISO_19005_1:{clause}', where, f"{info_key} is not a string")
            continue
        text = str(value)
        if comparison == 'date':
            reason = _date_unsupported(text, xmp_value)
            if reason is not None:
                ctx.deny(
                    f'ISO_19005_1:{clause}',
                    where,
                    f"{info_key} {text!r} or XMP {xmp_value!r} {reason}",
                    'unsupported',
                )
                continue
            equal = _dates_equal(text, xmp_value)
        else:
            equal = xmp_value == text
        if not equal:
            ctx.deny(
                f'ISO_19005_1:{clause}',
                where,
                f"{info_key} {text!r} does not match XMP {xmp_value!r}",
            )
