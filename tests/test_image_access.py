import pytest
import imghdr
from io import BytesIO
from PIL import Image, features as PIL_features
import zlib

# pylint: disable=w0621


from pikepdf import (
    Pdf, PdfImage, PdfError, Name,
    parse_content_stream, PdfInlineImage, Stream, StreamDecodeLevel
)


def first_image_in(filename):
    pdf = Pdf.open(filename)
    pdfimagexobj = next(iter(pdf.pages[0].images.values()))
    return pdfimagexobj, pdf


@pytest.fixture
def congress(resources):
    return first_image_in(resources / 'congress.pdf')


@pytest.fixture
def sandwich(resources):
    return first_image_in(resources / 'sandwich.pdf')


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
    grayscale = grayscale.resize((4, 4))  # So it is not obnoxious on error

    congress[0].write(
        zlib.compress(grayscale.tobytes()),
        filter=Name("/FlateDecode")
    )
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
    grayscale = grayscale.resize((4, 4))  # So it is not obnoxious on error

    congress[0].write(
        zlib.compress(grayscale.tobytes()[:10]),
        filter=Name("/FlateDecode")
    )
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
    assert iimage.colorspace == '/DeviceRGB'


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
    pdf.save(outfile, compress_streams=False,
             stream_decode_level=StreamDecodeLevel.none)

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


@pytest.mark.parametrize('filename,bpc,filters,ext,mode,format',
    [
        ('sandwich.pdf', 1, ['/CCITTFaxDecode'], '.tif', '1', 'TIFF'),
        ('congress-gray.pdf', 8, ['/DCTDecode'], '.jpg', 'L', 'JPEG'),
        ('congress.pdf', 8, ['/DCTDecode'], '.jpg', 'RGB', 'JPEG'),
        ('cmyk-jpeg.pdf', 8, ['/DCTDecode'], '.jpg', 'CMYK', 'JPEG')
    ]
)
def test_direct_extract(resources, filename, bpc, filters, ext, mode, format):
    xobj, pdf = first_image_in(resources / filename)
    pim = PdfImage(xobj)

    assert pim.bits_per_component == bpc
    assert pim.filters == filters

    outstream = BytesIO()
    outext = pim.extract_to(stream=outstream)
    assert outext == ext, 'unexpected output file'
    outstream.seek(0)

    im = Image.open(outstream)
    assert im.mode == mode
    assert im.format == format


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


def test_bool_in_inline_image():
    piim = PdfInlineImage(image_data=b'', image_object=(Name.IM, True))
    assert piim.image_mask


@pytest.mark.skipif(not PIL_features.check_codec('jpg_2000'),
                    reason='no JPEG2000 codec')
def test_jp2(resources):
    pdf = Pdf.open(resources / 'pike-jp2.pdf')
    xobj = next(iter(pdf.pages[0].images.values()))
    pim = PdfImage(xobj)

    assert '/JPXDecode' in pim.filters
    assert pim.colorspace == '/DeviceRGB'
    assert not pim.is_inline
    assert not pim.indexed
    assert pim.mode == 'RGB'
    assert pim.bits_per_component == 8

    outstream = BytesIO()
    pim.extract_to(stream=outstream)
    del pim
    del xobj.ColorSpace

    # If there is no explicit ColorSpace metadata we should get it from the
    # compressed data stream
    pim = PdfImage(xobj)
    assert pim.colorspace == '/DeviceRGB'
    assert pim.bits_per_component == 8
