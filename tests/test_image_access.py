# SPDX-FileCopyrightText: 2022 James R. Barlow
# SPDX-License-Identifier: CC0-1.0

from __future__ import annotations

import subprocess
import zlib
from contextlib import contextmanager
from io import BytesIO
from math import ceil
from os import fspath
from pathlib import Path
from subprocess import run
from typing import NamedTuple, Sequence

import PIL
import pytest
from conftest import needs_python_v
from hypothesis import assume, given, note, settings
from hypothesis import strategies as st
from packaging.version import Version
from PIL import Image, ImageChops, ImageCms
from PIL import features as PIL_features

import pikepdf
from pikepdf import (
    Array,
    Dictionary,
    Name,
    Object,
    Operator,
    Pdf,
    PdfError,
    PdfImage,
    PdfInlineImage,
    Stream,
    StreamDecodeLevel,
    parse_content_stream,
)
from pikepdf.models._transcoding import _next_multiple, unpack_subbyte_pixels
from pikepdf.models.image import (
    DependencyError,
    NotExtractableError,
    PdfJpxImage,
    UnsupportedImageTypeError,
)

# pylint: disable=redefined-outer-name


def has_pdfimages():
    try:
        run(['pdfimages', '-v'], check=True, capture_output=True)
    except FileNotFoundError:
        return False
    else:
        return True


requires_pdfimages = pytest.mark.skipif(
    not has_pdfimages(), reason="pdfimages not installed"
)


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
    with Pdf.open(resources / 'image-mono-inline.pdf') as pdf:
        for operands, _command in parse_content_stream(pdf.pages[0]):
            if operands and isinstance(operands[0], PdfInlineImage):
                yield operands[0], pdf
                break


def test_image_from_nonimage(resources):
    with Pdf.open(resources / 'congress.pdf') as pdf:
        contents = pdf.pages[0].Contents
        with pytest.raises(TypeError):
            PdfImage(contents)


def test_image(congress):
    xobj, _ = congress
    pdfimage = PdfImage(xobj)
    pillowimage = pdfimage.as_pil_image()

    assert pillowimage.mode == pdfimage.mode
    assert pillowimage.size == pdfimage.size


def test_imagemask(congress):
    xobj, _ = congress
    assert not PdfImage(xobj).image_mask


def test_imagemask_colorspace(trivial):
    xobj, _ = trivial
    rawimage = xobj
    rawimage.ImageMask = True
    pdfimage = PdfImage(rawimage)
    assert pdfimage.image_mask
    assert pdfimage.colorspace is None


def test_malformed_palette(trivial):
    xobj, _ = trivial
    rawimage = xobj
    rawimage.ColorSpace = [Name.Indexed, 'foo', 'bar']
    pdfimage = PdfImage(rawimage)
    with pytest.raises(ValueError, match="interpret this palette"):
        pdfimage.palette  # pylint: disable=pointless-statement


def test_image_eq(trivial, congress, inline):
    xobj_trivial, _ = trivial
    xobj_congress, _ = congress
    inline_image, _ = inline
    # Note: JPX equality is tested in test_jp2 (if we have a jpeg2000 codec)
    assert PdfImage(xobj_trivial) == PdfImage(xobj_trivial)
    assert PdfImage(xobj_trivial).__eq__(42) is NotImplemented
    assert PdfImage(xobj_trivial) != PdfImage(xobj_congress)

    assert inline_image != PdfImage(xobj_congress)
    assert inline_image.__eq__(42) is NotImplemented


def test_image_replace(congress, outdir):
    xobj, pdf = congress
    pdfimage = PdfImage(xobj)
    pillowimage = pdfimage.as_pil_image()

    grayscale = pillowimage.convert('L')
    grayscale = grayscale.resize((4, 4))  # So it is not obnoxious on error

    xobj.write(zlib.compress(grayscale.tobytes()), filter=Name("/FlateDecode"))
    xobj.ColorSpace = Name("/DeviceGray")
    pdf.save(outdir / 'congress_gray.pdf')


def test_lowlevel_jpeg(congress):
    xobj, _pdf = congress
    raw_bytes = xobj.read_raw_bytes()
    with pytest.raises(PdfError):
        xobj.read_bytes()

    im = Image.open(BytesIO(raw_bytes))
    assert im.format == 'JPEG'

    pim = PdfImage(xobj)
    b = BytesIO()
    pim.extract_to(stream=b)
    b.seek(0)
    im = Image.open(b)
    assert im.size == (xobj.Width, xobj.Height)
    assert im.mode == 'RGB'


def test_lowlevel_replace_jpeg(congress, outdir):
    xobj, pdf = congress
    # This test will modify the PDF so needs its own image
    raw_bytes = xobj.read_raw_bytes()

    im = Image.open(BytesIO(raw_bytes))
    grayscale = im.convert('L')
    grayscale = grayscale.resize((4, 4))  # So it is not obnoxious on error

    xobj.write(zlib.compress(grayscale.tobytes()[:10]), filter=Name("/FlateDecode"))
    xobj.ColorSpace = Name('/DeviceGray')

    pdf.save(outdir / 'congress_gray.pdf')


def test_inline(inline):
    iimage, pdf = inline
    assert iimage.width == 8
    assert not iimage.image_mask
    assert iimage.mode == 'RGB'
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


def test_inline_read(inline):
    iimage, _pdf = inline
    assert iimage.read_bytes()[0:6] == b'\xff\xff\xff\x00\x00\x00'


def test_inline_to_pil(inline):
    iimage, _pdf = inline
    im = iimage.as_pil_image()
    assert im.size == (8, 8) and im.mode == iimage.mode


def test_bits_per_component_missing(congress):
    cong_im, _ = congress
    del cong_im.stream_dict['/BitsPerComponent']
    assert PdfImage(cong_im).bits_per_component == 8


class ImageSpec(NamedTuple):
    bpc: int
    width: int
    height: int
    colorspace: pikepdf.Name
    imbytes: bytes


def pdf_from_image_spec(spec: ImageSpec):
    pdf = pikepdf.new()
    pdfw, pdfh = 36 * spec.width, 36 * spec.height

    pdf.add_blank_page(page_size=(pdfw, pdfh))

    imobj = Stream(
        pdf,
        spec.imbytes,
        BitsPerComponent=spec.bpc,
        ColorSpace=spec.colorspace,
        Width=spec.width,
        Height=spec.height,
        Type=Name.XObject,
        Subtype=Name.Image,
    )

    pdf.pages[0].Contents = Stream(pdf, b'%f 0 0 %f 0 0 cm /Im0 Do' % (pdfw, pdfh))
    pdf.pages[0].Resources = Dictionary(XObject=Dictionary(Im0=imobj))
    pdf.pages[0].MediaBox = Array([0, 0, pdfw, pdfh])

    return pdf


@st.composite
def valid_random_image_spec(
    draw,
    bpcs=st.sampled_from([1, 2, 4, 8, 16]),
    widths=st.integers(min_value=1, max_value=16),
    heights=st.integers(min_value=1, max_value=16),
    colorspaces=st.sampled_from([Name.DeviceGray, Name.DeviceRGB, Name.DeviceCMYK]),
):
    bpc = draw(bpcs)
    width = draw(widths)
    height = draw(heights)
    colorspace = draw(colorspaces)

    min_imbytes = width * height * (2 if bpc == 16 else 1)
    if colorspace == Name.DeviceRGB:
        min_imbytes *= 3
    elif colorspace == Name.DeviceCMYK:
        min_imbytes *= 4
    imbytes = draw(st.binary(min_size=min_imbytes, max_size=2 * min_imbytes))

    return ImageSpec(bpc, width, height, colorspace, imbytes)


@given(spec=valid_random_image_spec(bpcs=st.sampled_from([1, 2, 4, 8])))
@settings(deadline=None)  # For PyPy
def test_image_save_compare(tmp_path_factory, spec):
    pdf = pdf_from_image_spec(spec)
    image = pdf.pages[0].Resources.XObject['/Im0']
    w = image.Width
    h = image.Height
    cs = str(image.ColorSpace)
    bpc = image.BitsPerComponent
    pixeldata = image.read_bytes()

    assume((bpc < 8 and cs == '/DeviceGray') or (bpc == 8))

    outdir = tmp_path_factory.mktemp('image_roundtrip')
    outfile = outdir / f'test{w}{h}{cs[1:]}{bpc}.pdf'
    pdf.save(
        outfile, compress_streams=False, stream_decode_level=StreamDecodeLevel.none
    )

    with Pdf.open(outfile) as p2:
        pim = PdfImage(p2.pages[0].Resources.XObject['/Im0'])

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


def pack_2bit_row(row: Sequence[int]) -> bytes:
    assert len(row) % 4 == 0
    im76 = [s << 6 for s in row[0::4]]
    im54 = [s << 4 for s in row[1::4]]
    im32 = [s << 2 for s in row[2::4]]
    im10 = [s << 0 for s in row[3::4]]
    return bytes(sum(s) for s in zip(im76, im54, im32, im10))


def pack_4bit_row(row: Sequence[int]) -> bytes:
    assert len(row) % 2 == 0
    upper = [s << 4 for s in row[0::2]]
    lower = row[1::2]
    return bytes(sum(s) for s in zip(upper, lower))


@st.composite
def imagelike_data(draw, width, height, bpc, sample_range=None):
    bits_per_byte = 8 // bpc
    stride = _next_multiple(width, bits_per_byte)

    if not sample_range:
        sample_range = (0, 2**bpc - 1)

    if bpc in (2, 4, 8):
        intdata = draw(
            st.lists(
                st.lists(
                    st.integers(*sample_range),
                    min_size=stride,
                    max_size=stride,
                ),
                min_size=height,
                max_size=height,
            )
        )
        if bpc == 8:
            imbytes = b''.join(bytes(row) for row in intdata)
        elif bpc == 4:
            imbytes = b''.join(pack_4bit_row(row) for row in intdata)
        elif bpc == 2:
            imbytes = b''.join(pack_2bit_row(row) for row in intdata)
        assert len(imbytes) > 0
    elif bpc == 1:
        imdata = draw(
            st.lists(
                st.integers(0, 255 if sample_range[1] > 0 else 0),
                min_size=height * _next_multiple(width, 8),
                max_size=height * _next_multiple(width, 8),
            )
        )
        imbytes = bytes(imdata)
    return imbytes


class PaletteImageSpec(NamedTuple):
    bpc: int
    width: int
    height: int
    hival: int
    colorspace: pikepdf.Name
    palette: bytes
    imbytes: bytes


def pdf_from_palette_image_spec(spec: PaletteImageSpec):
    pdf = pikepdf.new()
    pdfw, pdfh = 36 * spec.width, 36 * spec.height

    pdf.add_blank_page(page_size=(pdfw, pdfh))

    imobj = Stream(
        pdf,
        spec.imbytes,
        BitsPerComponent=spec.bpc,
        ColorSpace=Array([Name.Indexed, spec.colorspace, spec.hival, spec.palette]),
        Width=spec.width,
        Height=spec.height,
        Type=Name.XObject,
        Subtype=Name.Image,
    )

    pdf.pages[0].Contents = Stream(pdf, b'%f 0 0 %f 0 0 cm /Im0 Do' % (pdfw, pdfh))
    pdf.pages[0].Resources = Dictionary(XObject=Dictionary(Im0=imobj))
    pdf.pages[0].MediaBox = Array([0, 0, pdfw, pdfh])

    return pdf


@st.composite
def valid_random_palette_image_spec(
    draw,
    bpcs=st.sampled_from([1, 2, 4, 8]),
    widths=st.integers(min_value=1, max_value=16),
    heights=st.integers(min_value=1, max_value=16),
    colorspaces=st.sampled_from([Name.DeviceGray, Name.DeviceRGB, Name.DeviceCMYK]),
    palette=None,
):
    bpc = draw(bpcs)
    width = draw(widths)
    height = draw(heights)
    colorspace = draw(colorspaces)
    hival = draw(st.integers(min_value=0, max_value=(2**bpc) - 1))

    imbytes = draw(imagelike_data(width, height, bpc, (0, hival)))

    channels = (
        1
        if colorspace == Name.DeviceGray
        else 3
        if colorspace == Name.DeviceRGB
        else 4
        if colorspace == Name.DeviceCMYK
        else 0
    )

    if not palette:
        palette = draw(
            st.binary(min_size=channels * (hival + 1), max_size=channels * (hival + 1))
        )

    return PaletteImageSpec(bpc, width, height, hival, colorspace, palette, imbytes)


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
    assert pim.mode == 'P'
    assert pim.bits_per_component == bpc

    outstream = BytesIO()
    pim.extract_to(stream=outstream)

    im_pal = pim.as_pil_image()
    im = im_pal.convert('RGB')
    assert im.getpixel((1, 1)) == rgb


@contextmanager
def first_image_from_pdfimages(pdf, tmpdir):
    if not has_pdfimages():
        pytest.skip("Need pdfimages for this test")

    pdf.save(tmpdir / 'in.pdf')

    run(
        ['pdfimages', '-q', '-png', fspath(tmpdir / 'in.pdf'), fspath('pdfimage')],
        cwd=fspath(tmpdir),
        check=True,
    )

    outpng = tmpdir / 'pdfimage-000.png'
    assert outpng.exists()
    with Image.open(outpng) as im:
        yield im


@given(spec=valid_random_palette_image_spec())
@settings(deadline=2000)
def test_image_palette2(spec, tmp_path_factory):
    pdf = pdf_from_palette_image_spec(spec)
    pim = PdfImage(pdf.pages[0].Resources.XObject['/Im0'])

    im1 = pim.as_pil_image()

    with first_image_from_pdfimages(
        pdf, tmp_path_factory.mktemp('test_image_palette2')
    ) as im2:
        if pim.palette.base_colorspace == 'CMYK' and im1.size == im2.size:
            return  # Good enough - CMYK is hard...

        if im1.mode == im2.mode:
            diff = ImageChops.difference(im1, im2)
        else:
            diff = ImageChops.difference(im1.convert('RGB'), im2.convert('RGB'))

        if diff.getbbox():
            if pim.palette.base_colorspace in ('L', 'RGB', 'CMYK') and im2.mode == '1':
                note("pdfimages bug - 1bit image stripped of palette")
                return

        assert (
            not diff.getbbox()
        ), f"{diff.getpixel((0, 0))}, {im1.getpixel((0,0))}, {im2.getpixel((0,0))}"


def test_bool_in_inline_image():
    piim = PdfInlineImage(image_data=b'', image_object=(Name.IM, True))
    assert piim.image_mask


@pytest.mark.skipif(
    not PIL_features.check_codec('jpg_2000'), reason='no JPEG2000 codec'
)
def test_jp2(first_image_in):
    xobj, _pdf = first_image_in('pike-jp2.pdf')
    pim = PdfImage(xobj)
    assert isinstance(pim, PdfJpxImage)

    assert '/JPXDecode' in pim.filters
    assert pim.colorspace == '/DeviceRGB'
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

    result = pim.extract_to(fileprefix=(outdir / 'image'))
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
    assert pim.mode == 'L'  # It may be 1 bit per pixel but it's more complex than that
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

    xobj.DecodeParms.BlackIs1 = True
    im = pim.as_pil_image()
    im = im.convert('L')
    assert im.getpixel((0, 0)) == 255, "Expected white background"

    xobj.DecodeParms.BlackIs1 = False
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


# Unforuntately pytest cannot test for this using "with pytest.warns(...)".
# Suppression is the best we can manage
suppress_unraisable_jbigdec_error_warning = pytest.mark.filterwarnings(
    "ignore:.*jbig2dec error.*:pytest.PytestUnraisableExceptionWarning"
)


@needs_python_v("3.8", reason="for pytest unraisable exception support")
@suppress_unraisable_jbigdec_error_warning
def test_jbig2_not_available(jbig2, monkeypatch):
    xobj, _pdf = jbig2
    pim = PdfImage(xobj)

    class NotFoundJBIG2Decoder(pikepdf.jbig2.JBIG2DecoderInterface):
        def check_available(self):
            raise DependencyError('jbig2dec') from FileNotFoundError('jbig2dec')

        def decode_jbig2(self, jbig2: bytes, jbig2_globals: bytes) -> bytes:
            raise FileNotFoundError('jbig2dec')

    monkeypatch.setattr(pikepdf.jbig2, 'get_decoder', NotFoundJBIG2Decoder)

    assert not pikepdf.jbig2.get_decoder().available()

    with pytest.raises(DependencyError):
        pim.as_pil_image()


needs_jbig2dec = pytest.mark.skipif(
    not pikepdf.jbig2.get_decoder().available(), reason="jbig2dec not installed"
)


@needs_jbig2dec
def test_jbig2_extractor(jbig2):
    xobj, _pdf = jbig2
    pikepdf.jbig2.get_decoder().decode_jbig2(xobj.read_raw_bytes(), b'')


@needs_jbig2dec
def test_jbig2(jbig2):
    xobj, _pdf = jbig2
    pim = PdfImage(xobj)
    im = pim.as_pil_image()
    assert im.size == (1000, 1520)
    assert im.getpixel((0, 0)) == 0  # Ensure loaded


@needs_jbig2dec
def test_jbig2_decodeparms_null_issue317(jbig2):
    xobj, _pdf = jbig2
    xobj.stream_dict = Object.parse(
        b'''<< /BitsPerComponent 1
               /ColorSpace /DeviceGray
               /Filter [ /JBIG2Decode ]
               /DecodeParms null
               /Height 1520
               /Length 19350
               /Subtype /Image
               /Type /XObject
               /Width 1000
            >>'''
    )
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


@needs_python_v("3.8", reason="for pytest unraisable exception support")
@suppress_unraisable_jbigdec_error_warning
def test_jbig2_error(first_image_in, monkeypatch):
    xobj, _pdf = first_image_in('jbig2global.pdf')
    pim = PdfImage(xobj)

    class BrokenJBIG2Decoder(pikepdf.jbig2.JBIG2DecoderInterface):
        def check_available(self):
            return

        def decode_jbig2(self, jbig2: bytes, jbig2_globals: bytes) -> bytes:
            raise subprocess.CalledProcessError(1, 'jbig2dec')

    monkeypatch.setattr(pikepdf.jbig2, 'get_decoder', BrokenJBIG2Decoder)

    pim = PdfImage(xobj)
    with pytest.raises(PdfError, match="unfilterable stream"):
        pim.as_pil_image()


@needs_python_v("3.8", reason="for pytest unraisable exception support")
@suppress_unraisable_jbigdec_error_warning
def test_jbig2_too_old(first_image_in, monkeypatch):
    xobj, _pdf = first_image_in('jbig2global.pdf')
    pim = PdfImage(xobj)

    class OldJBIG2Decoder(pikepdf.jbig2.JBIG2Decoder):
        def _version(self):
            return Version('0.12')

    monkeypatch.setattr(pikepdf.jbig2, 'get_decoder', OldJBIG2Decoder)

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


def test_decodeparms_filter_alternates():
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
    'base, hival, bits, palette, expect_type, expect_mode',
    [
        (Name.DeviceGray, 4, 8, b'\x00\x40\x80\xff', 'L', 'P'),
        (Name.DeviceCMYK, 4, 8, CMYK_PALETTE, 'CMYK', 'P'),
        (Name.DeviceGray, 4, 4, b'\x04\x08\x02\x0f', 'L', 'P'),
    ],
)
def test_palette_nonrgb(base, hival, bits, palette, expect_type, expect_mode):
    pdf = pikepdf.new()
    imobj = Stream(
        pdf,
        b'\x00\x01\x02\x03' * 16,
        BitsPerComponent=bits,
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
    # pim.extract_to(fileprefix=f'palette_nonrgb_{expect_type}_{bits}')
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


@given(
    spec=valid_random_image_spec(
        bpcs=st.sampled_from([2, 4]),
        colorspaces=st.just(Name.DeviceGray),
        widths=st.integers(1, 7),
        heights=st.integers(1, 7),
    )
)
def test_grayscale_stride(spec):
    pdf = pdf_from_image_spec(spec)
    pim = PdfImage(pdf.pages[0].Resources.XObject.Im0)
    assert pim.mode == 'L'
    imdata = pim.read_bytes()
    w = pim.width
    imdata_unpacked_view, stride = unpack_subbyte_pixels(
        imdata, pim.size, pim.bits_per_component
    )
    imdata_unpacked = bytes(imdata_unpacked_view)

    bio = BytesIO()
    pim.extract_to(stream=bio)
    im = Image.open(bio)
    assert im.mode == 'L' and im.size == pim.size

    for n, pixel in enumerate(im.getdata()):
        idx = stride * (n // w) + (n % w)
        assert imdata_unpacked[idx] == pixel


@requires_pdfimages
@given(spec=valid_random_image_spec())
def test_random_image(spec, tmp_path_factory):
    pdf = pdf_from_image_spec(spec)
    pim = PdfImage(pdf.pages[0].Resources.XObject.Im0)
    bio = BytesIO()
    colorspace = pim.colorspace
    width = pim.width
    height = pim.height
    bpc = pim.bits_per_component
    imbytes = pim.read_bytes()
    try:
        result_extension = pim.extract_to(stream=bio)
        assert result_extension in ('.png', '.tiff')
    except ValueError as e:
        if 'not enough image data' in str(e):
            return
        elif 'buffer is not large enough' in str(e):
            ncomps = (
                4
                if colorspace == Name.DeviceCMYK
                else 3
                if colorspace == Name.DeviceRGB
                else 1
            )
            assert ceil(bpc / 8) * width * height * ncomps > len(imbytes)
            return
        raise
    except PIL.UnidentifiedImageError:
        if len(imbytes) == 0:
            return
        raise
    except UnsupportedImageTypeError:
        if colorspace in (Name.DeviceRGB, Name.DeviceCMYK) and bpc < 8:
            return
        if bpc == 16:
            return
        raise

    bio.seek(0)
    im = Image.open(bio)
    assert im.mode == pim.mode
    assert im.size == pim.size

    outprefix = f'{width}x{height}x{im.mode}-'
    tmpdir = tmp_path_factory.mktemp(outprefix)
    pdf.save(tmpdir / 'pdf.pdf')

    # We don't have convenient CMYK checking tools
    if im.mode == 'CMYK':
        return

    im.save(tmpdir / 'pikepdf.png')
    Path(tmpdir / 'imbytes.bin').write_bytes(imbytes)
    run(
        [
            'pdfimages',
            '-png',
            fspath('pdf.pdf'),
            fspath('pdfimage'),  # omit suffix
        ],
        cwd=fspath(tmpdir),
        check=True,
    )
    outpng = tmpdir / 'pdfimage-000.png'
    assert outpng.exists()
    im_roundtrip = Image.open(outpng)

    assert im.size == im_roundtrip.size

    diff = ImageChops.difference(im, im_roundtrip)
    assert not diff.getbbox()
    # if diff.getbbox():
    #     im.save('im1.png')
    #     im_roundtrip.save('im2.png')
    #     diff.save('imdiff.png')
    #     breakpoint()
    #     assert False


class StencilMaskSpec(NamedTuple):
    width: int
    height: int
    imbytes: bytes

    def to_pdf(self):
        pdf = pikepdf.new()
        pdfw, pdfh = 36 * self.width, 36 * self.height

        pdf.add_blank_page(page_size=(pdfw, pdfh))

        imobj = Stream(
            pdf,
            self.imbytes,
            Width=self.width,
            Height=self.height,
            Type=Name.XObject,
            Subtype=Name.Image,
            ImageMask=True,
        )

        pdf.pages[0].Contents = Stream(
            pdf, b'%f 0 0 %f 0 0 cm 0.5 0.75 1.0 rg /Im0 Do' % (pdfw, pdfh)
        )
        pdf.pages[0].Resources = Dictionary(XObject=Dictionary(Im0=imobj))
        pdf.pages[0].MediaBox = Array([0, 0, pdfw, pdfh])
        return pdf


@st.composite
def valid_random_stencil_mask_spec(
    draw,
    widths=st.integers(min_value=1, max_value=16),
    heights=st.integers(min_value=1, max_value=16),
):
    width = draw(widths)
    height = draw(heights)

    min_imbytes = _next_multiple(width, 8) * height // 8
    imbytes = draw(st.binary(min_size=min_imbytes, max_size=min_imbytes))

    return StencilMaskSpec(width, height, imbytes)


@given(spec=valid_random_stencil_mask_spec())
def test_extract_stencil_mask(spec):
    pdf = spec.to_pdf()
    pim = PdfImage(pdf.pages[0].Resources.XObject.Im0)
    bio = BytesIO()
    pim.extract_to(stream=bio)
    im = Image.open(bio)
    assert im.mode == '1'
