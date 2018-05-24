import pytest
import imghdr
from io import BytesIO
from PIL import Image
import zlib
import sys

from pikepdf import (Pdf, Object, PdfImage, PdfError, Name, Null,
        parse_content_stream, ObjectType, PdfInlineImage)


@pytest.fixture
def congress(resources):
    pdf = Pdf.open(resources / 'congress.pdf')
    pdfimage = pdf.pages[0].Resources.XObject['/Im0']
    return pdfimage, pdf


def test_image_from_nonimage(resources):
    pdf = Pdf.open(resources / 'congress.pdf')
    resources = pdf.pages[0].Contents
    with pytest.raises(TypeError):
        PdfImage(resources)


def test_image(congress):
    pdfimage = PdfImage(congress[0])
    pillowimage = pdfimage.as_pil_image()

    assert pillowimage.mode == pdfimage.mode
    assert pillowimage.size == pdfimage.size


def test_imagemask(congress):
    assert PdfImage(congress[0]).image_mask == False


def test_image_replace(congress, outdir):
    pdfimage = PdfImage(congress[0])
    pillowimage = pdfimage.as_pil_image()

    grayscale = pillowimage.convert('L')

    congress[0].write(zlib.compress(grayscale.tobytes()), Name("/FlateDecode"), Null())
    congress[0].ColorSpace = Name("/DeviceGray")
    pdf = congress[1]
    pdf.save(outdir / 'congress_gray.pdf')


def test_lowlevel_jpeg(congress, outdir):
    raw_bytes = congress[0].read_raw_bytes()
    with pytest.raises(PdfError):
        congress[0].read_bytes()

    assert imghdr.what('', h=raw_bytes) == 'jpeg'

    pim = PdfImage(congress[0])
    b = BytesIO()
    pim.extract_to(stream=b)
    b.seek(0)
    im = Image.open(b)
    assert im.size == (congress[0].Width, congress[0].Height)
    assert im.mode == 'RGB'


def test_lowlevel_replace_jpeg(congress, outdir):
    # This test will modify the PDF so needs its own image
    raw_bytes = congress[0].read_raw_bytes()

    im = Image.open(BytesIO(raw_bytes))
    grayscale = im.convert('L')

    congress[0].write(zlib.compress(grayscale.tobytes()), Name("/FlateDecode"), Null())
    congress[0].ColorSpace = Name('/DeviceGray')

    pdf = congress[1]
    pdf.save(outdir / 'congress_gray.pdf')


@pytest.fixture
def inline(resources):
    pdf = Pdf.open(resources / 'image-mono-inline.pdf')
    for operands, command in parse_content_stream(pdf.pages[0]):
        if operands and isinstance(operands[0], PdfInlineImage):
            return operands[0], pdf


def test_inline(inline):
    iimage, pdf = inline
    assert iimage.width == 8
    assert iimage.image_mask == False
    assert iimage.mode == 'RGB'
