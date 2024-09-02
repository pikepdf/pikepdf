# SPDX-FileCopyrightText: 2022 James R. Barlow
# SPDX-License-Identifier: CC0-1.0

from __future__ import annotations

import logging
import os
import os.path
import pathlib
from io import BytesIO, FileIO
from shutil import copy

import pytest

import pikepdf
from pikepdf import Pdf, PdfError
from pikepdf._io import atomic_overwrite

# pylint: disable=redefined-outer-name


@pytest.fixture
def sandwich(resources):
    # Has XMP, docinfo, <?adobe-xap-filters esc="CRLF"?>, shorthand attribute XMP
    with Pdf.open(resources / 'sandwich.pdf') as pdf:
        yield pdf


class LimitedBytesIO(BytesIO):
    """Version of BytesIO that only accepts small reads/writes."""

    def write(self, b):
        amt = min(len(b), 100)
        return super().write(b[:amt])


def test_weird_output_stream(sandwich):
    bio = BytesIO()
    lbio = LimitedBytesIO()
    sandwich.save(bio, static_id=True)
    sandwich.save(lbio, static_id=True)
    assert bio.getvalue() == lbio.getvalue()


def test_overwrite_with_memory_file(outdir):
    (outdir / 'example.pdf').touch()
    pdf = Pdf.new()
    pdf.save(outdir / 'example.pdf')


def test_overwrite_input(resources, outdir):
    copy(resources / 'sandwich.pdf', outdir / 'sandwich.pdf')
    with Pdf.open(outdir / 'sandwich.pdf') as p:
        with pytest.raises(ValueError, match=r'overwrite input file'):
            p.save(outdir / 'sandwich.pdf')


def test_fail_only_overwrite_input_check(monkeypatch, resources, outdir):
    copy(resources / 'sandwich.pdf', outdir / 'sandwich.pdf')
    with Pdf.open(outdir / 'sandwich.pdf') as p:

        def mockraise(*args):
            raise OSError("samefile mocked")

        monkeypatch.setattr(pathlib.Path, 'samefile', mockraise)
        with pytest.raises(OSError, match=r'samefile mocked'):
            p.save(outdir / 'wouldwork.pdf')


class BadBytesIO(BytesIO):
    """Version of BytesIO that reports more bytes written than actual."""

    def write(self, b):
        super().write(b)
        return len(b) + 1


class WrongTypeBytesIO(BytesIO):
    """Returns wrong type."""

    def write(self, b):  # pylint: disable=unused-argument
        return None  # most likely wrong return type


class NegativeOneBytesIO(BytesIO):
    def write(self, b):  # pylint: disable=unused-argument
        return -1


@pytest.mark.parametrize(
    'bio_class,exc_type',
    [
        (BadBytesIO, ValueError),
        (WrongTypeBytesIO, TypeError),
        (NegativeOneBytesIO, PdfError),
    ],
)
def test_invalid_output_stream(sandwich, bio_class, exc_type):
    bio = bio_class()
    with pytest.raises(exc_type):
        sandwich.save(bio, static_id=True)


class ExpectedError(Exception):
    pass


def test_file_without_fileno(resources):
    class FileWithoutFileNo(FileIO):
        def fileno(self):
            raise ExpectedError("nope!")

    f = FileWithoutFileNo(resources / 'pal.pdf', 'rb')
    with pytest.raises(ExpectedError):
        Pdf.open(f, access_mode=pikepdf._core.AccessMode.mmap_only)

    # Confirm we automatically fallback to stream
    with Pdf.open(f, access_mode=pikepdf._core.AccessMode.mmap) as pdf:
        assert pdf.filename


def test_file_deny_mmap(resources, monkeypatch):
    import mmap

    def raises_oserror(*args, **kwargs):
        raise OSError("This file is temporarily not mmap-able")

    monkeypatch.setattr(mmap, 'mmap', raises_oserror)
    with pytest.raises(OSError):
        Pdf.open(resources / 'pal.pdf', access_mode=pikepdf._core.AccessMode.mmap_only)

    with Pdf.open(
        resources / 'pal.pdf', access_mode=pikepdf._core.AccessMode.default
    ) as pdf:
        assert len(pdf.pages) == 1


def test_mmap_only_file(resources):
    class UnreadableFile(FileIO):
        def readinto(self, *args):
            raise ExpectedError("can't read, you have to mmap me")

        read = readinto  # PyPy uses read() not readinto()

    f = UnreadableFile(resources / 'pal.pdf', 'rb')
    with pytest.raises(ExpectedError):
        Pdf.open(f, access_mode=pikepdf._core.AccessMode.stream)


def test_save_bytesio(resources, outpdf):
    with Pdf.open(resources / 'fourpages.pdf') as input_:
        pdf = Pdf.new()
        for page in input_.pages:
            pdf.pages.append(page)
        bio = BytesIO()
        pdf.save(bio, static_id=True)
        bio_value = bio.getvalue()
        assert bio_value != b''
        pdf.save(outpdf, static_id=True)
        assert outpdf.read_bytes() == bio_value


@pytest.mark.skipif(
    hasattr(os, 'geteuid') and os.geteuid() == 0, reason="root can override permissions"
)
def test_save_failure(sandwich, outdir):
    dest = outdir / 'notwritable.pdf'

    # This should work on Windows since Python maps the read-only bit
    dest.touch(mode=0o444, exist_ok=False)
    if dest.stat().st_mode & 0o400 != 0o400:
        pytest.skip("Couldn't create a read-only file")

    # Now try to overwrite
    with pytest.raises(PermissionError, match="denied"):
        sandwich.save(dest)


def test_stop_iteration_on_close(resources):
    class StopIterationOnClose(BytesIO):
        def close(self):
            raise StopIteration('To simulate weird generator behavior')

    # Inspired by https://github.com/pikepdf/pikepdf/issues/114
    stream = StopIterationOnClose((resources / 'pal-1bit-trivial.pdf').read_bytes())
    pdf = Pdf.open(stream)  # no with clause
    pdf.close()


def test_read_after_close(resources):
    pdf = Pdf.open(resources / 'pal.pdf')  # no with clause
    contents = pdf.pages[0].Contents
    pdf.close()
    with pytest.raises(PdfError, match="closed input source"):
        contents.read_raw_bytes()


def test_logging(caplog):
    caplog.set_level(logging.INFO)
    pikepdf._core._test.log_info("test log message")
    assert [("pikepdf._core", logging.INFO)] == [
        (rec[0], rec[1]) for rec in caplog.record_tuples
    ]


def test_atomic_overwrite_new(tmp_path):
    new_file = tmp_path / 'new.pdf'
    assert not new_file.exists()

    with pytest.raises(ValueError, match='oops'), atomic_overwrite(new_file) as f:
        f.write(b'a failed write should not produce an invalid file')
        raise ValueError('oops')
    assert not new_file.exists()

    assert list(tmp_path.glob('*.pikepdf')) == [], "Temporary files were not cleaned up"


def test_atomic_overwrite_existing(tmp_path):
    existing_file = tmp_path / 'existing.pdf'
    existing_file.write_bytes(b'existing')

    with atomic_overwrite(existing_file) as f:
        f.write(b'new')
    assert existing_file.read_bytes() == b'new'

    with pytest.raises(ValueError, match='oops'), atomic_overwrite(existing_file) as f:
        f.write(b'a failed update should not corrupt the file')
        raise ValueError('oops')
    assert existing_file.read_bytes() == b'new'

    assert list(tmp_path.glob('*.pikepdf')) == [], "Temporary files were not cleaned up"


def test_atomic_ovewrite_stat_preservation(tmp_path):
    existing_file = tmp_path / 'existing.pdf'
    existing_file.touch(0o755)
    os.utime(existing_file, ns=(0, 0))

    ctime = existing_file.stat().st_ctime
    with atomic_overwrite(existing_file) as f:
        f.write(b'new')
    stat = existing_file.stat()
    assert stat.st_ctime >= ctime
    assert stat.st_mtime > 0
    if os.name != 'nt':
        # st_mode is not preserved on Windows
        assert stat.st_mode & 0o777 == 0o755


def test_memory_to_path(resources, tmp_path):
    bio = BytesIO((resources / 'sandwich.pdf').read_bytes())
    with Pdf.open(bio) as pdf:
        assert len(pdf.pages) == 1
        pdf.save(str(tmp_path / 'out.pdf'))


def test_newline_handling(resources):
    with Pdf.open(
        resources / 'newline-buffer-test.pdf',
        access_mode=pikepdf._core.AccessMode.mmap_only,
    ) as pdf:
        assert pdf.check() == []
    with Pdf.open(
        resources / 'newline-buffer-test.pdf',
        access_mode=pikepdf._core.AccessMode.stream,
    ) as pdf:
        assert pdf.check() == []
