# SPDX-FileCopyrightText: 2026 James R. Barlow
# SPDX-License-Identifier: MPL-2.0

from __future__ import annotations

import pytest

pytest.importorskip('jsonschema')

import zlib

from pdfa_samples import (
    assert_verapdf_agrees,
    assert_verapdf_fails,
    make_image_only_pdf,
    replace_xmp,
    save_candidate,
)

import pikepdf
from pikepdf import Name, String
from pikepdf.pdfa import Flavour, validate_written
from pikepdf.pdfa._context import ValidationContext
from pikepdf.pdfa._report import ValidationReport
from pikepdf.pdfa._schemas import SchemaSet
from pikepdf.pdfa._walker import DocumentWalker
from pikepdf.pdfa._xmp import check_metadata
from pikepdf.pdfa._xmp_rdf import tables

PHOTOSHOP = 'http://ns.adobe.com/photoshop/1.0/'


def check(pdf: pikepdf.Pdf, flavour: str) -> ValidationReport:
    fl = Flavour(flavour)
    report = ValidationReport(fl)
    check_metadata(ValidationContext(fl, pdf, report))
    return report


def rule_ids(report: ValidationReport) -> set[str]:
    return {f.rule for f in report.findings}


@pytest.mark.parametrize('flavour, part', [('1b', '1'), ('2b', '2'), ('3b', '3')])
def test_pikepdf_metadata_accepted(flavour, part):
    with make_image_only_pdf(part) as pdf:
        report = check(pdf, flavour)
        assert report.passed, report.summary()


def test_missing_metadata():
    with make_image_only_pdf() as pdf:
        del pdf.Root['/Metadata']
        assert 'ISO_19005_2:6.6.2.1-1' in rule_ids(check(pdf, '2b'))


def test_bytes_attribute_in_packet_header():
    with make_image_only_pdf() as pdf:
        replace_xmp(pdf, b'<?xpacket begin=', b'<?xpacket bytes="1234" begin=')
        assert 'ISO_19005_2:6.6.2.1-2' in rule_ids(check(pdf, '2b'))
    with make_image_only_pdf('1') as pdf:
        replace_xmp(pdf, b'<?xpacket begin=', b'<?xpacket bytes="1234" begin=')
        assert 'ISO_19005_1:6.7.5-1' in rule_ids(check(pdf, '1b'))


def test_encoding_attribute_in_packet_header():
    with make_image_only_pdf() as pdf:
        replace_xmp(pdf, b'<?xpacket begin=', b'<?xpacket encoding="UTF-8" begin=')
        assert 'ISO_19005_2:6.6.2.1-3' in rule_ids(check(pdf, '2b'))


def test_not_utf8():
    with make_image_only_pdf() as pdf:
        replace_xmp(pdf, b'x:xmptk="pikepdf"', b'x:xmptk="pike\xffpdf"')
        assert 'ISO_19005_2:6.6.2.1-5' in rule_ids(check(pdf, '2b'))


def test_foreign_namespace_denied():
    with make_image_only_pdf() as pdf:
        replace_xmp(
            pdf,
            b'<rdf:Description rdf:about="">',
            b'<rdf:Description rdf:about="" xmlns:pdfx="http://ns.adobe.com/pdfx/1.3/"'
            b' pdfx:Foo="bar">',
        )
        report = check(pdf, '2b')
        assert 'ISO_19005_2:6.6.2.3.1-1' in rule_ids(report)
        assert any('pdfx' in f.message for f in report.findings)


def test_unknown_property_in_known_namespace_denied():
    with make_image_only_pdf() as pdf:
        with pdf.open_metadata(set_pikepdf_as_editor=False) as meta:
            meta['{http://ns.adobe.com/xap/1.0/}Frobnicate'] = 'yes'
        assert 'ISO_19005_2:6.6.2.3.1-1' in rule_ids(check(pdf, '2b'))


def test_wrong_value_type_denied():
    with make_image_only_pdf() as pdf:
        with pdf.open_metadata(
            set_pikepdf_as_editor=False, update_docinfo=False
        ) as meta:
            meta['xmp:CreateDate'] = 'yesterday'
        assert 'ISO_19005_2:6.6.2.3.1-2' in rule_ids(check(pdf, '2b'))


def test_wrong_pdfaid_part():
    with make_image_only_pdf('3') as pdf:
        assert 'ISO_19005_2:6.6.4-2' in rule_ids(check(pdf, '2b'))
    with make_image_only_pdf('2') as pdf:
        assert 'ISO_19005_3:6.6.4-2' in rule_ids(check(pdf, '3b'))


def test_wrong_conformance():
    with make_image_only_pdf() as pdf:
        with pdf.open_metadata(set_pikepdf_as_editor=False) as meta:
            meta['pdfaid:conformance'] = 'A'
        assert 'ISO_19005_2:6.6.4-3' in rule_ids(check(pdf, '2b'))


def test_missing_pdfaid():
    with make_image_only_pdf() as pdf:
        with pdf.open_metadata(set_pikepdf_as_editor=False) as meta:
            del meta['pdfaid:part']
            del meta['pdfaid:conformance']
        assert 'ISO_19005_2:6.6.4-1' in rule_ids(check(pdf, '2b'))


def _add_photoshop(pdf: pikepdf.Pdf) -> None:
    replace_xmp(
        pdf,
        b'<rdf:Description rdf:about="">',
        b'<rdf:Description rdf:about="" xmlns:photoshop="' + PHOTOSHOP.encode() + b'"'
        b' photoshop:Headline="News">',
    )


def test_photoshop_namespace_allowed_in_2b_denied_in_1b():
    with make_image_only_pdf('2') as pdf:
        _add_photoshop(pdf)
        report = check(pdf, '2b')
        assert report.passed, report.summary()
    with make_image_only_pdf('1') as pdf:
        _add_photoshop(pdf)
        assert 'ISO_19005_1:6.7.9-2' in rule_ids(check(pdf, '1b'))


def test_1b_info_title_mismatch():
    with make_image_only_pdf('1') as pdf:
        with pdf.open_metadata(set_pikepdf_as_editor=False) as meta:
            meta['dc:title'] = 'XMP title'
        pdf.docinfo[Name.Title] = String('Info title')
        assert 'ISO_19005_1:6.7.3-2' in rule_ids(check(pdf, '1b'))
        # 2b does not require agreement
        with pdf.open_metadata(
            set_pikepdf_as_editor=False, update_docinfo=False
        ) as meta:
            meta['pdfaid:part'] = '2'
        assert check(pdf, '2b').passed


def test_1b_info_matching_accepted():
    with make_image_only_pdf('1') as pdf:
        with pdf.open_metadata(set_pikepdf_as_editor=False) as meta:
            meta['dc:title'] = 'Same'
            meta['dc:creator'] = ['Author']
            meta['xmp:CreateDate'] = '2015-08-18T22:49:26-07:00'
        pdf.docinfo[Name.CreationDate] = String("D:20150819054926Z")
        report = check(pdf, '1b')
        assert report.passed, report.summary()


def test_1b_info_author_multiple_creators():
    with make_image_only_pdf('1') as pdf:
        with pdf.open_metadata(set_pikepdf_as_editor=False) as meta:
            meta['dc:creator'] = ['A', 'B']
        pdf.docinfo[Name.Author] = String('A')
        assert 'ISO_19005_1:6.7.3-3' in rule_ids(check(pdf, '1b'))


def test_1b_info_date_mismatch():
    with make_image_only_pdf('1') as pdf:
        with pdf.open_metadata(set_pikepdf_as_editor=False) as meta:
            meta['xmp:ModifyDate'] = '2020-01-01T00:00:00Z'
        pdf.docinfo[Name.ModDate] = String('D:20210101000000Z')
        assert 'ISO_19005_1:6.7.3-8' in rule_ids(check(pdf, '1b'))


def test_1b_metadata_filter_denied():
    # qpdf writes metadata streams unfiltered, so mutate the opened file.
    with make_image_only_pdf('1') as pdf:
        raw = pdf.Root.Metadata.read_bytes()
        pdf.Root.Metadata.write(zlib.compress(raw), filter=Name.FlateDecode)
        report = ValidationReport(Flavour.PDFA_1B)
        ctx = ValidationContext(Flavour.PDFA_1B, pdf, report)
        DocumentWalker(ctx, SchemaSet.for_flavour('1b')).walk()
        check_metadata(ctx)
        assert 'ISO_19005_1:6.7.2-2' in rule_ids(report)
        assert check(pdf, '2b').passed is False  # pdfaid:part is 1


def test_pdfaid_prefix_must_be_pdfaid():
    with make_image_only_pdf() as pdf:
        raw = pdf.Root.Metadata.read_bytes().replace(b'pdfaid', b'aid')
        pdf.Root.Metadata.write(raw)
        assert 'ISO_19005_2:6.6.4-4' in rule_ids(check(pdf, '2b'))


_SAMPLE_VALUES = {
    'text': 'x',
    'mimetype': 'application/pdf',
    'langalt': 'x',
    'date': '2020-01-01T00:00:00Z',
    'integer': '1',
    'boolean': 'True',
    'bag': ['x'],
    'seq': ['x'],
    'seq-date': ['2020-01-01T00:00:00Z'],
}


@pytest.mark.parametrize('flavour', ['1b', '2b'])
def test_every_simple_table_property_accepted(flavour, tmp_path):
    """Every unstructured property in the tables is accepted, and by veraPDF."""
    table = tables()['xmp2004' if flavour == '1b' else 'xmp2005']
    with make_image_only_pdf(flavour[0]) as pdf:
        with pdf.open_metadata(set_pikepdf_as_editor=False) as meta:
            for uri, properties in table.items():
                if uri == 'http://www.aiim.org/pdfa/ns/id/':
                    continue
                for name, shape in properties.items():
                    if shape in _SAMPLE_VALUES:
                        meta[f'{{{uri}}}{name}'] = _SAMPLE_VALUES[shape]
        path = save_candidate(pdf, tmp_path / 'out.pdf', flavour[0])
    report = validate_written(path, flavour)
    assert report.passed, report.summary()
    assert_verapdf_agrees(path, flavour)


@pytest.mark.parametrize(
    'key, value',
    [
        ('{http://ns.adobe.com/pdf/1.3/}Trapped', 'False'),
        (f'{{{PHOTOSHOP}}}ColorMode', '3'),
        (f'{{{PHOTOSHOP}}}ICCProfile', 'sRGB IEC61966-2.1'),
        (f'{{{PHOTOSHOP}}}History', 'x'),
        ('{http://ns.adobe.com/xap/1.0/}Advisory', ['x']),
        ('{http://purl.org/dc/elements/1.1/}format', 'x'),
    ],
)
def test_properties_verapdf_rejects_are_denied(key, value, tmp_path):
    """Properties added to XMP after 2005, or with invalid values, are denied."""
    with make_image_only_pdf('2') as pdf:
        with pdf.open_metadata(set_pikepdf_as_editor=False) as meta:
            meta[key] = value
        path = save_candidate(pdf, tmp_path / 'out.pdf', '2')
    assert not validate_written(path, '2b').passed
    assert_verapdf_fails(path, '2b', 'ISO_19005_2:6.6.2.3.1-2')


def test_structured_property_not_approved(tmp_path):
    """The content of structured properties is not checked, so deny them.

    stEvt:changed was added to ResourceEvent after XMP 2005.
    """
    with make_image_only_pdf('2') as pdf:
        replace_xmp(
            pdf,
            b'<rdf:Description rdf:about="">',
            b'<rdf:Description rdf:about=""'
            b' xmlns:xmpMM="http://ns.adobe.com/xap/1.0/mm/"'
            b' xmlns:stEvt="http://ns.adobe.com/xap/1.0/sType/ResourceEvent#">'
            b'<xmpMM:History><rdf:Seq><rdf:li rdf:parseType="Resource">'
            b'<stEvt:action>saved</stEvt:action><stEvt:changed>/</stEvt:changed>'
            b'</rdf:li></rdf:Seq></xmpMM:History>',
        )
        path = save_candidate(pdf, tmp_path / 'out.pdf', '2')
    report = validate_written(path, '2b')
    assert not report.passed
    assert any('History' in f.message for f in report.findings), report.summary()
    assert_verapdf_fails(path, '2b', 'ISO_19005_2:6.6.2.3.1-2')


def test_1b_info_date_without_time_zone_not_approved(tmp_path):
    """Do not approve dates without a time zone in PDF/A-1.

    veraPDF reads an unzoned XMP date in the local time zone of the machine
    running it and an unzoned PDF date as UTC, so its verdict on unzoned
    dates depends on where it runs.
    """
    with make_image_only_pdf('1') as pdf:
        pdf.docinfo[Name.CreationDate] = String('D:20160119123847')
        with pdf.open_metadata(
            set_pikepdf_as_editor=False, update_docinfo=False
        ) as meta:
            meta['xmp:CreateDate'] = '2016-01-19T12:38:47'
        report = check(pdf, '1b')
    assert [(f.rule, f.kind) for f in report.findings] == [
        ('ISO_19005_1:6.7.3-1', 'unsupported')
    ], report.summary()


_RDF_NAMESPACES = (
    'xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#" '
    'xmlns:dc="http://purl.org/dc/elements/1.1/" '
    'xmlns:xmp="http://ns.adobe.com/xap/1.0/" '
    'xmlns:pdfaid="http://www.aiim.org/pdfa/ns/id/"'
)


def _set_rdf_body(pdf: pikepdf.Pdf, body: str, part: str = '2') -> None:
    pdf.Root.Metadata.write(
        (
            '<?xpacket begin="﻿" id="W5M0MpCehiHzreSzNTczkc9d"?>'
            f'<x:xmpmeta xmlns:x="adobe:ns:meta/"><rdf:RDF {_RDF_NAMESPACES}>'
            f'<rdf:Description rdf:about="" pdfaid:part="{part}"'
            ' pdfaid:conformance="B"/>'
            f'{body}</rdf:RDF></x:xmpmeta><?xpacket end="w"?>'
        ).encode()
    )


@pytest.mark.parametrize(
    'body, rule, kind',
    [
        (
            '<rdf:Description rdf:about=""><xmp:Label>a</xmp:Label>'
            '<xmp:Label>b</xmp:Label></rdf:Description>',
            'ISO_19005_2:6.6.2.1-4',
            'violation',
        ),
        (
            '<rdf:Description rdf:about="" rdf:ID="a"/>',
            'ISO_19005_2:6.6.2.1-4',
            'violation',
        ),
        (
            '<xmp:Thing rdf:about=""/>',
            'ISO_19005_2:6.6.2.1-4',
            'violation',
        ),
        (
            '<rdf:Description rdf:about="uuid:1"><xmp:Label>a</xmp:Label>'
            '</rdf:Description>',
            'ISO_19005_2:6.6.2.1-4',
            'unsupported',
        ),
        (
            '<rdf:Description rdf:about=""><dc:title>plain</dc:title>'
            '</rdf:Description>',
            'ISO_19005_2:6.6.2.3.1-2',
            'violation',
        ),
        (
            '<rdf:Description rdf:about="" xmp:CreateDate=" 2020-01-01"/>',
            'ISO_19005_2:6.6.2.3.1-2',
            'violation',
        ),
        (
            '<rdf:Description rdf:about=""><dc:subject><rdf:Bag>'
            '<rdf:li><rdf:Bag><rdf:li>x</rdf:li></rdf:Bag></rdf:li>'
            '</rdf:Bag></dc:subject></rdf:Description>',
            'ISO_19005_2:6.6.2.3.1-2',
            'violation',
        ),
        (
            '<rdf:Description rdf:about=""><xmp:Bogus>x</xmp:Bogus></rdf:Description>',
            'ISO_19005_2:6.6.2.3.1-1',
            'violation',
        ),
    ],
)
def test_strict_rdf_findings(body, rule, kind):
    with make_image_only_pdf() as pdf:
        _set_rdf_body(pdf, body)
        report = check(pdf, '2b')
    assert (rule, kind) in {(f.rule, f.kind) for f in report.findings}, report.summary()


def test_canonical_rdf_body_accepted():
    with make_image_only_pdf() as pdf:
        _set_rdf_body(
            pdf,
            '<rdf:Description rdf:about="" xmp:CreatorTool="tool">'
            '<dc:title><rdf:Alt><rdf:li xml:lang="x-default">T</rdf:li>'
            '<rdf:li xml:lang="en">T</rdf:li></rdf:Alt></dc:title>'
            '<dc:creator><rdf:Seq><rdf:li>A</rdf:li></rdf:Seq></dc:creator>'
            '<xmp:Label/></rdf:Description>',
        )
        report = check(pdf, '2b')
    assert report.passed, report.summary()


def test_malformed_packet_denied():
    with make_image_only_pdf() as pdf:
        replace_xmp(pdf, b'</rdf:RDF>', b'</rdf:RDF><unclosed>')
        assert 'ISO_19005_2:6.6.2.1-4' in rule_ids(check(pdf, '2b'))


def test_pdfaid_read_strictly():
    with make_image_only_pdf() as pdf:
        replace_xmp(pdf, b'>2</pdfaid:part>', b'> 2</pdfaid:part>')
        found = rule_ids(check(pdf, '2b'))
    assert {'ISO_19005_2:6.6.2.3.1-2', 'ISO_19005_2:6.6.4-1'} <= found


def test_1b_info_title_compares_x_default():
    with make_image_only_pdf('1') as pdf:
        _set_rdf_body(
            pdf,
            '<rdf:Description rdf:about=""><dc:title><rdf:Alt>'
            '<rdf:li xml:lang="en">A</rdf:li><rdf:li xml:lang="x-default">B</rdf:li>'
            '</rdf:Alt></dc:title></rdf:Description>',
            part='1',
        )
        for key in list(pdf.docinfo.keys()):
            del pdf.docinfo[key]
        pdf.docinfo[Name.Title] = String('A')
        assert 'ISO_19005_1:6.7.3-2' in rule_ids(check(pdf, '1b'))
        pdf.docinfo[Name.Title] = String('B')
        report = check(pdf, '1b')
        assert report.passed, report.summary()


def test_1b_info_date_before_gregorian_calendar_not_approved():
    with make_image_only_pdf('1') as pdf:
        _set_rdf_body(
            pdf,
            '<rdf:Description rdf:about="" xmp:CreateDate="1500-06-01T00:00:00Z"/>',
            part='1',
        )
        for key in list(pdf.docinfo.keys()):
            del pdf.docinfo[key]
        pdf.docinfo[Name.CreationDate] = String('D:15000601000000Z')
        report = check(pdf, '1b')
    assert [(f.rule, f.kind) for f in report.findings] == [
        ('ISO_19005_1:6.7.3-1', 'unsupported')
    ], report.summary()
