import pytest
import imghdr
from io import BytesIO
from PIL import Image
import zlib

from pikepdf import Pdf, Object

def test_jpeg(resources, outdir):
    pdf = Pdf.open(resources / 'congress.pdf')

    # If you are looking at this as example code, Im0 is not necessarily the
    # name of any image.
    pdfimage = pdf.pages[0].Resources.XObject['/Im0']
    raw_bytes = pdfimage.read_raw_bytes()
    with pytest.raises(RuntimeError):
        pdfimage.read_bytes()

    assert imghdr.what('', h=raw_bytes) == 'jpeg'

    im = Image.open(BytesIO(raw_bytes))
    assert im.size == (pdfimage.Width, pdfimage.Height)
    assert im.mode == 'RGB'


def test_replace_jpeg(resources, outdir):
    pdf = Pdf.open(resources / 'congress.pdf')

    pdfimage = pdf.pages[0].Resources.XObject['/Im0']
    raw_bytes = pdfimage.read_raw_bytes()

    im = Image.open(BytesIO(raw_bytes))
    grayscale = im.convert('L')

    #newimage = Object.Stream(pdf, grayscale.tobytes())

    pdfimage.write(zlib.compress(grayscale.tobytes()), Object.Name("/FlateDecode"), Object.Null())
    pdfimage.ColorSpace = Object.Name('/DeviceGray')

    pdf.save(outdir / 'congress_gray.pdf')