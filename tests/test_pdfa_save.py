# SPDX-FileCopyrightText: 2026 James R. Barlow
# SPDX-License-Identifier: MPL-2.0

"""Tests of pikepdf.pdfa.save, which prepares, writes and revalidates."""

from __future__ import annotations

import pytest

pytest.importorskip('jsonschema')

import os
from io import BytesIO

from pdfa_samples import make_image_only_pdf

import pikepdf
from pikepdf import Array, Dictionary, Name
from pikepdf.pdfa import (
    Flavour,
    PdfaError,
    PrepareResult,
    Report,
    check,
    prepare,
    resolve_save_kwargs,
    save,
    validate_written,
)

FLAVOURS = ['1b', '2b', '3b']


def set_interpolate(pdf: pikepdf.Pdf) -> None:
    pdf.pages[0].Resources.XObject.Im0.Interpolate = True


def add_lzw_dct_image(pdf: pikepdf.Pdf) -> None:
    """An image qpdf cannot decode, so its forbidden LZW filter stays."""
    pdf.pages[0].Resources.XObject.Im1 = pdf.make_stream(
        b'\x80\x0b\x60\x50\x22\x0c\x0c\x85\x01',
        Type=Name.XObject,
        Subtype=Name.Image,
        Width=1,
        Height=1,
        ColorSpace=Name.DeviceGray,
        BitsPerComponent=8,
        Filter=Array([Name.LZWDecode, Name.DCTDecode]),
    )


def add_pattern(pdf: pikepdf.Pdf) -> None:
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
    'dirty': [set_interpolate],
    'fail': [add_lzw_dct_image],
    'not_checked': [add_pattern],
}


def sample(kind: str, flavour: str = '2b') -> pikepdf.Pdf:
    pdf = make_image_only_pdf(flavour[0])
    for mutate in MUTATIONS[kind]:
        mutate(pdf)
    return pdf


def static_bytes(pdf: pikepdf.Pdf) -> bytes:
    buffer = BytesIO()
    pdf.save(buffer, static_id=True, fix_metadata_version=False)
    return buffer.getvalue()


def temp_leftovers(directory) -> list[str]:
    return [p.name for p in directory.iterdir() if p.name.startswith('.pikepdf.')]


@pytest.mark.parametrize('flavour', FLAVOURS)
def test_save_repairs_and_passes(flavour, tmp_path):
    out = tmp_path / 'out.pdf'
    with sample('dirty', flavour) as pdf:
        report = save(pdf, out, flavour)
    assert isinstance(report, Report)
    assert report.verdict == 'pass', report.summary()
    assert report.flavour is Flavour(flavour)
    assert report.save_kwargs == resolve_save_kwargs(flavour)
    assert report.prepared is not None
    assert report.prepared.interpolation_removed == 1
    assert out.exists()
    assert validate_written(out, flavour).passed
    assert temp_leftovers(tmp_path) == []


def test_save_accepts_str_path(tmp_path):
    out = tmp_path / 'out.pdf'
    with sample('pass') as pdf:
        assert save(pdf, str(out), '2b').passed
    assert validate_written(out, '2b').passed


@pytest.mark.parametrize('kind', ['fail', 'not_checked'])
@pytest.mark.parametrize('flavour', FLAVOURS)
def test_save_failure_new_destination(kind, flavour, tmp_path):
    out = tmp_path / 'out.pdf'
    with sample(kind, flavour) as pdf, pytest.raises(PdfaError) as excinfo:
        save(pdf, out, flavour)
    assert excinfo.value.report.verdict == kind
    assert excinfo.value.report.save_kwargs == resolve_save_kwargs(flavour)
    assert not out.exists()
    assert temp_leftovers(tmp_path) == []


@pytest.mark.parametrize('kind', ['fail', 'not_checked'])
def test_save_failure_existing_destination(kind, tmp_path):
    out = tmp_path / 'out.pdf'
    out.write_bytes(b'original contents')
    old_time = 1_000_000_000
    os.utime(out, (old_time, old_time))
    with sample(kind) as pdf, pytest.raises(PdfaError):
        save(pdf, out, '2b')
    assert out.read_bytes() == b'original contents'
    assert out.stat().st_mtime == old_time
    assert temp_leftovers(tmp_path) == []


def test_save_replaces_existing_destination(tmp_path):
    out = tmp_path / 'out.pdf'
    out.write_bytes(b'original contents')
    with sample('pass') as pdf:
        save(pdf, out, '2b')
    assert validate_written(out, '2b').passed


def test_repair_false(tmp_path):
    out = tmp_path / 'out.pdf'
    with sample('dirty') as pdf:
        with pytest.raises(PdfaError) as excinfo:
            save(pdf, out, '2b', repair=False)
        assert excinfo.value.report.verdict == 'fail'
        assert not out.exists()
        assert pdf.pages[0].Resources.XObject.Im0.Interpolate
        report = save(pdf, out, '2b', repair=True)
    assert report.passed
    assert out.exists()


def test_repair_false_clean(tmp_path):
    out = tmp_path / 'out.pdf'
    with sample('pass') as pdf:
        report = save(pdf, out, '2b', repair=False)
    assert report.passed
    assert report.prepared is None


@pytest.mark.parametrize('to_stream', [False, True])
def test_save_failure_report_has_prepared(to_stream, tmp_path):
    destination = BytesIO() if to_stream else tmp_path / 'out.pdf'
    with sample('fail') as pdf, pytest.raises(PdfaError) as excinfo:
        save(pdf, destination, '2b')
    assert isinstance(excinfo.value.report.prepared, PrepareResult)


def test_save_failure_without_repair_has_no_prepared(tmp_path):
    with sample('fail') as pdf, pytest.raises(PdfaError) as excinfo:
        save(pdf, tmp_path / 'out.pdf', '2b', repair=False)
    assert excinfo.value.report.prepared is None


class TestStream:
    def test_written_on_pass(self):
        buffer = BytesIO()
        with sample('dirty') as pdf:
            report = save(pdf, buffer, '2b')
        assert report.passed
        data = buffer.getvalue()
        assert data.startswith(b'%PDF-')
        assert validate_written(BytesIO(data), '2b').passed

    @pytest.mark.parametrize('kind', ['fail', 'not_checked'])
    def test_untouched_on_failure(self, kind):
        buffer = BytesIO()
        with sample(kind) as pdf, pytest.raises(PdfaError):
            save(pdf, buffer, '2b')
        assert buffer.tell() == 0
        assert buffer.getvalue() == b''

    def test_text_stream_rejected(self):
        import io

        with sample('pass') as pdf, pytest.raises(TypeError):
            save(pdf, io.StringIO(), '2b')


class TestOverwritingInput:
    def test_allowed(self, tmp_path):
        path = tmp_path / 'in.pdf'
        with sample('dirty') as pdf:
            pdf.save(path)
        with pikepdf.open(path, allow_overwriting_input=True) as pdf:
            report = save(pdf, None, '2b')
        assert report.passed
        assert validate_written(path, '2b').passed

    def test_allowed_explicit_path(self, tmp_path):
        path = tmp_path / 'in.pdf'
        with sample('dirty') as pdf:
            pdf.save(path)
        with pikepdf.open(path, allow_overwriting_input=True) as pdf:
            assert save(pdf, path, '2b').passed
        assert validate_written(path, '2b').passed

    def test_refused(self, tmp_path):
        path = tmp_path / 'in.pdf'
        with sample('dirty') as pdf:
            pdf.save(path)
        before = path.read_bytes()
        with pikepdf.open(path) as pdf:
            unchanged = static_bytes(pdf)
            with pytest.raises(ValueError, match='Cannot overwrite input file'):
                save(pdf, path, '2b')
            with pytest.raises(ValueError, match='Cannot overwrite input file'):
                save(pdf, None, '2b')
            assert static_bytes(pdf) == unchanged
        assert path.read_bytes() == before

    def test_new_pdf_needs_destination(self):
        with pikepdf.new() as pdf, pytest.raises(ValueError, match='Pdf.new'):
            save(pdf, None, '2b')


@pytest.mark.parametrize('flavour', FLAVOURS)
def test_linearize(flavour, tmp_path):
    out = tmp_path / 'out.pdf'
    with sample('dirty', flavour) as pdf:
        report = save(pdf, out, flavour, linearize=True)
    assert report.passed
    assert report.save_kwargs['linearize'] is True
    with pikepdf.open(out) as pdf:
        assert pdf.is_linearized


def test_deterministic_id(tmp_path):
    # prepare stamps xmp:MetadataDate, so repair only once.
    with sample('dirty') as pdf:
        save(pdf, tmp_path / 'a.pdf', '2b', deterministic_id=True)
        save(pdf, tmp_path / 'b.pdf', '2b', deterministic_id=True, repair=False)
    assert (tmp_path / 'a.pdf').read_bytes() == (tmp_path / 'b.pdf').read_bytes()


@pytest.mark.parametrize(
    'kwargs, exc',
    [
        ({'encryption': pikepdf.Encryption(owner='x', user='y')}, ValueError),
        ({'qdf': True}, ValueError),
        ({'force_version': '2.0'}, ValueError),
        ({'no_such_setting': True}, TypeError),
    ],
)
def test_conflicting_kwargs_before_mutation(kwargs, exc, tmp_path):
    out = tmp_path / 'out.pdf'
    with sample('dirty') as pdf:
        before = static_bytes(pdf)
        with pytest.raises(exc):
            save(pdf, out, '2b', **kwargs)
        assert static_bytes(pdf) == before
    assert not out.exists()


def test_bad_flavour_before_mutation(tmp_path):
    with sample('dirty') as pdf:
        before = static_bytes(pdf)
        with pytest.raises(ValueError):
            save(pdf, tmp_path / 'out.pdf', '4b')
        assert static_bytes(pdf) == before


@pytest.mark.parametrize('kind', ['pass', 'dirty', 'fail', 'not_checked'])
@pytest.mark.parametrize('flavour', FLAVOURS)
def test_check_agrees_with_save(kind, flavour, tmp_path):
    out = tmp_path / 'out.pdf'
    with sample(kind, flavour) as pdf:
        prepare(pdf, flavour)
        predicted = check(pdf, flavour)
        try:
            written = save(pdf, out, flavour)
        except PdfaError as e:
            written = e.report
    assert predicted.verdict == written.verdict
    # Object numbers change on writing, so compare rules, not locations.
    assert sorted(f.rule for f in predicted.findings) == sorted(
        f.rule for f in written.findings
    )
    assert out.exists() == (predicted.verdict == 'pass')


def test_explicit_conversion(tmp_path):
    out = tmp_path / 'out.pdf'
    with pikepdf.explicit_conversion(), sample('dirty') as pdf:
        report = save(pdf, out, '2b')
    assert report.passed
    assert validate_written(out, '2b').passed
