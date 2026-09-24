# SPDX-FileCopyrightText: 2026 James R. Barlow
# SPDX-License-Identifier: MPL-2.0

"""How the validator reports dictionary keys its role schemas do not list.

PDF permits private and future keys, so an unlisted key is reported as
unsupported (the validator does not know what it means), not as a PDF/A
violation. Only dictionaries that PDF/A itself closes (``x-closed``) report
unlisted keys as violations.
"""

from __future__ import annotations

import pytest

pytest.importorskip('jsonschema')

from jsonschema import Draft202012Validator
from pdfa_samples import make_image_only_pdf, save_image_only_pdf

import pikepdf
from pikepdf import Array, Dictionary, Name, String
from pikepdf.pdfa import Flavour, validate
from pikepdf.pdfa._context import ValidationContext
from pikepdf.pdfa._report import ValidationReport
from pikepdf.pdfa._schemas import SchemaSet, unrecognized_keys
from pikepdf.pdfa._walker import DocumentWalker

PRINT = 4
RECT = [100, 100, 200, 150]


def walk(pdf: pikepdf.Pdf, flavour: str = '2b') -> ValidationReport:
    fl = Flavour(flavour)
    report = ValidationReport(fl)
    ctx = ValidationContext(fl, pdf, report)
    DocumentWalker(ctx, SchemaSet.for_flavour(fl)).walk()
    return report


def appearance(pdf: pikepdf.Pdf) -> pikepdf.Stream:
    return pdf.make_stream(
        b'0 0 1 rg 0 0 100 50 re f',
        Type=Name.XObject,
        Subtype=Name.Form,
        BBox=[0, 0, 100, 50],
        Resources=Dictionary(),
    )


def add_annot(pdf: pikepdf.Pdf, annot: Dictionary) -> pikepdf.Object:
    annot = pdf.make_indirect(annot)
    annot.P = pdf.pages[0].obj
    pdf.pages[0].obj.Annots = Array([annot])
    return annot


def link(**keys) -> Dictionary:
    entries = dict(
        Type=Name.Annot,
        Subtype=Name.Link,
        Rect=RECT,
        F=PRINT,
        Border=[0, 0, 0],
        A=Dictionary(S=Name.URI, URI=String('https://pikepdf.readthedocs.io/')),
    )
    entries.update(keys)
    return Dictionary(**entries)


# --- jsonschema message format -------------------------------------------------


@pytest.mark.parametrize('keyword', ['additionalProperties', 'unevaluatedProperties'])
@pytest.mark.parametrize(
    'instance, expected',
    [
        ({'/A': 1, '/Foo': 1}, ['/Foo']),
        ({'/A': 1, '/Foo': 1, '/Bar': 2}, ['/Bar', '/Foo']),
        ({"/B'x": 1}, ["/B'x"]),
        ({'/B"x': 1, '/Foo': 1}, ['/B"x', '/Foo']),
    ],
)
def test_unrecognized_keys_pins_jsonschema_message(keyword, instance, expected):
    """Fails if a jsonschema upgrade changes the unexpected-properties message."""
    schema = {
        'type': 'object',
        'allOf': [{'properties': {'/A': {}}}],
        keyword: False,
    }
    if keyword == 'additionalProperties':
        schema = {'type': 'object', 'properties': {'/A': {}}, keyword: False}
    (error,) = Draft202012Validator(schema).iter_errors(instance)
    assert sorted(unrecognized_keys(error)) == sorted(expected)


# --- open dictionaries: unlisted keys are unsupported --------------------------


def test_page_procset_passes():
    with make_image_only_pdf() as pdf:
        pdf.pages[0].obj.ProcSet = Array([Name.PDF, Name.ImageC])
        report = walk(pdf)
        assert report.findings == [], report.summary()


@pytest.mark.parametrize('part', ['1', '2', '3'])
def test_page_procset_passes_on_file(tmp_path, part):
    def add(pdf):
        pdf.pages[0].obj.ProcSet = Array([Name.PDF, Name.ImageC])

    path = save_image_only_pdf(tmp_path / 'c.pdf', part, add)
    report = validate(path, f'{part}b')
    assert report.passed, report.summary()


def test_page_tree_procset_passes():
    with make_image_only_pdf() as pdf:
        pdf.Root.Pages.ProcSet = Array([Name.PDF])
        assert walk(pdf).findings == []


def test_page_unknown_key_is_unsupported():
    with make_image_only_pdf() as pdf:
        pdf.pages[0].obj.Foo = 1
        report = walk(pdf)
    assert not report.passed
    assert len(report.findings) == 1, report.summary()
    (finding,) = report.findings
    assert finding.kind == 'unsupported'
    assert finding.rule == 'pikepdf:schema-Page'
    assert '/Foo' in finding.message
    assert 'not checked' in finding.message


def test_page_unknown_keys_named_together():
    with make_image_only_pdf() as pdf:
        pdf.pages[0].obj.Foo = 1
        pdf.pages[0].obj.Bar = 2
        report = walk(pdf)
    (finding,) = report.findings
    assert finding.kind == 'unsupported'
    assert '/Foo' in finding.message
    assert '/Bar' in finding.message


def test_link_annot_unknown_key_is_unsupported():
    """LinkAnnot closes its keys with unevaluatedProperties."""
    with make_image_only_pdf() as pdf:
        add_annot(pdf, link(Foo=1))
        report = walk(pdf)
    assert not report.passed
    assert [(f.rule, f.kind) for f in report.findings] == [
        ('pikepdf:schema-LinkAnnot', 'unsupported')
    ], report.summary()
    assert '/Foo' in report.findings[0].message


def test_explicitly_forbidden_key_stays_violation():
    with make_image_only_pdf() as pdf:
        pdf.pages[0].obj.AA = Dictionary()
        report = walk(pdf)
    assert [(f.rule, f.kind) for f in report.findings] == [
        ('ISO_19005_2:6.5.2-2', 'violation')
    ]


def test_forbidden_key_beside_unknown_key():
    with make_image_only_pdf() as pdf:
        pdf.pages[0].obj.AA = Dictionary()
        pdf.pages[0].obj.Foo = 1
        report = walk(pdf)
    assert {(f.rule, f.kind) for f in report.findings} == {
        ('ISO_19005_2:6.5.2-2', 'violation'),
        ('pikepdf:schema-Page', 'unsupported'),
    }


def test_open_additional_properties_schema_is_unsupported():
    """Custom document information entries of an unexpected type."""
    with make_image_only_pdf() as pdf:
        pdf.trailer.Info = pdf.make_indirect(Dictionary(Foo=42))
        report = walk(pdf)
    assert [(f.rule, f.kind) for f in report.findings] == [
        ('pikepdf:schema-Info', 'unsupported')
    ], report.summary()


# --- closed dictionaries: unlisted keys are violations -------------------------


@pytest.mark.parametrize(
    'part, rule',
    [
        ('1', 'ISO_19005_1:6.5.3-4'),
        ('2', 'ISO_19005_2:6.3.3-2'),
        ('3', 'ISO_19005_3:6.3.3-2'),
    ],
)
def test_appearance_dict_is_closed(part, rule):
    with make_image_only_pdf(part) as pdf:
        normal = appearance(pdf)
        add_annot(pdf, link(AP=Dictionary(N=normal, D=normal)))
        report = walk(pdf, f'{part}b')
    assert [(f.rule, f.kind) for f in report.findings] == [(rule, 'violation')], (
        report.summary()
    )


def test_closed_roles():
    """The roles whose unlisted keys PDF/A itself forbids."""
    schemas = SchemaSet.for_flavour('2b')
    closed = {
        role
        for role in schemas.roles()
        if any(node.get('x-closed') for node in schemas._nodes(role))
    }
    assert closed == {'AppearanceDict'}
