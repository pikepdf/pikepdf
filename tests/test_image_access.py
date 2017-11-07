import pytest
import imghdr
from io import BytesIO
from PIL import Image
import zlib

from pikepdf import Pdf, Object, PdfImage
from pikepdf._qpdf import Name, Null


@pytest.fixture
def congress_im0(resources):
    pdf = Pdf.open(resources / 'congress.pdf')
    pdfimage = pdf.pages[0].Resources.XObject['/Im0']
    return pdfimage


def test_image_from_nonimage(resources):
    pdf = Pdf.open(resources / 'congress.pdf')
    resources = pdf.pages[0].Contents
    with pytest.raises(TypeError):
        PdfImage(resources)


def test_image(congress_im0):
    pdfimage = PdfImage(congress_im0)
    pillowimage = pdfimage.topil()

    assert pillowimage.mode == pdfimage.mode
    assert pillowimage.size == pdfimage.size


def test_lowlevel_jpeg(congress_im0, outdir):
    raw_bytes = congress_im0.read_raw_bytes()
    with pytest.raises(RuntimeError):
        congress_im0.read_bytes()

    assert imghdr.what('', h=raw_bytes) == 'jpeg'

    im = Image.open(BytesIO(raw_bytes))
    assert im.size == (congress_im0.Width, congress_im0.Height)
    assert im.mode == 'RGB'


def test_lowlevel_replace_jpeg(congress_im0, outdir):
    # This test will modify the PDF so needs its own image
    raw_bytes = congress_im0.read_raw_bytes()

    im = Image.open(BytesIO(raw_bytes))
    grayscale = im.convert('L')

    #newimage = Object.Stream(pdf, grayscale.tobytes())

    congress_im0.write(zlib.compress(grayscale.tobytes()), Name("/FlateDecode"), Null())
    congress_im0.ColorSpace = Name('/DeviceGray')

    pdf.save(outdir / 'congress_gray.pdf')