# SPDX-FileCopyrightText: 2026 James R. Barlow
# SPDX-License-Identifier: MPL-2.0

"""Checks that apply to every object of the file, reachable or not."""

from __future__ import annotations

import pytest

pytest.importorskip('jsonschema')

import zlib

from pdfa_samples import (
    assert_verapdf_agrees,
    assert_verapdf_fails,
    make_image_only_pdf,
    save_candidate,
)

import pikepdf
from pikepdf import Dictionary, Name, String
from pikepdf.pdfa import Flavour, validate
from pikepdf.pdfa._context import ValidationContext
from pikepdf.pdfa._cos import check_objects
from pikepdf.pdfa._report import ValidationReport

DEPTH = 70
BIG_REAL = b'1' + b'0' * 39 + b'.0'


def rule_ids(report: ValidationReport) -> set[str]:
    return {f.rule for f in report.findings}


def check(pdf: pikepdf.Pdf, tmp_path, part: str = '2') -> ValidationReport:
    path = save_candidate(pdf, tmp_path / 'c.pdf', part)
    return validate(path, f'{part}b')


def _nested(inner: bytes, depth: int = DEPTH) -> bytes:
    return b'[' * depth + inner + b']' * depth


# --- implementation limits ---------------------------------------------------------


@pytest.mark.parametrize('part', ['1', '2'])
def test_deeply_nested_object_denied(tmp_path, part):
    with make_image_only_pdf(part) as pdf:
        pdf.Root.StructTreeRoot = pdf.make_indirect(
            Dictionary(
                Type=Name.StructTreeRoot, K=pikepdf.Object.parse(_nested(BIG_REAL))
            )
        )
        report = check(pdf, tmp_path, part)
    assert 'pikepdf:depth' in rule_ids(report), report.summary()
    rule = 'ISO_19005_1:6.1.12-2' if part == '1' else 'ISO_19005_2:6.1.13-2'
    assert_verapdf_fails(tmp_path / 'c.pdf', f'{part}b', rule)


def test_deeply_nested_operand_denied(tmp_path):
    with make_image_only_pdf() as pdf:
        pdf.pages[0].Contents = pdf.make_stream(
            b'/P << /A ' + _nested(BIG_REAL) + b' >> BDC EMC'
        )
        report = check(pdf, tmp_path)
    assert 'pikepdf:depth' in rule_ids(report), report.summary()
    assert_verapdf_fails(tmp_path / 'c.pdf', '2b', 'ISO_19005_2:6.1.13-2')


def test_deeply_nested_dash_array_denied(tmp_path):
    with make_image_only_pdf() as pdf:
        pdf.pages[0].Contents = pdf.make_stream(
            b'q ' + _nested(BIG_REAL) + b' 0 d 0 0 10 10 re S Q'
        )
        report = check(pdf, tmp_path)
    assert not report.passed
    assert_verapdf_fails(tmp_path / 'c.pdf', '2b', 'ISO_19005_2:6.1.13-2')


@pytest.mark.parametrize('dash', [b'[[1]] 0', b'[1 (x)] 0', b'[1] 0.5'])
def test_dash_operands_type_checked(tmp_path, dash):
    with make_image_only_pdf() as pdf:
        pdf.pages[0].Contents = pdf.make_stream(dash + b' d')
        report = check(pdf, tmp_path)
    if dash == b'[1] 0.5':
        assert report.passed, report.summary()
    else:
        assert 'pikepdf:content-operands' in rule_ids(report), report.summary()


# --- every stream --------------------------------------------------------------------


def _indexed_lookup(pdf: pikepdf.Pdf, **keys) -> None:
    lookup = pdf.make_stream(b'\x00\x00\xff', **keys)
    pdf.pages[0].Resources.ColorSpace = Dictionary(
        C0=pikepdf.Array([Name.Indexed, Name.DeviceRGB, 0, lookup])
    )
    pdf.pages[0].Contents = pdf.make_stream(
        b'/C0 cs 0 sc 0 0 10 10 re f q 612 0 0 792 0 0 cm /Im0 Do Q'
    )


def _decode_parms_stream(pdf: pikepdf.Pdf, **keys) -> None:
    image = pdf.pages[0].Resources.XObject.Im0
    image.DecodeParms = Dictionary(G=pdf.make_stream(b'x', **keys))


def _info_stream(pdf: pikepdf.Pdf, **keys) -> None:
    pdf.trailer.Info = pdf.make_indirect(Dictionary(Foo=pdf.make_stream(b'x', **keys)))


CARRIERS = [_indexed_lookup, _decode_parms_stream, _info_stream]


@pytest.mark.parametrize('carrier', CARRIERS)
@pytest.mark.parametrize(
    'part, rule', [('1', 'ISO_19005_1:6.1.7-3'), ('2', 'ISO_19005_2:6.1.7.1-3')]
)
def test_external_stream_keys_denied_everywhere(tmp_path, carrier, part, rule):
    with make_image_only_pdf(part) as pdf:
        carrier(pdf, F=String('external.bin'))
        report = check(pdf, tmp_path, part)
    assert rule in rule_ids(report), report.summary()
    assert_verapdf_fails(tmp_path / 'c.pdf', f'{part}b', rule)


@pytest.mark.parametrize('key', ['/FFilter', '/FDecodeParms'])
def test_other_external_stream_keys_denied(tmp_path, key):
    with make_image_only_pdf() as pdf:
        _info_stream(pdf, **{key[1:]: Name.FlateDecode})
        report = check(pdf, tmp_path)
    assert 'ISO_19005_2:6.1.7.1-3' in rule_ids(report), report.summary()


@pytest.mark.parametrize(
    'part, filters, rule',
    [
        ('2', Name('/FooDecode'), 'ISO_19005_2:6.1.7.2-1'),
        ('1', Name('/FooDecode'), 'pikepdf:filter'),
        ('2', Name.Fl, 'ISO_19005_2:6.1.7.2-1'),
        ('2', String('FlateDecode'), 'pikepdf:filter'),
    ],
)
def test_stream_filters_denied_everywhere(tmp_path, part, filters, rule):
    with make_image_only_pdf(part) as pdf:
        _info_stream(pdf, Filter=filters)
        report = check(pdf, tmp_path, part)
    assert rule in rule_ids(report), report.summary()
    if rule.startswith('ISO'):
        assert_verapdf_fails(tmp_path / 'c.pdf', f'{part}b', rule)


def test_permitted_filters_on_unreached_stream_approved(tmp_path):
    with make_image_only_pdf() as pdf:
        _info_stream(pdf, Filter=pikepdf.Array([Name.ASCIIHexDecode]))
        pdf.trailer.Info.Foo.write(b'78', filter=Name.ASCIIHexDecode)
        pdf.trailer.Info.Bar = pdf.make_stream(
            zlib.compress(b'x'), Filter=Name.FlateDecode
        )
        report = check(pdf, tmp_path)
    assert report.passed, report.summary()
    assert_verapdf_agrees(tmp_path / 'c.pdf', '2b')


def test_walked_stream_is_reported_once(tmp_path):
    with make_image_only_pdf() as pdf:
        pdf.pages[0].Contents.F = String('external.bin')
        report = check(pdf, tmp_path)
    found = [f for f in report.findings if f.rule == 'ISO_19005_2:6.1.7.1-3']
    assert len(found) == 1, report.summary()


@pytest.mark.parametrize(
    'flavour, filters, rule',
    [
        ('2b', Name.LZWDecode, 'ISO_19005_2:6.1.7.2-1'),
        ('2b', pikepdf.Array([Name.FlateDecode, Name.Crypt]), 'ISO_19005_2:6.1.7.2-1'),
        ('1b', Name.LZWDecode, 'ISO_19005_1:6.1.10-1'),
        ('1b', Name.Crypt, 'pikepdf:filter'),
    ],
)
def test_forbidden_filters_in_memory(flavour, filters, rule):
    # qpdf decodes LZWDecode and Crypt when saving, so check an open file
    with make_image_only_pdf() as pdf:
        _info_stream(pdf, Filter=filters)
        report = ValidationReport(Flavour(flavour))
        check_objects(ValidationContext(Flavour(flavour), pdf, report))
    assert rule_ids(report) == {rule}


# --- embedded and associated files -------------------------------------------------


def _structure_with_embedded_file(pdf: pikepdf.Pdf) -> None:
    embedded = pdf.make_stream(
        b'x', Type=Name.EmbeddedFile, Subtype=Name('/text#2Fplain')
    )
    filespec = pdf.make_indirect(
        Dictionary(
            Type=Name.Filespec,
            F=String('a.txt'),
            UF=String('a.txt'),
            AFRelationship=Name.Supplement,
            EF=Dictionary(F=embedded),
        )
    )
    root = pdf.make_indirect(Dictionary(Type=Name.StructTreeRoot))
    element = pdf.make_indirect(
        Dictionary(Type=Name.StructElem, S=Name.Formula, P=root, AF=[filespec])
    )
    root.K = element
    pdf.Root.StructTreeRoot = root
    pdf.Root.MarkInfo = Dictionary(Marked=True)


@pytest.mark.parametrize(
    'part, rules',
    [
        ('1', {'ISO_19005_1:6.1.11-1', 'pikepdf:associated-files'}),
        ('2', {'pikepdf:embedded-file', 'pikepdf:associated-files'}),
    ],
)
def test_embedded_file_in_structure_denied(tmp_path, part, rules):
    with make_image_only_pdf(part) as pdf:
        _structure_with_embedded_file(pdf)
        report = check(pdf, tmp_path, part)
    assert rules <= rule_ids(report), report.summary()
    if part == '1':
        assert_verapdf_fails(tmp_path / 'c.pdf', '1b', 'ISO_19005_1:6.1.11-1')
    else:
        assert_verapdf_fails(tmp_path / 'c.pdf', '2b', 'ISO_19005_2:6.8-5')
