import subprocess
import zlib
from contextlib import contextmanager
from io import BytesIO
from os import fspath
from pathlib import Path

import pytest
from PIL import Image, ImageCms
from PIL import features as PIL_features

import pikepdf
from pikepdf import (
    Array,
    Dictionary,
    Name,
    Operator,
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
    PdfJpxImage,
    UnsupportedImageTypeError,
)

# pylint: disable=redefined-outer-name


@pytest.fixture
def first_image_in(resources, request):
    pdf = None

    def opener(filename):
        nonlocal pdf
        pdf = Pdf.open(resources / filename)
        pdfimagexobj = next(iter(pdf.pages[0].images.values()))
        return pdfimagexobj, pdf

    def closer():
        if pdf:
            pdf.close()

    request.addfinalizer(closer)

    return opener


@pytest.fixture
def congress(first_image_in):
    return first_image_in('congress.pdf')


@pytest.fixture
def sandwich(first_image_in):
    return first_image_in('sandwich.pdf')


@pytest.fixture
def jbig2(first_image_in):
    return first_image_in('jbig2.pdf')


@pytest.fixture
def trivial(first_image_in):
    return first_image_in('pal-1bit-trivial.pdf')


@pytest.fixture
def inline(resources):
    pdf = Pdf.open(resources / 'image-mono-inline.pdf')
    for operands, _command in parse_content_stream(pdf.pages[0]):
        if operands and isinstance(operands[0], PdfInlineImage):
            yield operands[0], pdf
    pdf.close()


def test_image_from_nonimage(resources):
    pdf = Pdf.open(resources / 'congress.pdf')
    contents = pdf.pages[0].Contents
    with pytest.raises(TypeError):
        PdfImage(contents)


def test_image(congress):
    pdfimage = PdfImage(congress[0])
    pillowimage = pdfimage.as_pil_image()

    assert pillowimage.mode == pdfimage.mode
    assert pillowimage.size == pdfimage.size


def test_imagemask(congress):
    assert not PdfImage(congress[0]).image_mask


def test_imagemask_colorspace(trivial):
    rawimage = trivial[0]
    rawimage.ImageMask = True
    pdfimage = PdfImage(rawimage)
    assert pdfimage.image_mask
    assert pdfimage.colorspace is None


def test_malformed_palette(trivial):
    rawimage = trivial[0]
    rawimage.ColorSpace = [Name.Indexed, 'foo', 'bar']
    pdfimage = PdfImage(rawimage)
    with pytest.raises(ValueError, match="interpret this palette"):
        pdfimage.palette  # pylint: disable=pointless-statement


def test_image_eq(trivial, congress, inline):
    # Note: JPX equality is tested in test_jp2 (if we have a jpeg2000 codec)
    assert PdfImage(trivial[0]) == PdfImage(trivial[0])
    assert PdfImage(trivial[0]).__eq__(42) is NotImplemented
    assert PdfImage(trivial[0]) != PdfImage(congress[0])

    assert inline != PdfImage(congress[0])
    assert inline.__eq__(42) is NotImplemented


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


def test_inline(inline):
    iimage, pdf = inline
    assert iimage.width == 8
    assert not iimage.image_mask
    assert iimage.mode == 'RGB'
    assert iimage.is_inline
    assert iimage.colorspace == '/DeviceRGB'
    assert 'PdfInlineImage' in repr(iimage)

    unparsed = iimage.unparse()
    assert b'/W 8' in unparsed, "inline images should have abbreviated metadata"
    assert b'/Width 8' not in unparsed, "abbreviations expanded in inline image"

    cs = pdf.make_stream(unparsed)
    for operands, command in parse_content_stream(cs):
        if operands and isinstance(operands[0], PdfInlineImage):
            assert command == Operator('INLINE IMAGE')
            reparsed_iim = operands[0]
            assert reparsed_iim == iimage


def test_inline_extract(inline):
    iimage, _pdf = inline
    bio = BytesIO()
    iimage.extract_to(stream=bio)
    bio.seek(0)
    im = Image.open(bio)
    assert im.size == (8, 8) and im.mode == iimage.mode


def test_inline_to_pil(inline):
    iimage, _pdf = inline
    im = iimage.as_pil_image()
    assert im.size == (8, 8) and im.mode == iimage.mode


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
        (1, 1, b'\xff\x80\x40\x20', '/DeviceCMYK', 8),
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
    outfile = outdir / f'test{w}{h}{cs[1:]}{bpc}.pdf'
    pdf.save(
        outfile, compress_streams=False, stream_decode_level=StreamDecodeLevel.none
    )

    with Pdf.open(outfile) as p2:
        pim = PdfImage(p2.pages[0].Resources.XObject['/Im1'])

        assert pim.bits_per_component == bpc
        assert pim.colorspace == cs
        assert pim.width == w
        assert pim.height == h
        if cs == '/DeviceRGB':
            assert pim.mode == 'RGB'
        elif cs == '/DeviceGray' and bpc == 8:
            assert pim.mode == 'L'
        elif cs == '/DeviceCMYK':
            assert pim.mode == 'CMYK'
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
def test_direct_extract(first_image_in, filename, bpc, filters, ext, mode, format_):
    xobj, _pdf = first_image_in(filename)
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
def test_jp2(first_image_in):
    xobj, pdf = first_image_in('pike-jp2.pdf')
    pim = PdfImage(xobj)
    assert isinstance(pim, PdfJpxImage)

    assert '/JPXDecode' in pim.filters
    assert pim.colorspace == '/DeviceRGB'
    assert not pim.is_inline
    assert not pim.indexed
    assert pim.mode == 'RGB'
    assert pim.bits_per_component == 8
    assert pim.__eq__(42) is NotImplemented
    assert pim == PdfImage(xobj)

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


def test_icc_use(first_image_in):
    xobj, _pdf = first_image_in('1biticc.pdf')

    pim = PdfImage(xobj)
    assert pim.mode == '1'
    assert pim.colorspace == '/ICCBased'
    assert pim.bits_per_component == 1

    assert pim.icc.profile.xcolor_space == 'GRAY'


def test_icc_extract(first_image_in):
    xobj, _pdf = first_image_in('aquamarine-cie.pdf')

    pim = PdfImage(xobj)
    assert pim.as_pil_image().info['icc_profile'] == pim.icc.tobytes()


def test_icc_palette(first_image_in):
    xobj, _pdf = first_image_in('pink-palette-icc.pdf')
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


def test_stacked_compression(first_image_in):
    xobj, _pdf = first_image_in('pike-flate-jp2.pdf')

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


def test_imagemagick_uses_rle_compression(first_image_in):
    xobj, _rle = first_image_in('rle.pdf')

    pim = PdfImage(xobj)
    im = pim.as_pil_image()
    assert im.getpixel((5, 5)) == (255, 128, 0)


def test_jbig2_not_available(jbig2, monkeypatch):
    xobj, _pdf = jbig2
    pim = PdfImage(xobj)

    def raise_filenotfound(*args, **kwargs):
        raise FileNotFoundError('jbig2dec')

    monkeypatch.setattr(pikepdf.jbig2, 'run', raise_filenotfound)

    assert not pikepdf.jbig2.jbig2dec_available()

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
def test_jbig2_global(first_image_in):
    xobj, _pdf = first_image_in('jbig2global.pdf')
    pim = PdfImage(xobj)
    im = pim.as_pil_image()
    assert im.size == (4000, 2864)
    assert im.getpixel((0, 0)) == 255  # Ensure loaded


@needs_jbig2dec
def test_jbig2_global_palette(first_image_in):
    xobj, _pdf = first_image_in('jbig2global.pdf')
    xobj.ColorSpace = pikepdf.Array(
        [Name.Indexed, Name.DeviceRGB, 1, b'\x00\x00\x00\xff\xff\xff']
    )
    pim = PdfImage(xobj)
    im = pim.as_pil_image()
    assert im.size == (4000, 2864)
    assert im.getpixel((0, 0)) == 255  # Ensure loaded


def test_jbig2_error(first_image_in, monkeypatch):
    xobj, _pdf = first_image_in('jbig2global.pdf')
    pim = PdfImage(xobj)
    monkeypatch.setattr(pikepdf.jbig2, 'jbig2dec_available', lambda: True)

    def raise_calledprocesserror(*args, **kwargs):
        raise subprocess.CalledProcessError(1, 'jbig2dec')

    monkeypatch.setattr(pikepdf.jbig2, 'run', raise_calledprocesserror)

    pim = PdfImage(xobj)
    with pytest.raises(subprocess.CalledProcessError):
        pim.as_pil_image()


def test_jbig2_too_old(first_image_in, monkeypatch):
    xobj, _pdf = first_image_in('jbig2global.pdf')
    pim = PdfImage(xobj)

    def run_version_override(subprocargs, *args, **kwargs):
        if '--version' in subprocargs:
            return subprocess.CompletedProcess(subprocargs, 0, 'jbig2dec 0.12\n')
        return subprocess.run(subprocargs, *args, **kwargs)

    monkeypatch.setattr(pikepdf.jbig2, 'run', run_version_override)

    pim = PdfImage(xobj)
    with pytest.raises(DependencyError, match='too old'):
        pim.as_pil_image()


def test_ccitt_icc(first_image_in, resources):
    xobj, pdf = first_image_in('sandwich.pdf')

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


def test_invalid_icc(first_image_in):
    xobj, _pdf = first_image_in('pink-palette-icc.pdf')

    cs = xobj.ColorSpace[1][1]  # [/Indexed [/ICCBased <stream>]]
    cs.write(b'foobar')  # corrupt the ICC profile
    with pytest.raises(
        UnsupportedImageTypeError, match="ICC profile corrupt or not readable"
    ):
        pim = PdfImage(xobj)
        assert pim.icc is not None


def test_dict_or_array_dict():
    pdf = pikepdf.new()
    imobj = Stream(
        pdf,
        b'dummy',
        BitsPerComponent=1,
        ColorSpace=Name.DeviceGray,
        DecodeParms=Array(
            [
                Dictionary(
                    BlackIs1=False,
                    Columns=16,
                    K=-1,
                )
            ]
        ),
        Filter=Array([Name.CCITTFaxDecode]),
        Height=16,
        Width=16,
        Type=Name.XObject,
        Subtype=Name.Image,
    )
    pim = pikepdf.PdfImage(imobj)
    assert pim.decode_parms[0].K == -1  # Check that array of dict is unpacked properly


CMYK_RED = b'\x00\xc0\xc0\x15'
CMYK_GREEN = b'\x90\x00\xc0\x15'
CMYK_BLUE = b'\xc0\xa0\x00\x15'
CMYK_PINK = b'\x04\xc0\x00\x15'

CMYK_PALETTE = CMYK_RED + CMYK_GREEN + CMYK_BLUE + CMYK_PINK


@pytest.mark.parametrize(
    'base, hival, palette, expect_type, expect_mode',
    [
        (Name.DeviceGray, 4, b'\x00\x40\x80\xff', 'L', 'P'),
        (Name.DeviceCMYK, 4, CMYK_PALETTE, 'CMYK', 'P'),
    ],
)
def test_palette_nonrgb(base, hival, palette, expect_type, expect_mode):
    pdf = pikepdf.new()
    imobj = Stream(
        pdf,
        b'\x00\x01\x02\x03' * 16,
        BitsPerComponent=8,
        ColorSpace=Array([Name.Indexed, base, hival, palette]),
        Width=16,
        Height=4,
        Type=Name.XObject,
        Subtype=Name.Image,
    )
    pim = pikepdf.PdfImage(imobj)
    assert pim.palette == (expect_type, palette)
    pim.extract_to(stream=BytesIO())
    # To view images:
    # pim.extract_to(fileprefix=f'palette_nonrgb_{expect_type}')
    assert pim.mode == expect_mode


def test_extract_to_mutex_params(sandwich):
    pdfimage = PdfImage(sandwich[0])
    with pytest.raises(ValueError, match="Cannot set both"):
        pdfimage.extract_to(stream=BytesIO(), fileprefix='anything')


def test_separation():
    # Manually construct a 2"x1" document with a Separation
    # colorspace that devices a single "spot" color channel named
    # "LogoGreen". Define a conversion to standard CMYK that assigns
    # CMYK equivalents. Copied example from PDF RM.
    # LogoGreen is a teal-ish green. First panel is white to full green,
    # second is green to full white. RGB ~= (31, 202, 113)
    pdf = pikepdf.new()
    pdf.add_blank_page(page_size=(144, 72))

    # pikepdf does not interpret this - it is for the PDF viewer
    # Explanation:
    #   X is implicitly loaded to stack
    #   dup: X X
    #   0.84 mul: X 0.84X
    #   exch: 0.84X X
    #   0.00: 0.84X X 0.00
    #   exch: 0.84X 0.00 X
    #   dup: 0.84X 0.00 X X
    #   0.44 mul: 0.84X 0.00 X 0.44X
    #   exch: 0.84X 0.00 0.44X X
    #   0.21mul: 0.84X 0.00 0.44X 0.21X
    # X -> {0.84X, 0, 0.44X, 0.21X}
    tint_transform_logogreen_to_cmyk = b'''
    {
        dup 0.84 mul
        exch 0.00 exch dup 0.44 mul
        exch 0.21 mul
    }
    '''

    cs = Array(
        [
            Name.Separation,
            Name.LogoGreen,
            Name.DeviceCMYK,
            Stream(
                pdf,
                tint_transform_logogreen_to_cmyk,
                FunctionType=4,
                Domain=[0.0, 1.0],
                Range=[0.0, 1.0, 0.0, 1.0, 0.0, 1.0, 0.0, 1.0],
            ),
        ]
    )

    def check_pim(imobj, idx):
        pim = pikepdf.PdfImage(imobj)
        assert pim.mode == 'Separation'
        assert pim.is_separation
        assert not pim.is_device_n
        assert pim.indexed == idx
        assert repr(pim)
        with pytest.raises(pikepdf.models.image.HifiPrintImageNotTranscodableError):
            pim.extract_to(stream=BytesIO())

    imobj0 = Stream(
        pdf,
        bytes(range(0, 256)),
        BitsPerComponent=8,
        ColorSpace=cs,
        Width=16,
        Height=16,
        Type=Name.XObject,
        Subtype=Name.Image,
    )
    check_pim(imobj0, idx=False)

    imobj1 = Stream(
        pdf,
        bytes(range(0, 256)),
        BitsPerComponent=8,
        ColorSpace=Array([Name.Indexed, cs, 255, bytes(range(255, -1, -1))]),
        Width=16,
        Height=16,
        Type=Name.XObject,
        Subtype=Name.Image,
    )
    check_pim(imobj1, idx=True)

    pdf.pages[0].Contents = Stream(
        pdf, b'72 0 0 72 0 0 cm /Im0 Do 1 0 0 1 1 0 cm /Im1 Do'
    )
    pdf.pages[0].Resources = Dictionary(XObject=Dictionary(Im0=imobj0, Im1=imobj1))
    # pdf.save("separation.pdf")


def test_devicen():
    # Manually construct a 2"x1" document with a DeviceN
    # colorspace that devices a single "spot" color channel named
    # "Black". Define a conversion to standard CMYK that assigns
    # C=0 M=0 Y=0 and lets black through. The result should appear as a
    # gradient from white (top left) to black (bottom right) in the
    # left cell, and black to white in the right cell.
    pdf = pikepdf.new()
    pdf.add_blank_page(page_size=(144, 72))

    # Postscript function to map X -> CMYK={0, 0, 0, X}
    # Explanation:
    #   X is implicitly on the stack
    #   0 0 0 <- load three zeros on to stack
    #   stack contains: X 0 0 0
    #   4 -1 roll <- roll stack 4 elements -1 times, meaning the order is reversed
    #   stack contains: 0 0 0 X
    # pikepdf currently does not interpret tint transformation functions. This
    # is done so that the output test file can be checked in a PDF viewer.
    tint_transform_k_to_cmyk = b'{0 0 0 4 -1 roll}'

    cs = Array(
        [
            Name.DeviceN,
            Array([Name.Black]),
            Name.DeviceCMYK,
            Stream(
                pdf,
                tint_transform_k_to_cmyk,
                FunctionType=4,
                Domain=[0.0, 1.0],
                Range=[0.0, 1.0, 0.0, 1.0, 0.0, 1.0, 0.0, 1.0],
            ),
        ]
    )

    def check_pim(imobj, idx):
        pim = pikepdf.PdfImage(imobj)
        assert pim.mode == 'DeviceN'
        assert pim.is_device_n
        assert not pim.is_separation
        assert pim.indexed == idx
        assert repr(pim)
        with pytest.raises(pikepdf.models.image.HifiPrintImageNotTranscodableError):
            pim.extract_to(stream=BytesIO())

    imobj0 = Stream(
        pdf,
        bytes(range(0, 256)),
        BitsPerComponent=8,
        ColorSpace=cs,
        Width=16,
        Height=16,
        Type=Name.XObject,
        Subtype=Name.Image,
    )
    check_pim(imobj0, idx=False)

    imobj1 = Stream(
        pdf,
        bytes(range(0, 256)),
        BitsPerComponent=8,
        ColorSpace=Array([Name.Indexed, cs, 255, bytes(range(255, -1, -1))]),
        Width=16,
        Height=16,
        Type=Name.XObject,
        Subtype=Name.Image,
    )
    check_pim(imobj1, idx=True)

    pdf.pages[0].Contents = Stream(
        pdf, b'72 0 0 72 0 0 cm /Im0 Do 1 0 0 1 1 0 cm /Im1 Do'
    )
    pdf.pages[0].Resources = Dictionary(XObject=Dictionary(Im0=imobj0, Im1=imobj1))
    # pdf.save('devicen.pdf')
