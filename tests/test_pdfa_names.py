# SPDX-FileCopyrightText: 2026 James R. Barlow
# SPDX-License-Identifier: MPL-2.0

"""Name trees and named destinations in the PDF/A validator."""

from __future__ import annotations

import pytest

pytest.importorskip('jsonschema')

from collections.abc import Callable  # noqa: E402
from pathlib import Path  # noqa: E402

from conftest import verapdf_failed_rules  # noqa: E402
from pdfa_samples import (  # noqa: E402
    assert_verapdf_agrees,
    make_simple_truetype_pdf,
    save_candidate,
)

import pikepdf  # noqa: E402
from pikepdf import Array, Dictionary, Name, String  # noqa: E402
from pikepdf.pdfa import prepare, validate_written  # noqa: E402
from pikepdf.pdfa._context import MAX_DEPTH  # noqa: E402
from pikepdf.pdfa._report import ValidationReport  # noqa: E402

PARTS = ['1', '2', '3']


def check(pdf: pikepdf.Pdf, path: Path, part: str = '2') -> ValidationReport:
    save_candidate(pdf, path, part)
    return validate_written(path, f'{part}b')


def assert_approved(pdf: pikepdf.Pdf, path: Path, part: str = '2') -> None:
    report = check(pdf, path, part)
    assert report.passed, report.summary()
    assert_verapdf_agrees(path, f'{part}b')


def assert_denied(
    pdf: pikepdf.Pdf,
    path: Path,
    rule: str,
    part: str = '2',
    *,
    kind: str = 'violation',
    verapdf_fails: bool = False,
) -> ValidationReport:
    report = check(pdf, path, part)
    assert rule in {f.rule for f in report.findings if f.kind == kind}, report.summary()
    if verapdf_fails:
        failed = verapdf_failed_rules(path, f'{part}b')
        if failed is not None:
            assert rule in failed, failed
    return report


def _page(pdf: pikepdf.Pdf) -> pikepdf.Dictionary:
    return pdf.pages[0].obj


# --- named destinations --------------------------------------------------------

DESTINATIONS: dict[str, Callable[[pikepdf.Pdf], pikepdf.Object]] = {
    'xyz': lambda pdf: Array([_page(pdf), Name.XYZ, 0, 600, 0]),
    'null-page': lambda pdf: Array([None, Name.XYZ, 0, 600, None]),
    'integer-page': lambda pdf: Array([0, Name.Fit]),
    'fitr': lambda pdf: Array([_page(pdf), Name.FitR, 0, 0, 100, 100]),
    'dict': lambda pdf: Dictionary(D=Array([_page(pdf), Name.Fit])),
    'indirect': lambda pdf: pdf.make_indirect(Array([_page(pdf), Name.FitH, None])),
    'dict-indirect-d': lambda pdf: Dictionary(
        D=pdf.make_indirect(Array([_page(pdf), Name.FitBV, 10]))
    ),
}


@pytest.mark.parametrize('part', PARTS)
@pytest.mark.parametrize('kind', DESTINATIONS)
def test_dests_name_tree(tmp_path, part, kind):
    pdf = make_simple_truetype_pdf(part)
    destination = DESTINATIONS[kind](pdf)
    pdf.Root.Names = Dictionary(
        Dests=Dictionary(Names=Array([String('A1'), destination]))
    )
    assert_approved(pdf, tmp_path / 'c.pdf', part)


@pytest.mark.parametrize('part', PARTS)
@pytest.mark.parametrize('kind', ['xyz', 'null-page', 'dict', 'indirect'])
def test_catalog_dests(tmp_path, part, kind):
    pdf = make_simple_truetype_pdf(part)
    pdf.Root.Dests = Dictionary(A1=DESTINATIONS[kind](pdf))
    assert_approved(pdf, tmp_path / 'c.pdf', part)


def test_dests_name_tree_with_kids(tmp_path):
    pdf = make_simple_truetype_pdf()
    leaves = [
        pdf.make_indirect(
            Dictionary(
                Names=Array([String(key), Array([_page(pdf), Name.Fit])]),
                Limits=Array([String(key), String(key)]),
            )
        )
        for key in ('A', 'B')
    ]
    middle = pdf.make_indirect(
        Dictionary(Kids=Array(leaves), Limits=Array([String('A'), String('B')]))
    )
    pdf.Root.Names = Dictionary(Dests=pdf.make_indirect(Dictionary(Kids=[middle])))
    assert_approved(pdf, tmp_path / 'c.pdf')


BAD_DESTINATIONS: dict[str, Callable[[pikepdf.Pdf], pikepdf.Object]] = {
    'string': lambda pdf: String('x'),
    'fit-type': lambda pdf: Array([_page(pdf), Name.Bogus]),
    'too-short': lambda pdf: Array([_page(pdf)]),
    'page-is-name': lambda pdf: Array([Name.Page, Name.Fit]),
    'coordinate': lambda pdf: Array([_page(pdf), Name.FitH, String('x')]),
    'dict-without-d': lambda pdf: Dictionary(S=Name.GoTo),
    'dict-d-string': lambda pdf: Dictionary(D=String('x')),
    'indirect-d-bad': lambda pdf: Dictionary(
        D=pdf.make_indirect(Array([_page(pdf), Name.Bogus]))
    ),
}


@pytest.mark.parametrize('kind', BAD_DESTINATIONS)
def test_dests_bad_values(tmp_path, kind):
    pdf = make_simple_truetype_pdf()
    pdf.Root.Names = Dictionary(
        Dests=Dictionary(Names=Array([String('A1'), BAD_DESTINATIONS[kind](pdf)]))
    )
    report = check(pdf, tmp_path / 'c.pdf')
    assert not report.passed
    assert all(f.rule.startswith('pikepdf:') for f in report.findings), report.summary()


@pytest.mark.parametrize('kind', ['string', 'fit-type', 'dict-without-d'])
def test_catalog_dests_bad_values(tmp_path, kind):
    pdf = make_simple_truetype_pdf()
    pdf.Root.Dests = Dictionary(A1=BAD_DESTINATIONS[kind](pdf))
    report = check(pdf, tmp_path / 'c.pdf')
    assert not report.passed, report.summary()


# --- malformed name trees ----------------------------------------------------------


def _dests_tree(pdf: pikepdf.Pdf, node: pikepdf.Object) -> None:
    pdf.Root.Names = Dictionary(Dests=node)


@pytest.mark.parametrize(
    'names',
    [
        pytest.param(lambda pdf: String('x'), id='not-array'),
        pytest.param(lambda pdf: Array([String('A')]), id='odd'),
        pytest.param(
            lambda pdf: Array([Name.A, Array([_page(pdf), Name.Fit])]), id='name-key'
        ),
    ],
)
def test_dests_malformed_names(tmp_path, names):
    pdf = make_simple_truetype_pdf()
    _dests_tree(pdf, Dictionary(Names=names(pdf)))
    report = check(pdf, tmp_path / 'c.pdf')
    assert not report.passed
    assert all(f.rule.startswith('pikepdf:') for f in report.findings), report.summary()


def test_dests_kids_cycle(tmp_path):
    # veraPDF accepts a cycle; every node is still checked once
    pdf = make_simple_truetype_pdf()
    leaf = pdf.make_indirect(
        Dictionary(Names=Array([String('A'), Array([_page(pdf), Name.Bogus])]))
    )
    root = pdf.make_indirect(Dictionary(Kids=Array([leaf])))
    leaf.Kids = Array([root])
    _dests_tree(pdf, root)
    report = check(pdf, tmp_path / 'c.pdf')
    assert 'pikepdf:schema-Destination' in {f.rule for f in report.findings}


def test_dests_kids_too_deep(tmp_path):
    pdf = make_simple_truetype_pdf()
    node = pdf.make_indirect(
        Dictionary(Names=Array([String('A'), Array([_page(pdf), Name.Fit])]))
    )
    for _ in range(MAX_DEPTH + 1):
        node = pdf.make_indirect(Dictionary(Kids=Array([node])))
    _dests_tree(pdf, node)
    assert_denied(pdf, tmp_path / 'c.pdf', 'pikepdf:depth', kind='unsupported')


# --- alternate presentations and document-level JavaScript -----------------------------


def _with_alternate_presentations(part: str) -> pikepdf.Pdf:
    pdf = make_simple_truetype_pdf(part)
    pdf.Root.Names = Dictionary(AlternatePresentations=Dictionary(Names=Array()))
    return pdf


@pytest.mark.parametrize('part', ['2', '3'])
def test_alternate_presentations_denied(tmp_path, part):
    assert_denied(
        _with_alternate_presentations(part),
        tmp_path / 'c.pdf',
        f'ISO_19005_{part}:6.10-1',
        part,
        verapdf_fails=True,
    )


@pytest.mark.parametrize('part', PARTS)
def test_alternate_presentations_repaired(tmp_path, part):
    pdf = _with_alternate_presentations(part)
    result = prepare(pdf, f'{part}b')
    assert result.alternate_presentations_removed
    assert '/AlternatePresentations' not in pdf.Root.Names
    assert_approved(pdf, tmp_path / 'c.pdf', part)


def _with_javascript(part: str) -> pikepdf.Pdf:
    pdf = make_simple_truetype_pdf(part)
    action = pdf.make_indirect(
        Dictionary(S=Name.JavaScript, JS=String('app.alert("hi")'))
    )
    pdf.Root.Names = Dictionary(
        JavaScript=Dictionary(Names=Array([String('init'), action]))
    )
    return pdf


@pytest.mark.parametrize(
    'part, rule', [('1', '6.6.1-1'), ('2', '6.5.1-1'), ('3', '6.5.1-1')]
)
def test_document_javascript_denied(tmp_path, part, rule):
    # ISO 19005 forbids JavaScript actions; veraPDF 1.30 does not look for
    # them in the /JavaScript name tree, so this is not a differential case.
    assert_denied(
        _with_javascript(part), tmp_path / 'c.pdf', f'ISO_19005_{part}:{rule}', part
    )


@pytest.mark.parametrize('part', PARTS)
def test_document_javascript_repaired(tmp_path, part):
    pdf = _with_javascript(part)
    result = prepare(pdf, f'{part}b')
    assert result.document_javascript_removed
    assert '/JavaScript' not in pdf.Root.Names
    assert_approved(pdf, tmp_path / 'c.pdf', part)


def test_repairs_leave_other_names(tmp_path):
    pdf = _with_javascript('2')
    pdf.Root.Names.AlternatePresentations = Dictionary(Names=Array())
    pdf.Root.Names.Dests = Dictionary(
        Names=Array([String('A1'), Array([_page(pdf), Name.Fit])])
    )
    prepare(pdf, '2b')
    assert set(pdf.Root.Names.keys()) == {'/Dests'}
    again = prepare(pdf, '2b')
    assert not again.alternate_presentations_removed
    assert not again.document_javascript_removed


# --- named appearance streams ----------------------------------------------------------


def _with_named_appearance(part: str, **extra) -> pikepdf.Pdf:
    pdf = make_simple_truetype_pdf(part)
    form = pdf.make_stream(
        b'0 0 m 10 10 l S',
        Type=Name.XObject,
        Subtype=Name.Form,
        BBox=[0, 0, 10, 10],
        **extra,
    )
    pdf.Root.Names = Dictionary(AP=Dictionary(Names=Array([String('A'), form])))
    return pdf


@pytest.mark.parametrize('part', PARTS)
def test_named_appearance_streams(tmp_path, part):
    assert_approved(_with_named_appearance(part), tmp_path / 'c.pdf', part)


def test_named_appearance_stream_checked(tmp_path):
    # /PS is forbidden whatever its value
    pdf = _with_named_appearance('2', PS=Name.Whatever)
    assert_denied(pdf, tmp_path / 'c.pdf', 'ISO_19005_2:6.2.9-1')
