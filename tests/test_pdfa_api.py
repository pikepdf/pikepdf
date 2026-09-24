# SPDX-FileCopyrightText: 2026 James R. Barlow
# SPDX-License-Identifier: MPL-2.0

"""Public API of pikepdf.pdfa: flavours, reports, verdicts and the engine."""

from __future__ import annotations

import pytest

pytest.importorskip('jsonschema')

from io import BytesIO

from pdfa_samples import make_image_only_pdf

import pikepdf
from pikepdf import Dictionary, Name
from pikepdf.pdfa import (
    Finding,
    Flavour,
    PdfaError,
    Report,
    ValidationReport,
    _engine,
    resolve_save_kwargs,
    validate_written,
)
from pikepdf.pdfa._writemodel import WriteModel


def set_interpolate(pdf: pikepdf.Pdf) -> None:
    pdf.pages[0].Resources.XObject.Im0.Interpolate = True


def add_pattern(pdf: pikepdf.Pdf) -> None:
    # On a page of its own: the walker does not look inside a resource
    # dictionary it cannot check, which would hide findings on page 1.
    pattern = pdf.make_stream(
        b'0 0 10 10 re f',
        Type=Name.Pattern,
        PatternType=1,
        PaintType=1,
        TilingType=1,
        BBox=[0, 0, 10, 10],
        XStep=10,
        YStep=10,
        Resources=Dictionary(),
    )
    page = Dictionary(
        Type=Name.Page,
        MediaBox=[0, 0, 612, 792],
        Resources=Dictionary(Pattern=Dictionary(P0=pattern)),
        Contents=pdf.make_stream(b''),
    )
    pdf.pages.append(pikepdf.Page(page))


MUTATIONS = {
    'pass': [],
    'fail': [set_interpolate],
    'not_checked': [add_pattern],
    'both': [set_interpolate, add_pattern],
}


def sample(kind: str, part: str = '2') -> pikepdf.Pdf:
    pdf = make_image_only_pdf(part)
    for mutate in MUTATIONS[kind]:
        mutate(pdf)
    return pdf


def save_as_validated(pdf: pikepdf.Pdf, path, flavour: Flavour):
    pdf.save(path, **resolve_save_kwargs(flavour))
    return path


def static_bytes(pdf: pikepdf.Pdf) -> bytes:
    buffer = BytesIO()
    pdf.save(buffer, static_id=True, fix_metadata_version=False)
    return buffer.getvalue()


class TestFlavour:
    def test_from_string(self):
        assert Flavour('2b') is Flavour.PDFA_2B

    def test_from_member(self):
        assert Flavour(Flavour.PDFA_2B) is Flavour.PDFA_2B

    @pytest.mark.parametrize('value', ['1b', '2b', '3b'])
    def test_str_and_format(self, value):
        f = Flavour(value)
        assert str(f) == value
        assert f'{f}' == value

    def test_part_and_spec(self):
        assert Flavour('1b').part == 1
        assert Flavour('3b').part == 3
        assert Flavour('2b').spec == 'ISO_19005_2'

    @pytest.mark.parametrize('value', ['4b', '2a', '', 'pdfa-2b'])
    def test_bad_value(self, value):
        with pytest.raises(ValueError):
            Flavour(value)


class TestReport:
    def test_alias(self):
        assert ValidationReport is Report

    def test_empty_report(self):
        report = Report(Flavour.PDFA_2B)
        assert report.verdict == 'pass'
        assert report.passed
        assert report.save_kwargs == {}
        assert report.output_intent is None
        assert 'pass' in report.summary()

    def test_verdict_from_kinds(self):
        v = Finding('r', 'w', 'm', 'violation')
        u = Finding('r', 'w', 'm', 'unsupported')
        assert Report(Flavour.PDFA_2B, [u]).verdict == 'not_checked'
        assert Report(Flavour.PDFA_2B, [v]).verdict == 'fail'
        assert Report(Flavour.PDFA_2B, [u, v]).verdict == 'fail'
        assert not Report(Flavour.PDFA_2B, [u]).passed

    def test_summary_limit(self):
        findings = [Finding('r', f'w{i}', 'm') for i in range(5)]
        summary = Report(Flavour.PDFA_2B, findings).summary(limit=2)
        assert 'fail' in summary
        assert 'w1' in summary
        assert 'w2' not in summary
        assert '3 more' in summary


class TestVerdicts:
    @pytest.mark.parametrize(
        'kind, verdict',
        [
            ('pass', 'pass'),
            ('fail', 'fail'),
            ('not_checked', 'not_checked'),
            ('both', 'fail'),
        ],
    )
    def test_verdict(self, kind, verdict, tmp_path):
        flavour = Flavour.PDFA_2B
        with sample(kind) as pdf:
            path = save_as_validated(pdf, tmp_path / 'c.pdf', flavour)
        report = validate_written(path, flavour)
        assert report.verdict == verdict, report.summary()
        assert report.passed == (verdict == 'pass')
        assert verdict in report.summary()
        assert set(report.violations) | set(report.unsupported) == set(report.findings)
        assert len(report.violations) + len(report.unsupported) == len(report.findings)
        assert all(f.kind == 'violation' for f in report.violations)
        assert all(f.kind == 'unsupported' for f in report.unsupported)
        if kind == 'not_checked':
            assert report.findings
            assert all(f.kind == 'unsupported' for f in report.findings)
        if kind in ('fail', 'both'):
            assert report.violations
        if kind == 'both':
            assert report.unsupported
        for finding in report.findings:
            assert not finding.rule.startswith('ocrmypdf:')
            assert not finding.rule.startswith('schema:')

    def test_validate_written_records_save_kwargs(self, tmp_path):
        flavour = Flavour.PDFA_2B
        with sample('pass') as pdf:
            path = save_as_validated(pdf, tmp_path / 'c.pdf', flavour)
        kwargs = {'compress_streams': True}
        report = validate_written(path, flavour, kwargs)
        assert report.save_kwargs == kwargs

    def test_output_intent(self):
        with sample('pass') as pdf:
            report = _engine.run(pdf, Flavour.PDFA_2B)
        assert report.output_intent == 'RGB'


class TestPdfaError:
    def test_carries_report(self):
        report = Report(Flavour.PDFA_2B, [Finding('r', 'somewhere', 'bad thing')])
        err = PdfaError(report)
        assert err.report is report
        assert report.summary() in str(err)
        assert isinstance(err, Exception)


class TestEngineRun:
    @pytest.mark.parametrize('kind', ['pass', 'fail', 'not_checked', 'both'])
    @pytest.mark.parametrize('part', ['1', '2'])
    def test_open_pdf_matches_written(self, kind, part, tmp_path):
        flavour = Flavour(f'{part}b')
        with sample(kind, part) as pdf:
            path = save_as_validated(pdf, tmp_path / 'c.pdf', flavour)
        written = validate_written(path, flavour)
        with pikepdf.open(path, inherit_page_attributes=False) as pdf:
            in_memory = _engine.run(pdf, flavour)
        assert in_memory.findings == written.findings
        assert in_memory.verdict == written.verdict
        assert in_memory.output_intent == written.output_intent

    def test_explicit_model(self):
        with sample('fail') as pdf:
            default = _engine.run(pdf, Flavour.PDFA_2B)
            identity = _engine.run(pdf, Flavour.PDFA_2B, WriteModel.identity())
        assert default.findings == identity.findings

    def test_accepts_string_flavour(self):
        with sample('pass') as pdf:
            report = _engine.run(pdf, '2b')
        assert report.flavour is Flavour.PDFA_2B
        assert report.passed

    def test_save_kwargs_recorded(self):
        with sample('pass') as pdf:
            report = _engine.run(pdf, '2b', save_kwargs={'linearize': True})
        assert report.save_kwargs == {'linearize': True}

    @pytest.mark.parametrize('kind', ['pass', 'fail', 'not_checked'])
    def test_under_explicit_conversion(self, kind):
        with sample(kind) as pdf:
            baseline = _engine.run(pdf, Flavour.PDFA_2B)
            with pikepdf.explicit_conversion():
                explicit = _engine.run(pdf, Flavour.PDFA_2B)
        assert explicit.findings == baseline.findings

    @pytest.mark.parametrize('kind', ['pass', 'fail', 'not_checked'])
    def test_explicit_conversion_mode_pdf(self, kind, tmp_path):
        flavour = Flavour.PDFA_2B
        with sample(kind) as pdf:
            path = save_as_validated(pdf, tmp_path / 'c.pdf', flavour)
        with pikepdf.open(path) as pdf:
            baseline = _engine.run(pdf, flavour)
        with pikepdf.open(path, conversion_mode='explicit') as pdf:
            explicit = _engine.run(pdf, flavour)
        assert explicit.findings == baseline.findings

    @pytest.mark.parametrize('kind', ['pass', 'fail', 'both'])
    def test_does_not_mutate(self, kind):
        with sample(kind) as pdf:
            before = static_bytes(pdf)
            _engine.run(pdf, Flavour.PDFA_2B)
            _engine.run(pdf, Flavour.PDFA_1B)
            after = static_bytes(pdf)
        assert before == after

    def test_internal_error_becomes_unsupported(self, monkeypatch):
        def boom(ctx):
            raise RuntimeError('kaboom')

        monkeypatch.setattr(_engine, 'check_document', boom)
        with sample('pass') as pdf:
            report = _engine.run(pdf, Flavour.PDFA_2B)
        assert report.verdict == 'not_checked'
        (finding,) = report.findings
        assert finding.rule == 'pikepdf:internal'
        assert 'kaboom' in finding.message
