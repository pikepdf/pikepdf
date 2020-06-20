import os.path
import sys
from io import BytesIO
from shutil import copy

import psutil
import pytest

from pikepdf import Pdf, PdfError

# pylint: disable=redefined-outer-name


@pytest.fixture
def sandwich(resources):
    # Has XMP, docinfo, <?adobe-xap-filters esc="CRLF"?>, shorthand attribute XMP
    return Pdf.open(resources / 'sandwich.pdf')


class LimitedBytesIO(BytesIO):
    """Version of BytesIO that only accepts small reads/writes"""

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


@pytest.mark.skipif(sys.version_info < (3, 6), reason='pathlib and shutil')
def test_overwrite_input(resources, outdir):
    copy(resources / 'sandwich.pdf', outdir / 'sandwich.pdf')
    p = Pdf.open(outdir / 'sandwich.pdf')
    with pytest.raises(ValueError, match=r'overwrite input file'):
        p.save(outdir / 'sandwich.pdf')


@pytest.mark.skipif(sys.version_info < (3, 6), reason='pathlib')
def test_fail_only_overwrite_input_check(monkeypatch, resources, outdir):
    copy(resources / 'sandwich.pdf', outdir / 'sandwich.pdf')
    p = Pdf.open(outdir / 'sandwich.pdf')

    def mockraise(*args):
        raise OSError("samefile mocked")

    monkeypatch.setattr(os.path, 'samefile', mockraise)
    with pytest.raises(OSError, match=r'samefile mocked'):
        p.save(outdir / 'wouldwork.pdf')


class BadBytesIO(BytesIO):
    """Version of BytesIO that reports more bytes written than actual"""

    def write(self, b):
        super().write(b)
        return len(b) + 1


class WrongTypeBytesIO(BytesIO):
    """Returns wrong type"""

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


uses_psutil_open_files = pytest.mark.skipif(
    sys.platform == 'win32' or sys.platform.startswith('freebsd'),
    reason="psutil documentation warns that .open_files() has problems on these",
)


def file_descriptor_is_open_for(path):
    process = psutil.Process()
    return any((f.path == str(path.resolve())) for f in process.open_files())


@uses_psutil_open_files
def test_open_named_file_closed(resources):
    path = resources / 'pal.pdf'
    pdf = Pdf.open(path)
    assert file_descriptor_is_open_for(path)

    pdf.close()
    assert not file_descriptor_is_open_for(
        path
    ), "pikepdf did not close a stream it opened"


@uses_psutil_open_files
def test_streamed_file_not_closed(resources):
    path = resources / 'pal.pdf'
    stream = path.open('rb')
    pdf = Pdf.open(stream)
    assert file_descriptor_is_open_for(path)

    pdf.close()
    assert file_descriptor_is_open_for(path), "pikepdf closed a stream it did not open"


@uses_psutil_open_files
@pytest.mark.parametrize('branch', ['success', 'failure'])
def test_save_named_file_closed(resources, outdir, branch):
    with Pdf.open(resources / 'pal.pdf') as pdf:
        path = outdir / "pal.pdf"

        def confirm_opened(progress_percent):
            if progress_percent == 0:
                assert file_descriptor_is_open_for(path)
            if progress_percent > 0 and branch == 'failure':
                raise ValueError('failure branch')

        try:
            pdf.save(path, progress=confirm_opened)
        except ValueError:
            pass
        assert not file_descriptor_is_open_for(
            path
        ), "pikepdf did not close a stream it opened"


@uses_psutil_open_files
def test_save_streamed_file_not_closed(resources, outdir):
    with Pdf.open(resources / 'pal.pdf') as pdf:
        path = outdir / "pal.pdf"
        stream = path.open('wb')

        def confirm_opened(progress_percent):
            if progress_percent == 0:
                assert file_descriptor_is_open_for(path)

        pdf.save(stream, progress=confirm_opened)
        assert file_descriptor_is_open_for(
            path
        ), "pikepdf closed a stream it did not open"
