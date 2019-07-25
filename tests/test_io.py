import pytest

from pikepdf import Pdf, PdfError
from pikepdf._cpphelpers import fspath
from io import BytesIO
from shutil import copy
import sys


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


class BadBytesIO(BytesIO):
    """Version of BytesIO that reports more bytes written than actual"""

    def write(self, b):
        super().write(b)
        return len(b) + 1


class WrongTypeBytesIO(BytesIO):
    """Returns wrong type"""

    def write(self, b):
        return None  # most likely wrong return type


class NegativeOneBytesIO(BytesIO):
    def write(self, b):
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
