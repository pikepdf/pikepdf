import pytest
import imghdr
from io import BytesIO
from PIL import Image
import zlib

# pylint: disable=w0621


from pikepdf import (
    Pdf, PdfImage, PdfError, Name, Null,
    parse_content_stream, PdfInlineImage, Stream, StreamDataMode
)


@pytest.fixture
def congress(resources):
    pdf = Pdf.open(resources / 'congress.pdf')
    pdfimagexobj = pdf.pages[0].Resources.XObject['/Im0']
    return pdfimagexobj, pdf


@pytest.fixture
def sandwich(resources):
    pdf = Pdf.open(resources / 'sandwich.pdf')
    pdfimagexobj = next(iter(pdf.pages[0].images.values()))
    return pdfimagexobj, pdf


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


def test_lowlevel_jpeg(congress):
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

    congress[0].write(zlib.compress(grayscale.tobytes()[:10]), Name("/FlateDecode"), Null())
    congress[0].ColorSpace = Name('/DeviceGray')

    pdf = congress[1]
    pdf.save(outdir / 'congress_gray.pdf')


@pytest.fixture
def inline(resources):
    pdf = Pdf.open(resources / 'image-mono-inline.pdf')
    for operands, _command in parse_content_stream(pdf.pages[0]):
        if operands and isinstance(operands[0], PdfInlineImage):
            return operands[0], pdf


def test_inline(inline):
    iimage, _pdf = inline
    assert iimage.width == 8
    assert iimage.image_mask == False
    assert iimage.mode == 'RGB'
    assert iimage.is_inline


def test_bits_per_component_missing(congress):
    cong_im = congress[0]
    del cong_im.stream_dict['/BitsPerComponent']
    assert PdfImage(congress[0]).bits_per_component == 8


@pytest.mark.parametrize('w,h,pixeldata,cs,bpc', [
    (1, 1, b'\xff', '/DeviceGray', 1),
    (1, 1, b'\xf0', '/DeviceGray', 8),
    (1, 1, b'\xff\x00\xff', '/DeviceRGB', 8)
])
def test_image_roundtrip(outdir, w, h, pixeldata, cs, bpc):
    pdf = Pdf.new()

    image_data = pixeldata * (w * h)

    image = Stream(pdf, image_data)
    image.Type = Name('/XObject')
    image.Subtype = Name('/Image')
    image.ColorSpace = Name(cs)
    image.BitsPerComponent = bpc
    image.Width = w
    image.Height = h

    xobj = {'/Im1': image}
    resources = {'/XObject': xobj}
    mediabox = [0, 0, 100, 100]
    stream = b'q 100 0 0 100 0 0 cm /Im1 Do Q'
    contents = Stream(pdf, stream)

    page_dict = {
        '/Type': Name('/Page'),
        '/MediaBox': mediabox,
        '/Contents': contents,
        '/Resources': resources
    }
    page = pdf.make_indirect(page_dict)

    pdf.pages.append(page)
    outfile = outdir / 'test{w}{h}{cs}{bpc}.pdf'.format(
        w=w, h=h, cs=cs[1:], bpc=bpc
    )
    pdf.save(outfile, stream_data_mode=StreamDataMode.preserve)

    p2 = pdf.open(outfile)
    pim = PdfImage(p2.pages[0].Resources.XObject['/Im1'])

    assert pim.bits_per_component == bpc
    assert pim.colorspace == cs
    assert pim.width == w
    assert pim.height == h
    if cs == '/DeviceRGB':
        assert pim.mode == 'RGB'
    elif cs == '/DeviceGray' and bpc == 8:
        assert pim.mode == 'L'
    elif bpc == 1:
        assert pim.mode == '1'
    assert not pim.palette

    assert pim.filters == []
    assert pim.read_bytes() == pixeldata

    outstream = BytesIO()
    pim.extract_to(stream=outstream)
    outstream.seek(0)
    im = Image.open(outstream)
    assert pim.mode == im.mode


def test_image_ccitt(sandwich):
    pim = PdfImage(sandwich[0])

    assert pim.bits_per_component == 1
    assert pim.filters == ['/CCITTFaxDecode']

    outstream = BytesIO()
    assert pim.extract_to(stream=outstream) == '.tif'


@pytest.mark.parametrize('filename,bpc', [
    ('pal.pdf', 8),
    ('pal-1bit-trivial.pdf', 1),
    pytest.param('pal-1bit-rgb.pdf', 1, marks=pytest.mark.xfail(raises=NotImplementedError)),
])
def test_image_palette(resources, filename, bpc):
    pdf = Pdf.open(resources / filename)
    pim = PdfImage(next(iter(pdf.pages[0].images.values())))

    assert pim.palette[0] == 'RGB'
    assert pim.colorspace == '/DeviceRGB'
    assert not pim.is_inline
    assert pim.mode == 'P'
    assert pim.bits_per_component == bpc

    outstream = BytesIO()
    pim.extract_to(stream=outstream)
