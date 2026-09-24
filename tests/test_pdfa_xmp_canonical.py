# SPDX-FileCopyrightText: 2026 James R. Barlow
# SPDX-License-Identifier: MPL-2.0

"""XMP packets that pikepdf's metadata mapping reads leniently.

Each case is an rdf:RDF body that veraPDF rejects, in a form that pikepdf's
metadata mapping flattens or does not see. The strict XMP reader must deny
it, and the speculative PDF/A conversion must rewrite it into a canonical
packet that both validators accept, or else be denied.
"""

from __future__ import annotations

import pytest

pytest.importorskip('jsonschema')

import logging
from pathlib import Path

from pdfa_samples import (
    _build_image_only_pdf,
    save_candidate,
    verapdf_failed_rules,
)

import pikepdf
from pikepdf import Dictionary, Name
from pikepdf.pdfa import validate
from pikepdf.pdfa._api import convert
from pikepdf.pdfa._declare import canonicalize_xmp
from pikepdf.pdfa._xmp_rdf import read_packet

NAMESPACES = (
    'xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#" '
    'xmlns:dc="http://purl.org/dc/elements/1.1/" '
    'xmlns:xmp="http://ns.adobe.com/xap/1.0/" '
    'xmlns:pdf="http://ns.adobe.com/pdf/1.3/" '
    'xmlns:xmpMM="http://ns.adobe.com/xap/1.0/mm/" '
    'xmlns:pdfaid="http://www.aiim.org/pdfa/ns/id/"'
)
D = '<rdf:Description rdf:about="">{}</rdf:Description>'
U = '<rdf:Description rdf:about="uuid:6c1f7c5e-1a2b-11dc-9d4e-000d936b25a4">{}</rdf:Description>'
ALT = '<rdf:Alt><rdf:li xml:lang="x-default">{}</rdf:li></rdf:Alt>'

ACROBAT_INFO = {
    '/Title': 'T',
    '/Producer': 'Acrobat Distiller',
    '/Creator': 'Word',
    '/CreationDate': "D:20200101100000+01'00'",
}

# name: (rdf:RDF body, DocInfo, flavours)
CASES = {
    # The value form does not match the property's type
    'title_plain': (D.format('<dc:title>Hello</dc:title>'), None, '12'),
    'title_struct': (
        D.format(
            '<dc:title rdf:parseType="Resource"><xmp:Label>x</xmp:Label></dc:title>'
        ),
        None,
        '12',
    ),
    'creatortool_alt': (
        D.format(f'<xmp:CreatorTool>{ALT.format("T")}</xmp:CreatorTool>'),
        None,
        '12',
    ),
    'creatortool_struct': (
        D.format(
            '<xmp:CreatorTool rdf:parseType="Resource"><xmp:Label>x</xmp:Label>'
            '</xmp:CreatorTool>'
        ),
        None,
        '12',
    ),
    'creatortool_empty_struct': (
        D.format('<xmp:CreatorTool rdf:parseType="Resource"></xmp:CreatorTool>'),
        None,
        '2',
    ),
    'text_attr_struct': (D.format('<xmp:CreatorTool xmp:Label="x"/>'), None, '2'),
    'nested_desc_as_value': (
        D.format(
            '<xmp:CreatorTool><rdf:Description><xmp:Bogus>x</xmp:Bogus>'
            '</rdf:Description></xmp:CreatorTool>'
        ),
        None,
        '2',
    ),
    'creator_bag': (
        D.format('<dc:creator><rdf:Bag><rdf:li>Me</rdf:li></rdf:Bag></dc:creator>'),
        None,
        '2',
    ),
    'subject_seq': (
        D.format('<dc:subject><rdf:Seq><rdf:li>k</rdf:li></rdf:Seq></dc:subject>'),
        None,
        '12',
    ),
    'subject_li_struct': (
        D.format(
            '<dc:subject><rdf:Bag><rdf:li rdf:parseType="Resource">'
            '<xmp:Label>x</xmp:Label></rdf:li></rdf:Bag></dc:subject>'
        ),
        None,
        '2',
    ),
    'subject_li_nested_bag': (
        D.format(
            '<dc:subject><rdf:Bag><rdf:li><rdf:Bag><rdf:li>x</rdf:li></rdf:Bag>'
            '</rdf:li></rdf:Bag></dc:subject>'
        ),
        None,
        '2',
    ),
    'langalt_nolang': (
        D.format('<dc:rights><rdf:Alt><rdf:li>nolang</rdf:li></rdf:Alt></dc:rights>'),
        None,
        '12',
    ),
    # Whitespace around values of constrained types
    'date_ws': (
        D.format('<xmp:CreateDate> 2020-01-01T10:00:00Z </xmp:CreateDate>'),
        None,
        '12',
    ),
    'int_ws': (D.format('<xmpMM:SaveID> 3 </xmpMM:SaveID>'), None, '2'),
    'mime_ws': (D.format('<dc:format> application/pdf </dc:format>'), None, '2'),
    # Descriptions whose rdf:about is not empty, or with other rdf: attributes
    'about_uuid_unknown': (
        D.format('') + U.format('<xmp:Bogus>x</xmp:Bogus>'),
        None,
        '12',
    ),
    'about_uuid_wrongtype': (U.format('<dc:title>plain</dc:title>'), None, '2'),
    'about_missing_unknown': (
        D.format('') + '<rdf:Description><xmp:Bogus>x</xmp:Bogus></rdf:Description>',
        None,
        '2',
    ),
    'about_space_unknown': (
        '<rdf:Description rdf:about=" "><xmp:Bogus>x</xmp:Bogus></rdf:Description>',
        None,
        '2',
    ),
    'rdf_attr_on_desc': ('<rdf:Description rdf:about="" rdf:Bogus="x"/>', None, '2'),
    'uuid_pdf_trapped': (U.format('<pdf:Trapped>False</pdf:Trapped>'), None, '2'),
    'uuid_original_docid': (
        U.format('<xmpMM:OriginalDocumentID>xmp.did:1</xmpMM:OriginalDocumentID>'),
        None,
        '2',
    ),
    'uuid_acrobat_like': (
        U.format(
            '<xmp:CreateDate>2020-01-01T10:00:00+01:00</xmp:CreateDate>'
            '<xmp:CreatorTool>Word</xmp:CreatorTool>'
            '<pdf:Producer>Acrobat Distiller</pdf:Producer>'
            f'<dc:title>{ALT.format("T")}</dc:title>'
        ),
        ACROBAT_INFO,
        '12',
    ),
    # RDF syntax that veraPDF's XMP parser rejects
    'dup_property_two_desc': (
        D.format(f'<dc:title>{ALT.format("A")}</dc:title>')
        + D.format('<dc:title>plain</dc:title>'),
        None,
        '12',
    ),
    'dup_property_same_desc': (
        D.format(
            '<xmp:CreatorTool>A</xmp:CreatorTool>'
            '<xmp:CreatorTool><rdf:Bag><rdf:li>x</rdf:li></rdf:Bag></xmp:CreatorTool>'
        ),
        None,
        '2',
    ),
    'mixed_content': (
        D.format(f'<dc:title>txt{ALT.format("A")}</dc:title>'),
        None,
        '12',
    ),
    'two_arrays': (
        D.format(
            '<dc:subject><rdf:Bag><rdf:li>x</rdf:li></rdf:Bag>'
            '<rdf:Seq><rdf:li>y</rdf:li></rdf:Seq></dc:subject>'
        ),
        None,
        '2',
    ),
    'parsetype_literal': (
        D.format('<xmp:CreatorTool rdf:parseType="Literal"><b>x</b></xmp:CreatorTool>'),
        None,
        '2',
    ),
    'typed_node': (
        '<xmp:Thing rdf:about=""><xmp:Label>x</xmp:Label></xmp:Thing>' + D.format(''),
        None,
        '12',
    ),
    'desc_nodeID': ('<rdf:Description rdf:about="" rdf:nodeID="a"/>', None, '2'),
    'desc_ID': ('<rdf:Description rdf:about="" rdf:ID="a"/>', None, '2'),
    'prop_rdf_ID': (D.format('<xmp:Label rdf:ID="foo">x</xmp:Label>'), None, '2'),
    'li_outside_array': (
        D.format('<xmp:Label><rdf:li>x</rdf:li></xmp:Label>'),
        None,
        '2',
    ),
    # PDF/A-1 DocInfo agreement with values pikepdf reads differently
    'title_first_li_not_xdefault': (
        D.format(
            '<dc:title><rdf:Alt><rdf:li xml:lang="en">A</rdf:li>'
            '<rdf:li xml:lang="x-default">B</rdf:li></rdf:Alt></dc:title>'
        ),
        {'/Title': 'A'},
        '1',
    ),
    'desc_first_li_not_xdefault': (
        D.format(
            '<dc:description><rdf:Alt><rdf:li xml:lang="de">A</rdf:li>'
            '<rdf:li xml:lang="x-default">B</rdf:li></rdf:Alt></dc:description>'
        ),
        {'/Subject': 'A'},
        '1',
    ),
    'title_two_xdefault': (
        D.format(
            '<dc:title><rdf:Alt><rdf:li xml:lang="x-default">A</rdf:li>'
            '<rdf:li xml:lang="x-default">B</rdf:li></rdf:Alt></dc:title>'
        ),
        {'/Title': 'A'},
        '1',
    ),
    'creatortool_rdf_value': (
        D.format(
            '<xmp:CreatorTool rdf:parseType="Resource"><rdf:value>T</rdf:value>'
            '<xmp:Label>q</xmp:Label></xmp:CreatorTool>'
        ),
        {'/Creator': ''},
        '1',
    ),
    'creatortool_rdf_resource': (
        D.format('<xmp:CreatorTool rdf:resource="http://x/"/>'),
        {'/Creator': ''},
        '1',
    ),
    'creatortool_whitespace_only': (
        D.format('<xmp:CreatorTool>   </xmp:CreatorTool>'),
        {'/Creator': ''},
        '1',
    ),
    'createdate_julian': (
        D.format('<xmp:CreateDate>1500-06-01T00:00:00Z</xmp:CreateDate>'),
        {'/CreationDate': 'D:15000601000000Z'},
        '1',
    ),
}

# Cases the strict reader denies although veraPDF accepts them as given: it
# reads Descriptions about other resources as describing the document
VERAPDF_ACCEPTS = {'uuid_acrobat_like'}

PDFAID = '<rdf:Description rdf:about="" pdfaid:part="{part}" pdfaid:conformance="B"/>'


def packet(body: str) -> bytes:
    return (
        '<?xpacket begin="\ufeff" id="W5M0MpCehiHzreSzNTczkc9d"?>\n'
        f'<x:xmpmeta xmlns:x="adobe:ns:meta/"><rdf:RDF {NAMESPACES}>\n{body}\n'
        '</rdf:RDF></x:xmpmeta>\n<?xpacket end="w"?>'
    ).encode()


def make_input(body: str, info: dict[str, str] | None, part: str = '2') -> pikepdf.Pdf:
    """Return the image-only sample with an arbitrary XMP body and DocInfo."""
    pdf = _build_image_only_pdf(part)
    pdf.Root.Metadata = pdf.make_stream(
        packet(body), Type=Name.Metadata, Subtype=Name.XML
    )
    if '/Info' in pdf.trailer:
        del pdf.trailer['/Info']
    if info:
        pdf.trailer.Info = pdf.make_indirect(
            Dictionary({k: pikepdf.String(v) for k, v in info.items()})
        )
    return pdf


def _params():
    for name, (_body, _info, parts) in CASES.items():
        for part in parts:
            yield pytest.param(name, part, id=f'{name}-{part}b')


def assert_verapdf_rejects(path: Path, flavour: str) -> None:
    failed = verapdf_failed_rules(path, flavour)
    if failed is not None:
        assert failed, f"veraPDF finds {path.name} compliant as {flavour}"


@pytest.mark.parametrize('name, part', list(_params()))
def test_strict_reader_denies(name, part, tmp_path):
    """The candidate as given is denied, and veraPDF rejects it too."""
    body, info, _parts = CASES[name]
    with make_input(body + PDFAID.format(part=part), info, part) as pdf:
        # Keep the packet as given: rewriting it to update pdf:PDFVersion
        # would drop Descriptions that hold no properties.
        path = save_candidate(
            pdf, tmp_path / 'candidate.pdf', part, fix_metadata_version=False
        )
    report = validate(path, f'{part}b')
    assert not report.passed
    if name not in VERAPDF_ACCEPTS:
        assert_verapdf_rejects(path, f'{part}b')


@pytest.mark.parametrize('name, part', list(_params()))
def test_conversion_never_falsely_approved(name, part, tmp_path):
    """After conversion the validators agree, or only ours denies."""
    body, info, _parts = CASES[name]
    with make_input(body, info) as pdf:
        pdf.save(tmp_path / 'in.pdf')
    out = convert(tmp_path / 'in.pdf', tmp_path / 'out.pdf', f'{part}b')
    with pikepdf.open(out) as pdf:
        reading = read_packet(pdf.Root.Metadata.read_bytes(), f'{part}b')
        assert reading.problems == []
    report = validate(out, f'{part}b')
    if report.passed:
        failed = verapdf_failed_rules(out, f'{part}b')
        assert not failed, f"veraPDF fails {sorted(failed or ())}"


@pytest.mark.parametrize('part', ['1', '2'])
def test_acrobat_uuid_description_replaced_from_docinfo(part, tmp_path):
    body, info, _parts = CASES['uuid_acrobat_like']
    with make_input(body, info) as pdf:
        pdf.save(tmp_path / 'in.pdf')
    out = convert(tmp_path / 'in.pdf', tmp_path / 'out.pdf', f'{part}b')
    with pikepdf.open(out) as pdf:
        raw = pdf.Root.Metadata.read_bytes()
        assert b'uuid:' not in raw
        assert raw.count(b'<pdf:Producer') == 1
        meta = pdf.open_metadata()
        assert meta['dc:title'] == 'T'
        assert meta['xmp:CreatorTool'] == 'Word'
        assert str(pdf.docinfo.Title) == 'T'
        assert str(pdf.docinfo.Creator) == 'Word'
        assert str(pdf.docinfo.Producer) == meta['pdf:Producer']
    assert validate(out, f'{part}b').passed


def test_docinfo_follows_x_default(tmp_path):
    body, info, _parts = CASES['title_first_li_not_xdefault']
    with make_input(body, info) as pdf:
        pdf.save(tmp_path / 'in.pdf')
    out = convert(tmp_path / 'in.pdf', tmp_path / 'out.pdf', '1b')
    with pikepdf.open(out) as pdf:
        assert str(pdf.docinfo.Title) == 'B'
        raw = pdf.Root.Metadata.read_bytes()
        # x-default comes first
        assert raw.index(b'x-default') < raw.index(b'xml:lang="en"')
    assert validate(out, '1b').passed


@pytest.mark.parametrize('part, author', [('1', None), ('2', 'A; B')])
def test_multiple_creators(part, author, tmp_path):
    body = D.format(
        '<dc:creator><rdf:Seq><rdf:li>A</rdf:li><rdf:li>B</rdf:li></rdf:Seq></dc:creator>'
    )
    with make_input(body, {'/Author': 'A; B'}) as pdf:
        pdf.save(tmp_path / 'in.pdf')
    out = convert(tmp_path / 'in.pdf', tmp_path / 'out.pdf', f'{part}b')
    with pikepdf.open(out) as pdf:
        assert pdf.open_metadata()['dc:creator'] == ['A', 'B']
        value = pdf.docinfo.get(Name.Author)
        assert (None if value is None else str(value)) == author
    assert validate(out, f'{part}b').passed


def test_canonical_packet_keeps_permitted_forms():
    body = (
        D.format(
            f'<dc:title>{ALT.format("T")}</dc:title>'
            '<dc:subject><rdf:Bag><rdf:li>a</rdf:li><rdf:li>b</rdf:li></rdf:Bag></dc:subject>'
            '<dc:date><rdf:Seq><rdf:li>2020-01-01</rdf:li></rdf:Seq></dc:date>'
        )
        + '<rdf:Description rdf:about="" xmp:CreatorTool="tool" pdfaid:part="1"/>'
    )
    with make_input(body, None) as pdf:
        dropped = canonicalize_xmp(pdf, '2b')
        assert dropped == []
        raw = pdf.Root.Metadata.read_bytes()
        assert raw.count(b'<rdf:Description') == 1
        assert b'pdfaid' not in raw
        reading = read_packet(raw, '2b')
        assert reading.problems == []
        values = {k.split('}')[1]: v for k, v in reading.properties.items()}
        assert values['title'].items == ('T',)
        assert values['title'].form == 'Alt'
        assert values['subject'].items == ('a', 'b')
        assert values['subject'].form == 'Bag'
        assert values['date'].form == 'Seq'
        assert values['CreatorTool'].text == 'tool'
        # Idempotent
        assert canonicalize_xmp(pdf, '2b') == []
        assert pdf.Root.Metadata.read_bytes() == raw


def test_canonicalize_logs_dropped(caplog):
    body = D.format('<dc:title>plain</dc:title><xmp:Bogus>x</xmp:Bogus>')
    with (
        make_input(body, None) as pdf,
        caplog.at_level(logging.DEBUG, logger='pikepdf.pdfa'),
    ):
        assert canonicalize_xmp(pdf, '2b') == ['dc:title', 'xmp:Bogus']
    assert "not permitted in PDF/A-2b: dc:title, xmp:Bogus" in caplog.text


def test_canonicalize_unparseable_packet():
    with make_input('', {'/Title': 'Kept'}) as pdf:
        pdf.Root.Metadata.write(b'<x:xmpmeta><broken')
        canonicalize_xmp(pdf, '2b')
        reading = read_packet(pdf.Root.Metadata.read_bytes(), '2b')
        assert reading.problems == []
        assert reading.properties['{http://purl.org/dc/elements/1.1/}title'].items == (
            'Kept',
        )
