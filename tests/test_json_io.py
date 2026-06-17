# SPDX-FileCopyrightText: 2026 James R. Barlow
# SPDX-License-Identifier: CC0-1.0

from __future__ import annotations

from io import BytesIO

import pytest

from pikepdf import (
    JSONStreamData,
    ObjectStreamMode,
    Pdf,
    StreamDecodeLevel,
    XrefEntry,
)


@pytest.fixture
def fourpages(resources):
    with Pdf.open(resources / 'fourpages.pdf') as pdf:
        yield pdf


def test_write_qpdf_json_to_stream(fourpages):
    buf = BytesIO()
    fourpages.write_qpdf_json(buf)
    data = buf.getvalue()
    assert data.startswith(b'{')
    assert b'"qpdf"' in data


def test_write_qpdf_json_to_path(fourpages, outdir):
    target = outdir / 'out.json'
    fourpages.write_qpdf_json(target)
    assert target.exists()
    assert target.read_bytes().startswith(b'{')


def test_json_round_trip_stream(fourpages):
    buf = BytesIO()
    fourpages.write_qpdf_json(buf)
    buf.seek(0)
    pdf2 = Pdf.from_qpdf_json(buf)
    assert len(pdf2.pages) == len(fourpages.pages)
    # The reconstructed PDF should be saveable
    out = BytesIO()
    pdf2.save(out)
    assert out.getvalue().startswith(b'%PDF-')


def test_json_round_trip_path(fourpages, outdir):
    target = outdir / 'roundtrip.json'
    fourpages.write_qpdf_json(target)
    pdf2 = Pdf.from_qpdf_json(target)
    assert len(pdf2.pages) == len(fourpages.pages)


def test_update_from_qpdf_json(resources, fourpages):
    buf = BytesIO()
    fourpages.write_qpdf_json(buf)
    buf.seek(0)
    target = Pdf.open(resources / 'fourpages.pdf')
    target.update_from_qpdf_json(buf)
    assert len(target.pages) == len(fourpages.pages)


def test_write_qpdf_json_stream_data_file(resources, outdir):
    # A PDF with image stream data; write streams to external files.
    with Pdf.open(resources / 'graph.pdf') as pdf:
        prefix = outdir / 'graph-streams'
        target = outdir / 'graph.json'
        pdf.write_qpdf_json(
            target,
            json_stream_data=JSONStreamData.file,
            file_prefix=str(prefix),
        )
    assert target.exists()
    produced = list(outdir.glob('graph-streams-*'))
    assert produced, "expected external stream files to be written"


def test_write_qpdf_json_decode_level(fourpages):
    # Both decode levels should produce valid JSON.
    for level in (StreamDecodeLevel.none, StreamDecodeLevel.generalized):
        buf = BytesIO()
        fourpages.write_qpdf_json(buf, decode_level=level)
        assert buf.getvalue().startswith(b'{')


def test_write_qpdf_json_file_mode_requires_prefix_for_stream(fourpages):
    with pytest.raises(ValueError, match="file_prefix"):
        fourpages.write_qpdf_json(BytesIO(), json_stream_data=JSONStreamData.file)


def test_get_xref_table(fourpages):
    xref = fourpages.get_xref_table()
    assert isinstance(xref, dict)
    assert len(xref) > 0
    for key, entry in xref.items():
        assert isinstance(key, tuple) and len(key) == 2
        assert isinstance(entry, XrefEntry)
        assert entry.type in (0, 1, 2)
        if entry.type == 1:
            assert entry.offset is not None and entry.offset >= 0
            assert entry.obj_stream_number is None
        elif entry.type == 2:
            assert entry.obj_stream_number is not None
            assert entry.obj_stream_index is not None
            assert entry.offset is None


def test_xref_entry_repr(fourpages):
    xref = fourpages.get_xref_table()
    entry = next(iter(xref.values()))
    assert 'XrefEntry' in repr(entry)


def test_get_xref_table_object_streams(resources):
    # A PDF saved with object streams exercises type-2 (compressed) entries.
    with Pdf.open(resources / 'fourpages.pdf') as pdf:
        buf = BytesIO()
        pdf.save(buf, object_stream_mode=ObjectStreamMode.generate)
    buf.seek(0)
    with Pdf.open(buf) as pdf2:
        xref = pdf2.get_xref_table()
        assert any(entry.type == 2 for entry in xref.values())


def test_fix_dangling_references(fourpages):
    # A no-op on a clean file should not raise and should preserve the document.
    fourpages.fix_dangling_references()
    fourpages.fix_dangling_references(force=True)
    assert len(fourpages.pages) == 4
