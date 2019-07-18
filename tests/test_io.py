import pytest

from pikepdf import Pdf
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
