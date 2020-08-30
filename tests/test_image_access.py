import zlib
from io import BytesIO
from os import fspath
from pathlib import Path

import pytest
from PIL import Image, ImageCms
from PIL import features as PIL_features

import pikepdf
from pikepdf import (
    Dictionary,
    Name,
    Pdf,
    PdfError,
    PdfImage,
    PdfInlineImage,
    Stream,
    StreamDecodeLevel,
    parse_content_stream,
)
from pikepdf.models.image import (
    DependencyError,
    NotExtractableError,
    UnsupportedImageTypeError,
)

# pylint: disable=redefined-outer-name


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


@pytest.fixture
def jbig2(resources):
    return first_image_in(resources / 'jbig2.pdf')


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

    congress[0].write(zlib.compress(grayscale.tobytes()), filter=Name("/FlateDecode"))
    congress[0].ColorSpace = Name("/DeviceGray")
    pdf = congress[1]
    pdf.save(outdir / 'congress_gray.pdf')


def test_lowlevel_jpeg(congress):
    raw_bytes = congress[0].read_raw_bytes()
    with pytest.raises(PdfError):
        congress[0].read_bytes()

    im = Image.open(BytesIO(raw_bytes))
    assert im.format == 'JPEG'

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
        zlib.compress(grayscale.tobytes()[:10]), filter=Name("/FlateDecode")
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
    iimage, pdf = inline
    assert iimage.width == 8
    assert iimage.image_mask == False
    assert iimage.mode == 'RGB'
    assert iimage.is_inline
    assert iimage.colorspace == '/DeviceRGB'

    unparsed = iimage.unparse()

    cs = pdf.make_stream(unparsed)
    for operands, _command in parse_content_stream(cs):
        if operands and isinstance(operands[0], PdfInlineImage):
            reparsed_iim = operands[0]
            assert reparsed_iim == iimage


def test_bits_per_component_missing(congress):
    cong_im = congress[0]
    del cong_im.stream_dict['/BitsPerComponent']
    assert PdfImage(congress[0]).bits_per_component == 8


@pytest.mark.parametrize(
    'w,h,pixeldata,cs,bpc',
    [
        (1, 1, b'\xff', '/DeviceGray', 1),
        (1, 1, b'\xf0', '/DeviceGray', 8),
        (1, 1, b'\xff\x00\xff', '/DeviceRGB', 8),
    ],
)
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
        '/Resources': resources,
    }
    page = pdf.make_indirect(page_dict)

    pdf.pages.append(page)
    outfile = outdir / 'test{w}{h}{cs}{bpc}.pdf'.format(w=w, h=h, cs=cs[1:], bpc=bpc)
    pdf.save(
        outfile, compress_streams=False, stream_decode_level=StreamDecodeLevel.none
    )

    p2 = Pdf.open(outfile)
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


@pytest.mark.parametrize(
    'filename,bpc,filters,ext,mode,format_',
    [
        ('sandwich.pdf', 1, ['/CCITTFaxDecode'], '.tif', '1', 'TIFF'),
        ('congress-gray.pdf', 8, ['/DCTDecode'], '.jpg', 'L', 'JPEG'),
        ('congress.pdf', 8, ['/DCTDecode'], '.jpg', 'RGB', 'JPEG'),
        ('cmyk-jpeg.pdf', 8, ['/DCTDecode'], '.jpg', 'CMYK', 'JPEG'),
    ],
)
def test_direct_extract(resources, filename, bpc, filters, ext, mode, format_):
    xobj, _pdf = first_image_in(resources / filename)
    pim = PdfImage(xobj)

    assert pim.bits_per_component == bpc
    assert pim.filters == filters

    outstream = BytesIO()
    outext = pim.extract_to(stream=outstream)
    assert outext == ext, 'unexpected output file'
    outstream.seek(0)

    im = Image.open(outstream)
    assert im.mode == mode
    assert im.format == format_


@pytest.mark.parametrize(
    'filename,bpc,rgb',
    [
        ('pal.pdf', 8, (0, 0, 255)),
        ('pal-1bit-trivial.pdf', 1, (255, 255, 255)),
        ('pal-1bit-rgb.pdf', 1, (255, 128, 0)),
    ],
)
def test_image_palette(resources, filename, bpc, rgb):
    pdf = Pdf.open(resources / filename)
    pim = PdfImage(next(iter(pdf.pages[0].images.values())))

    assert pim.palette[0] == 'RGB'
    assert pim.colorspace == '/DeviceRGB'
    assert not pim.is_inline
    assert pim.mode == 'P'
    assert pim.bits_per_component == bpc

    outstream = BytesIO()
    pim.extract_to(stream=outstream)

    im = pim.as_pil_image().convert('RGB')
    assert im.getpixel((1, 1)) == rgb


def test_bool_in_inline_image():
    piim = PdfInlineImage(image_data=b'', image_object=(Name.IM, True))
    assert piim.image_mask


@pytest.mark.skipif(
    not PIL_features.check_codec('jpg_2000'), reason='no JPEG2000 codec'
)
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


def test_extract_filepath(congress, outdir):
    xobj, _pdf = congress
    pim = PdfImage(xobj)

    # fspath is for Python 3.5
    result = pim.extract_to(fileprefix=fspath(outdir / 'image'))
    assert Path(result).exists()
    assert (outdir / 'image.jpg').exists()


def test_extract_direct_fails_nondefault_colortransform(congress):
    xobj, _pdf = congress

    xobj.DecodeParms = Dictionary(
        ColorTransform=42  # Non standard (or allowed in the spec)
    )
    pim = PdfImage(xobj)

    bio = BytesIO()
    with pytest.raises(NotExtractableError):
        pim._extract_direct(stream=bio)
    with pytest.raises(UnsupportedImageTypeError):
        pim.extract_to(stream=bio)

    xobj.ColorSpace = Name.DeviceCMYK
    pim = PdfImage(xobj)
    with pytest.raises(NotExtractableError):
        pim._extract_direct(stream=bio)
    with pytest.raises(UnsupportedImageTypeError):
        pim.extract_to(stream=bio)


def test_icc_use(resources):
    xobj, _pdf = first_image_in(resources / '1biticc.pdf')

    pim = PdfImage(xobj)
    assert pim.mode == '1'
    assert pim.colorspace == '/ICCBased'
    assert pim.bits_per_component == 1

    assert pim.icc.profile.xcolor_space == 'GRAY'


def test_icc_extract(resources):
    xobj, _pdf = first_image_in(resources / 'aquamarine-cie.pdf')

    pim = PdfImage(xobj)
    assert pim.as_pil_image().info['icc_profile'] == pim.icc.tobytes()


def test_icc_palette(resources):
    xobj, _pdf = first_image_in(resources / 'pink-palette-icc.pdf')
    pim = PdfImage(xobj)
    assert pim.icc.profile.xcolor_space == 'RGB '  # with trailing space
    b = BytesIO()
    pim.extract_to(stream=b)
    b.seek(0)

    im = Image.open(b)
    assert im.size == (xobj.Width, xobj.Height)
    assert im.mode == 'P'
    pil_icc = im.info.get('icc_profile')
    pil_icc_stream = BytesIO(pil_icc)
    pil_prf = ImageCms.ImageCmsProfile(pil_icc_stream)

    assert pil_prf.tobytes() == pim.icc.tobytes()


def test_stacked_compression(resources):
    xobj, _pdf = first_image_in(resources / 'pike-flate-jp2.pdf')

    pim = PdfImage(xobj)
    assert pim.mode == 'RGB'
    assert pim.colorspace == '/DeviceRGB'
    assert pim.bits_per_component == 8
    assert pim.filters == ['/FlateDecode', '/JPXDecode']


def test_ccitt_photometry(sandwich):
    xobj, _pdf = sandwich

    pim = PdfImage(xobj)
    im = pim.as_pil_image()
    im = im.convert('L')
    assert im.getpixel((0, 0)) == 255, "Expected white background"


def test_ccitt_encodedbytealign(sandwich):
    xobj, _pdf = sandwich

    # Pretend this is image is "EncodedByteAlign". We don't have a FOSS
    # example of such an image.
    xobj.DecodeParms.EncodedByteAlign = True
    pim = PdfImage(xobj)
    with pytest.raises(UnsupportedImageTypeError):
        pim.as_pil_image()


def test_imagemagick_uses_rle_compression(resources):
    xobj, _rle = first_image_in(resources / 'rle.pdf')

    pim = PdfImage(xobj)
    im = pim.as_pil_image()
    assert im.getpixel((5, 5)) == (255, 128, 0)


def test_jbig2_not_available(jbig2, monkeypatch):
    xobj, _pdf = jbig2
    pim = PdfImage(xobj)

    monkeypatch.setattr(pikepdf.jbig2, 'jbig2dec_available', lambda: False)
    with pytest.raises(DependencyError):
        pim.as_pil_image()


needs_jbig2dec = pytest.mark.skipif(
    not pikepdf.jbig2.jbig2dec_available(), reason="jbig2dec not installed"
)


@needs_jbig2dec
def test_jbig2(jbig2):
    xobj, _pdf = jbig2
    pim = PdfImage(xobj)
    im = pim.as_pil_image()
    assert im.size == (1000, 1520)
    assert im.getpixel((0, 0)) == 0  # Ensure loaded


@needs_jbig2dec
def test_jbig2_global(resources):
    xobj, _pdf = first_image_in(resources / 'jbig2global.pdf')
    pim = PdfImage(xobj)
    im = pim.as_pil_image()
    assert im.size == (4000, 2864)
    assert im.getpixel((0, 0)) == 255  # Ensure loaded


@needs_jbig2dec
def test_jbig2_global_palette(resources):
    xobj, _pdf = first_image_in(resources / 'jbig2global.pdf')
    xobj.ColorSpace = pikepdf.Array(
        [Name.Indexed, Name.DeviceRGB, 1, b'\x00\x00\x00\xff\xff\xff']
    )
    pim = PdfImage(xobj)
    im = pim.as_pil_image()
    assert im.size == (4000, 2864)
    assert im.getpixel((0, 0)) == 255  # Ensure loaded


def test_ccitt_icc(resources):
    xobj, pdf = first_image_in(resources / 'sandwich.pdf')

    pim = PdfImage(xobj)
    assert pim.icc is None
    bio = BytesIO()
    output_type = pim.extract_to(stream=bio)
    assert output_type == '.tif'
    bio.seek(0)
    assert b'GRAYXYZ' not in bio.read(1000)
    bio.seek(0)
    assert Image.open(bio)

    icc_data = (resources / 'Gray.icc').read_bytes()
    icc_stream = pdf.make_stream(icc_data)
    icc_stream.N = 1
    xobj.ColorSpace = pikepdf.Array([Name.ICCBased, icc_stream])

    pim = PdfImage(xobj)
    assert pim.icc.profile.xcolor_space == 'GRAY'
    bio = BytesIO()
    output_type = pim.extract_to(stream=bio)
    assert output_type == '.tif'
    bio.seek(0)
    assert b'GRAYXYZ' in bio.read(1000)
    bio.seek(0)
    assert Image.open(bio)
