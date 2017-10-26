import pytest
import imghdr
from io import BytesIO
from PIL import Image

from pikepdf import _qpdf as qpdf

def test_jpeg(resources, outdir):
    pdf = qpdf.Pdf.open(resources / 'congress.pdf')

    # If you are looking at this as example code, Im0 is not necessarily the
    # name of any image.
    pdfimage = pdf.pages[0].Resources.XObject.Im0
    raw_stream = pdf.pages[0].Resources.XObject.Im0.read_raw_stream()
    with pytest.raises(RuntimeError):
        pdf.pages[0].Resources.XObject.Im0.read_stream()

    assert imghdr.what('', h=raw_stream) == 'jpeg'

    im = Image.open(BytesIO(raw_stream))
    assert im.size == (pdfimage.Width, pdfimage.Height)
    assert im.mode == 'RGB'