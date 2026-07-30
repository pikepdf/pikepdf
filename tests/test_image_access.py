# SPDX-FileCopyrightText: 2022 James R. Barlow
# SPDX-License-Identifier: CC0-1.0

from __future__ import annotations

import sys
import zlib
from collections.abc import Sequence
from contextlib import contextmanager, nullcontext
from io import BytesIO
from math import ceil
from os import fspath
from pathlib import Path
from subprocess import run
from typing import NamedTuple

import PIL
import pytest
from hypothesis import assume, given, note, settings
from hypothesis import strategies as st
from PIL import Image, ImageChops, ImageCms
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
from pikepdf.models._transcoding import (
    _next_multiple,
    fix_1bit_palette_image,
    unpack_subbyte_pixels,
)
from pikepdf.models.image import (
    ImageDecompressionError,
    PdfJpxImage,
    UnsupportedImageTypeError,
)

if sys.version_info.releaselevel in ('alpha', 'beta'):
    # When testing a pre-release, we are likely building Pillow from source, and it will
    # be missing several of its libraries and trigger errors around missing libtiff and
    # the CMS library. Rather than trying to get a full build of Pillow, just skip these
    # tests.
    pytest.skip(
        "skipping image tests on alpha/beta due to complex Pillow deps",
        allow_module_level=True,
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
        pdfimagexobj = next(iter(pdf.pages[0].get_images(recursive=False).values()))
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


def test_imagemask_decode(trivial):
    xobj, _ = trivial
    rawimage = xobj
    rawimage.ImageMask = True
    pdfimage = PdfImage(rawimage)
    assert pdfimage.image_mask
    assert pdfimage._decode_array == (0.0, 1.0)


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


def _inline_named_cs_pdf(cs_definition, cs_name=b'/CustomRGB', *, define=True):
    """One-page PDF with an inline image referencing a named colour space."""
    pdf = Pdf.new()
    pdf.add_blank_page(page_size=(72, 72))
    page = pdf.pages[0]
    if define:
        cs_obj = pdf.make_indirect(cs_definition)
        page.Resources = Dictionary(ColorSpace=Dictionary(CustomRGB=cs_obj))
    else:
        page.Resources = Dictionary(ColorSpace=Dictionary())
    # 4x4 RGB pixels (page size must be >= 3 PDF units for extraction); bytes
    # chosen to avoid a spurious 'EI' inline-image delimiter.
    data = bytes([10, 20, 30]) * 16
    content = b'q\nBI /W 4 /H 4 /BPC 8 /CS ' + cs_name + b' ID\n' + data + b'\nEI\nQ\n'
    page.Contents = pdf.make_stream(content)
    return pdf


def _first_inline_image(pdf):
    for operands, _cmd in parse_content_stream(pdf.pages[0]):
        if operands and isinstance(operands[0], PdfInlineImage):
            return operands[0]
    return None


CALRGB_CS = [
    Name.CalRGB,
    {
        '/WhitePoint': [0.9505, 1.0, 1.089],
        '/Gamma': [2.2, 2.2, 2.2],
        '/Matrix': [
            0.4124,
            0.2126,
            0.0193,
            0.3576,
            0.7152,
            0.1192,
            0.1805,
            0.0722,
            0.9505,
        ],
    },
]


def test_inline_named_colorspace_resolves():
    pdf = _inline_named_cs_pdf(Array(CALRGB_CS))
    iimage = _first_inline_image(pdf)
    assert iimage is not None
    assert iimage.colorspace == '/CalRGB'
    assert iimage.mode == 'RGB'


def test_inline_named_colorspace_extracts():
    pdf = _inline_named_cs_pdf(Array(CALRGB_CS))
    iimage = _first_inline_image(pdf)
    assert iimage is not None
    im = iimage.as_pil_image()
    assert im.mode == 'RGB'
    assert im.size == (4, 4)


def test_inline_unknown_named_colorspace_errors():
    # The inline image names /CustomRGB but it is not defined in /Resources.
    pdf = _inline_named_cs_pdf(Array(CALRGB_CS), define=False)
    iimage = _first_inline_image(pdf)
    assert iimage is not None
    with pytest.raises(NotImplementedError):
        iimage.colorspace  # noqa: B018


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
    # Use strings for colorspace names and convert to Name inside the function
    # to avoid creating persistent pikepdf.Object instances at module level
    # (which nanobind reports as shutdown leaks).
    colorspaces=st.sampled_from(['DeviceGray', 'DeviceRGB', 'DeviceCMYK']),
):
    bpc = draw(bpcs)
    width = draw(widths)
    height = draw(heights)
    colorspace_name = draw(colorspaces)
    colorspace = Name(f'/{colorspace_name}')

    min_imbytes = width * height * (2 if bpc == 16 else 1)
    if colorspace == Name.DeviceRGB:
        min_imbytes *= 3
    elif colorspace == Name.DeviceCMYK:
        min_imbytes *= 4
    imbytes = draw(st.binary(min_size=min_imbytes, max_size=2 * min_imbytes))

    return ImageSpec(bpc, width, height, colorspace, imbytes)


@given(spec=valid_random_image_spec(bpcs=st.sampled_from([1, 2, 4, 8, 16])))
@settings(deadline=None)  # For PyPy
def test_image_save_compare(tmp_path_factory, spec):
    pdf = pdf_from_image_spec(spec)
    image = pdf.pages[0].Resources.XObject['/Im0']
    w = image.Width
    h = image.Height
    cs = str(image.ColorSpace)
    bpc = image.BitsPerComponent
    pixeldata = image.read_bytes()

    assume(
        (bpc < 8 and cs == '/DeviceGray')
        or (bpc == 8)
        or (bpc == 16 and cs == '/DeviceGray')
    )

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
        elif cs == '/DeviceGray' and bpc == 16:
            assert pim.mode == 'I;16'
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
    colorspaces=st.sampled_from(['DeviceGray', 'DeviceRGB', 'DeviceCMYK']),
    palette=None,
):
    bpc = draw(bpcs)
    width = draw(widths)
    height = draw(heights)
    colorspace = Name(f'/{draw(colorspaces)}')
    hival = draw(st.integers(min_value=0, max_value=(2**bpc) - 1))

    imbytes = draw(imagelike_data(width, height, bpc, (0, hival)))

    channels = (
        1
        if colorspace == Name.DeviceGray
        else (
            3
            if colorspace == Name.DeviceRGB
            else 4
            if colorspace == Name.DeviceCMYK
            else 0
        )
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
    pim = PdfImage(next(iter(pdf.pages[0].get_images(recursive=False).values())))

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
@settings(deadline=60000)
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

        assert not diff.getbbox(), (
            f"{diff.getpixel((0, 0))}, {im1.getpixel((0, 0))}, {im2.getpixel((0, 0))}"
        )


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


def test_rgb_jpeg_nondefault_colortransform_transcodes(congress):
    # A non-default /ColorTransform means the stored JPEG cannot be copied out as
    # a standalone .jpg (the codec parameters would be lost), but pikepdf still
    # decodes it via Pillow -- which honours the JPEG's own markers -- and
    # transcodes it to PNG rather than failing.
    xobj, _pdf = congress

    xobj.DecodeParms = Dictionary(
        ColorTransform=0  # Non-default for a 3-component (RGB) JPEG
    )
    pim = PdfImage(xobj)

    assert pim._extract_direct(stream=BytesIO()) is None
    im = pim.as_pil_image()
    assert im.mode == 'RGB'
    assert im.size == (pim.width, pim.height)

    bio = BytesIO()
    assert pim.extract_to(stream=bio) == '.png'


def test_cmyk_jpeg_nondefault_colortransform_transcodes(first_image_in):
    # A YCCK-style CMYK JPEG (ColorTransform 1) cannot be copied out directly, but
    # it transcodes via Pillow to a CMYK image saved as TIFF.
    xobj, _pdf = first_image_in('cmyk-jpeg.pdf')

    xobj.DecodeParms = Dictionary(
        ColorTransform=1  # Non-default for a 4-component (CMYK) JPEG
    )
    pim = PdfImage(xobj)

    assert pim._extract_direct(stream=BytesIO()) is None
    im = pim.as_pil_image()
    assert im.mode == 'CMYK'
    assert im.size == (pim.width, pim.height)

    bio = BytesIO()
    assert pim.extract_to(stream=bio) == '.tiff'


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


def test_stacked_compression_no_orphaned_objects(first_image_in):
    # Regression test for issue #691
    xobj, pdf = first_image_in('pike-flate-jp2.pdf')

    initial_count = len(pdf.objects)
    pim = PdfImage(xobj)

    for _ in range(3):
        pim.as_pil_image().close()

    assert len(pdf.objects) == initial_count


def test_ascii85_flate_dct_extracts_jpg(congress):
    # Any number of generalized/specialized filters wrapping a single terminal
    # codec must be peeled away, leaving the JPEG to extract directly.
    xobj, _pdf = congress
    raw_jpeg = xobj.read_raw_bytes()
    import base64

    a85 = base64.a85encode(zlib.compress(raw_jpeg)) + b'~>'
    xobj.write(
        a85, filter=Array([Name.ASCII85Decode, Name.FlateDecode, Name.DCTDecode])
    )

    pim = PdfImage(xobj)
    data, filters = pim._remove_simple_filters()
    assert filters == ['/DCTDecode']
    assert data == raw_jpeg
    bio = BytesIO()
    assert pim.extract_to(stream=bio) == '.jpg'


def test_flate_wrapped_ccitt_extract(sandwich):
    # A simple filter wrapping a CCITT codec must peel correctly *and* the CCITT
    # header must be built from the CCITT filter's own /DecodeParms, not from the
    # (now leading) simple filter's parms.
    xobj, _pdf = sandwich
    baseline = PdfImage(xobj).as_pil_image().convert('L').tobytes()

    raw_ccitt = xobj.read_raw_bytes()
    ccitt_parms = xobj.DecodeParms
    xobj.write(
        zlib.compress(raw_ccitt),
        filter=Array([Name.FlateDecode, Name.CCITTFaxDecode]),
        decode_parms=Array([Dictionary(), ccitt_parms]),
    )

    pim = PdfImage(xobj)
    assert pim.filters == ['/FlateDecode', '/CCITTFaxDecode']
    data, filters = pim._remove_simple_filters()
    assert filters == ['/CCITTFaxDecode']
    assert data == raw_ccitt
    assert PdfImage(xobj).as_pil_image().convert('L').tobytes() == baseline


def test_two_terminal_codecs_unsupported(congress):
    # Two terminal image codecs in one chain cannot be decoded by any reader;
    # pikepdf rejects this with a clear, consistent exception type.
    xobj, _pdf = congress
    xobj.Filter = Array([Name.DCTDecode, Name.CCITTFaxDecode])
    pim = PdfImage(xobj)
    with pytest.raises(UnsupportedImageTypeError):
        pim._remove_simple_filters()


@pytest.mark.parametrize(
    'blackis1,decode,expected',
    [
        (None, None, 255),
        (False, None, 255),
        (True, None, 0),
        (None, [0, 1], 255),
        (None, [1, 0], 0),
        (False, [0, 1], 255),
        (False, [1, 0], 0),
        (True, [0, 1], 0),
        (True, [1, 0], 255),
    ],
)
def test_ccitt_photometry(sandwich, blackis1, decode, expected):
    xobj, _pdf = sandwich

    if blackis1 is not None:
        xobj.DecodeParms.BlackIs1 = blackis1
    if decode is not None:
        xobj.Decode = decode

    pim = PdfImage(xobj)
    im = pim.as_pil_image()
    im = im.convert('L')
    assert im.getpixel((0, 0)) == expected, f"Expected background pixel = {expected}"


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
    # rle.pdf carries an /SMask, so the extracted image now has an alpha channel.
    im = pim.as_pil_image()
    assert im.mode == 'RGBA'
    assert im.getpixel((5, 5)) == (255, 128, 0, 255)
    # Without mask application the colour samples are unchanged and opaque RGB.
    opaque = pim.as_pil_image(apply_mask=False)
    assert opaque.mode == 'RGB'
    assert opaque.getpixel((5, 5)) == (255, 128, 0)


def _make_gray_xobject(pdf, *, width, height, bpc, data, decode=None):
    """Build an uncompressed DeviceGray image XObject for Decode testing."""
    obj = Stream(pdf, data)
    obj.Type = Name.XObject
    obj.Subtype = Name.Image
    obj.Width = width
    obj.Height = height
    obj.BitsPerComponent = bpc
    obj.ColorSpace = Name.DeviceGray
    if decode is not None:
        obj.Decode = Array(decode)
    return obj


def test_decode_array_inverts_1bit_gray():
    # Issue #650: 1-bit DeviceGray FlateDecode image with /Decode = [1, 0]
    # must be extracted inverted (sample 0 -> white, sample 1 -> black).
    pdf = Pdf.new()
    data = bytes([0b10101010])  # 8 pixels: 1,0,1,0,1,0,1,0
    normal = PdfImage(_make_gray_xobject(pdf, width=8, height=1, bpc=1, data=data))
    inverted = PdfImage(
        _make_gray_xobject(pdf, width=8, height=1, bpc=1, data=data, decode=[1, 0])
    )

    normal_px = list(normal.as_pil_image().convert('L').tobytes())
    inverted_px = list(inverted.as_pil_image().convert('L').tobytes())

    assert normal_px == [255, 0, 255, 0, 255, 0, 255, 0]
    assert inverted_px == [0, 255, 0, 255, 0, 255, 0, 255]


def test_decode_array_lut_8bit_gray():
    # 8-bit DeviceGray with /Decode = [1, 0] exercises the linear LUT path
    # (output = 255 - input).
    pdf = Pdf.new()
    data = bytes([0, 64, 128, 255])
    pim = PdfImage(
        _make_gray_xobject(pdf, width=4, height=1, bpc=8, data=data, decode=[1, 0])
    )
    assert list(pim.as_pil_image().tobytes()) == [255, 191, 127, 0]


def test_decode_array_lut_partial_range():
    # A non-reversing /Decode maps samples into a sub-range of [0, 1]:
    # output = round((dmin + (p/255)*(dmax-dmin)) * 255).
    pdf = Pdf.new()
    data = bytes([0, 255])
    pim = PdfImage(
        _make_gray_xobject(
            pdf, width=2, height=1, bpc=8, data=data, decode=[0.25, 0.75]
        )
    )
    # p=0 -> round(0.25*255)=64 ; p=255 -> round(0.75*255)=191
    assert list(pim.as_pil_image().tobytes()) == [64, 191]


def test_decode_array_rgb_invert():
    # Per-band LUT on a 3-band image.
    pdf = Pdf.new()
    obj = Stream(pdf, bytes([10, 20, 30, 200, 100, 50]))  # two RGB pixels
    obj.Type = Name.XObject
    obj.Subtype = Name.Image
    obj.Width = 2
    obj.Height = 1
    obj.BitsPerComponent = 8
    obj.ColorSpace = Name.DeviceRGB
    obj.Decode = Array([1, 0, 1, 0, 1, 0])
    px = list(PdfImage(obj).as_pil_image().tobytes())
    assert px == [245, 235, 225, 55, 155, 205]  # 255 - each component


def test_decode_array_skipped_for_indexed(trivial):
    # /Decode on an Indexed image remaps palette indices, not colors; the
    # value-LUT path must leave such images untouched (no corruption/crash).
    xobj, _pdf = trivial
    baseline = list(PdfImage(xobj).as_pil_image().convert('RGB').tobytes())
    xobj.Decode = Array([0, 1])  # identity for this 1-bit palette: no warning
    after = list(PdfImage(xobj).as_pil_image().convert('RGB').tobytes())
    assert after == baseline


def test_decode_array_indexed_nonidentity_warns(trivial):
    # A non-identity /Decode on an Indexed image cannot be honored (it remaps
    # indices); warn rather than silently mislead.
    xobj, _pdf = trivial
    xobj.Decode = Array([1, 0])  # non-identity for a 1-bit palette ([0, 1])
    with pytest.warns(UserWarning, match="Indexed"):
        PdfImage(xobj).as_pil_image()


def test_decode_array_not_applied_when_disabled():
    # apply_decode_array=False returns the raw samples (forensic view), i.e. the
    # /Decode = [1, 0] inversion is NOT applied.
    pdf = Pdf.new()
    data = bytes([0b10101010])
    pim = PdfImage(
        _make_gray_xobject(pdf, width=8, height=1, bpc=1, data=data, decode=[1, 0])
    )
    applied = list(pim.as_pil_image(apply_decode_array=True).convert('L').tobytes())
    raw = list(pim.as_pil_image(apply_decode_array=False).convert('L').tobytes())
    assert applied == [0, 255, 0, 255, 0, 255, 0, 255]
    assert raw == [255, 0, 255, 0, 255, 0, 255, 0]


def test_decode_array_extract_to_respects_flag():
    pdf = Pdf.new()
    data = bytes([0b10101010])
    pim = PdfImage(
        _make_gray_xobject(pdf, width=8, height=1, bpc=1, data=data, decode=[1, 0])
    )
    for flag, expected in [(True, [0, 255]), (False, [255, 0])]:
        bio = BytesIO()
        ext = pim.extract_to(stream=bio, apply_decode_array=flag)
        assert ext == '.png'
        bio.seek(0)
        px = list(Image.open(bio).convert('L').tobytes())
        assert px[:2] == expected


def _make_dct_rgb_xobject(pdf, pil_img, decode=None):
    bio = BytesIO()
    pil_img.save(bio, format='JPEG', quality=95)
    obj = Stream(pdf, bio.getvalue())
    obj.Type = Name.XObject
    obj.Subtype = Name.Image
    obj.Width, obj.Height = pil_img.size
    obj.BitsPerComponent = 8
    obj.ColorSpace = Name.DeviceRGB
    obj.Filter = Name.DCTDecode
    if decode is not None:
        obj.Decode = Array(decode)
    return obj


def _approx(actual, expected, tol=12):
    return all(abs(a - e) <= tol for a, e in zip(actual, expected))


def test_decode_array_not_applied_to_dct():
    # /Decode is deferred to the JPEG codec (which carries its own color
    # semantics, e.g. the Adobe APP14 inverted-CMYK marker). pikepdf must not
    # re-apply it: extract_to stays a direct .jpg and the pixels are not
    # double-inverted, regardless of the flag.
    pdf = Pdf.new()
    src = Image.new('RGB', (8, 8), (200, 50, 100))
    pim = PdfImage(_make_dct_rgb_xobject(pdf, src, decode=[1, 0, 1, 0, 1, 0]))

    assert _approx(pim.as_pil_image().getpixel((4, 4)), (200, 50, 100))

    for flag in (True, False):
        bio = BytesIO()
        assert pim.extract_to(stream=bio, apply_decode_array=flag) == '.jpg'
        bio.seek(0)
        assert _approx(Image.open(bio).convert('RGB').getpixel((4, 4)), (200, 50, 100))


def test_decode_array_ccitt_respects_flag(sandwich):
    # CCITT honors /Decode via the TIFF photometry tag; disabling the flag must
    # produce the raw (non-inverted) photometry.
    xobj, _pdf = sandwich
    xobj.Decode = Array([1, 0])
    pim = PdfImage(xobj)
    applied = pim.as_pil_image(apply_decode_array=True).convert('L').getpixel((0, 0))
    raw = pim.as_pil_image(apply_decode_array=False).convert('L').getpixel((0, 0))
    assert applied == 0
    assert raw == 255


def test_decode_array_ccitt_extract_to_bakes_decode(sandwich):
    # extract_to keeps the efficient direct CCITT->TIFF path while honoring
    # /Decode by baking it into the TIFF photometry tag. The flag controls
    # whether that inversion is baked in.
    xobj, _pdf = sandwich
    xobj.Decode = Array([1, 0])
    pim = PdfImage(xobj)

    results = {}
    for flag in (True, False):
        bio = BytesIO()
        assert pim.extract_to(stream=bio, apply_decode_array=flag) == '.tif'
        bio.seek(0)
        results[flag] = Image.open(bio).convert('L').getpixel((0, 0))
    assert results[True] == 0  # /Decode [1, 0] inverts the background to black
    assert results[False] == 255  # raw photometry leaves it white


@pytest.mark.parametrize('bpc,decode', [(8, None), (8, [0, 1]), (1, [0, 1])])
def test_decode_array_identity_no_inversion(bpc, decode):
    # No /Decode and the identity /Decode must both be perfect no-ops: the
    # extracted samples must equal the stored samples (guard against accidental
    # inversion creeping into the default path).
    pdf = Pdf.new()
    if bpc == 8:
        data = bytes([10, 200])
        width = 2
        expected = [10, 200]
    else:
        data = bytes([0b10000000])  # pixels: 1, 0
        width = 2
        expected = [255, 0]
    pim = PdfImage(
        _make_gray_xobject(
            pdf, width=width, height=1, bpc=bpc, data=data, decode=decode
        )
    )
    assert list(pim.as_pil_image().convert('L').tobytes())[:2] == expected


def test_decode_array_1bit_nonreversal_lut():
    # A 1-bit image with a non-reversal, non-identity /Decode cannot stay in
    # mode '1'; it is promoted to 'L' and mapped through the linear LUT.
    pdf = Pdf.new()
    data = bytes([0b10000000])  # pixels: 1, 0
    pim = PdfImage(
        _make_gray_xobject(
            pdf, width=2, height=1, bpc=1, data=data, decode=[0.25, 0.75]
        )
    )
    im = pim.as_pil_image()
    assert im.mode == 'L'
    # sample 1 -> 0.75 -> 191 ; sample 0 -> 0.25 -> 64
    assert list(im.tobytes()) == [191, 64]


def test_decode_array_length_mismatch_ignored():
    # A /Decode whose length disagrees with the number of bands is malformed;
    # pikepdf refuses to guess and leaves the samples untouched (no inversion).
    pdf = Pdf.new()
    data = bytes([10, 200])
    pim = PdfImage(
        _make_gray_xobject(
            pdf, width=2, height=1, bpc=8, data=data, decode=[1, 0, 1, 0, 1, 0]
        )
    )
    assert list(pim.as_pil_image().convert('L').tobytes()) == [10, 200]


def _make_iccbased_xobject(pdf, *, n, decode=None):
    """Build a minimal ICCBased image XObject with an N-channel profile stream."""
    icc_stream = pdf.make_stream(b'\x00' * 16)
    icc_stream.N = n
    imobj = Stream(
        pdf,
        b'\x00' * n,
        BitsPerComponent=8,
        ColorSpace=Array([Name.ICCBased, icc_stream]),
        Width=1,
        Height=1,
        Type=Name.XObject,
        Subtype=Name.Image,
    )
    if decode is not None:
        imobj.Decode = Array(decode)
    return imobj


def test_indexed_default_decode_array():
    # The default /Decode for an Indexed colour space maps stored samples across
    # the index range [0, 2**bpc - 1], not across the base colour space's range.
    pdf = Pdf.new()
    palette = bytes(range(6))  # two RGB palette entries
    imobj = Stream(
        pdf,
        b'\x00\x01',
        BitsPerComponent=8,
        ColorSpace=Array([Name.Indexed, Name.DeviceRGB, 1, palette]),
        Width=2,
        Height=1,
        Type=Name.XObject,
        Subtype=Name.Image,
    )
    pim = PdfImage(imobj)
    assert pim.indexed
    assert pim._decode_array == (0.0, 255.0)


def test_iccbased_cmyk_default_decode_array():
    # A 4-channel (CMYK) ICCBased image has an 8-element identity default /Decode.
    pdf = Pdf.new()
    pim = PdfImage(_make_iccbased_xobject(pdf, n=4))
    assert pim._decode_array == (0.0, 1.0, 0.0, 1.0, 0.0, 1.0, 0.0, 1.0)


def test_iccbased_cmyk_explicit_decode_array():
    # An explicit 8-element /Decode on a CMYK ICCBased image is honoured verbatim.
    pdf = Pdf.new()
    pim = PdfImage(_make_iccbased_xobject(pdf, n=4, decode=[1, 0, 1, 0, 1, 0, 1, 0]))
    assert pim._decode_array == (1.0, 0.0, 1.0, 0.0, 1.0, 0.0, 1.0, 0.0)


@pytest.mark.skipif(
    not PIL_features.check_codec('jpg_2000'), reason='no JPEG2000 codec'
)
def test_decode_array_not_applied_to_jpx(first_image_in):
    # As with DCT, /Decode is deferred to the JPEG 2000 codec: adding a
    # reversing /Decode must not change the decoded pixels, and extract_to keeps
    # the direct .jp2 output for both flag values.
    xobj, _pdf = first_image_in('pike-jp2.pdf')
    baseline = PdfImage(xobj).as_pil_image().convert('RGB').getpixel((0, 0))

    xobj.Decode = Array([1, 0, 1, 0, 1, 0])
    pim = PdfImage(xobj)
    assert pim.as_pil_image().convert('RGB').getpixel((0, 0)) == baseline
    for flag in (True, False):
        bio = BytesIO()
        assert pim.extract_to(stream=bio, apply_decode_array=flag) == '.jp2'


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

GRAY_RGB_PALETTE = b''.join(bytes([gray, gray, gray]) for gray in range(256))


@pytest.mark.parametrize(
    'base_factory, hival, bits, palette, expect_type, expect_mode',
    [
        # Use lambdas so pikepdf objects are constructed at test time, not at
        # module collection time (avoids nanobind shutdown leak warnings).
        (lambda: Name.DeviceGray, 4, 8, b'\x00\x40\x80\xff', 'L', 'P'),
        (lambda: Name.DeviceCMYK, 4, 8, CMYK_PALETTE, 'CMYK', 'P'),
        (lambda: Name.DeviceGray, 4, 4, b'\x04\x08\x02\x0f', 'L', 'P'),
        (
            lambda: Array([Name.CalRGB, Dictionary(WhitePoint=Array([1.0, 1.0, 1.0]))]),
            255,
            8,
            GRAY_RGB_PALETTE,
            'RGB',
            'P',
        ),
    ],
)
def test_palette_nonrgb(base_factory, hival, bits, palette, expect_type, expect_mode):
    base = base_factory()
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


def test_palette_1bit_cmyk():
    # A 1-bit /Indexed image over a /DeviceCMYK base must apply its palette.
    # 8x1 pixels alternating index 0,1 packed MSB-first (0b01010101) into one
    # byte, with a two-entry CMYK palette.
    pdf = pikepdf.new()
    palette = CMYK_RED + CMYK_GREEN
    imobj = Stream(
        pdf,
        bytes([0b01010101]),
        BitsPerComponent=1,
        ColorSpace=Array([Name.Indexed, Name.DeviceCMYK, 1, palette]),
        Width=8,
        Height=1,
        Type=Name.XObject,
        Subtype=Name.Image,
    )
    pim = pikepdf.PdfImage(imobj)
    assert pim.palette == ('CMYK', palette)
    im = pim.as_pil_image()
    assert im.mode == 'CMYK'
    assert im.getpixel((0, 0)) == tuple(CMYK_RED)
    assert im.getpixel((1, 0)) == tuple(CMYK_GREEN)


def test_palette_1bit_rgb_single_color():
    # A 1-bit /Indexed /DeviceRGB image with hival 0 has a single-entry (3-byte)
    # palette; every pixel is index 0 and must render as that colour.
    pdf = pikepdf.new()
    palette = bytes([255, 128, 0])
    imobj = Stream(
        pdf,
        bytes([0x00]),  # 8x1 pixels, all index 0
        BitsPerComponent=1,
        ColorSpace=Array([Name.Indexed, Name.DeviceRGB, 0, palette]),
        Width=8,
        Height=1,
        Type=Name.XObject,
        Subtype=Name.Image,
    )
    pim = pikepdf.PdfImage(imobj)
    assert pim.palette == ('RGB', palette)
    im = pim.as_pil_image().convert('RGB')
    assert im.getpixel((0, 0)) == (255, 128, 0)
    assert im.getpixel((7, 0)) == (255, 128, 0)


def test_fix_1bit_palette_rejects_unsupported_base():
    # An /Indexed base that is not RGB/L/CMYK (e.g. /DeviceN or /Separation)
    # must fail loudly rather than silently return an unpalettized image, to
    # match the 2/4/8-bit path (image_from_buffer_and_palette).
    from PIL import Image

    im = Image.frombytes('1', (8, 1), bytes([0b01010101]))
    with pytest.raises(NotImplementedError, match='palette with DeviceN'):
        fix_1bit_palette_image(im, 'DeviceN', b'\x00' * 8)


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
        colorspaces=st.just('DeviceGray'),
        widths=st.integers(1, 7),
        heights=st.integers(1, 7),
    )
)
@settings(deadline=None)
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

    imdata = (
        im.get_flattened_data() if hasattr(im, 'get_flattened_data') else im.getdata()
    )
    for n, pixel in enumerate(imdata):
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
    # 16-bit RGB/CMYK is losslessly impossible in Pillow, so pikepdf reduces it
    # to 8-bit and warns; that warning is expected behavior, so trap it here.
    expect_downconvert = bpc == 16 and colorspace in (
        Name.DeviceRGB,
        Name.DeviceCMYK,
    )
    warn_ctx = (
        pytest.warns(UserWarning, match='reduced to 8-bit')
        if expect_downconvert
        else nullcontext()
    )
    try:
        with warn_ctx:
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

    # pdfimages reduces 16-bit images to 8 bits, so a pixel-exact cross-check
    # against it is not meaningful; pikepdf's own output was validated above.
    if bpc == 16:
        return

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


def test_repr_when_mode_not_impl():
    pdf = Pdf.new()
    pim = PdfImage(
        Stream(
            pdf,
            b'',
            BitsPerComponent=1,
            ColorSpace=Name.InvalidColorSpace,
            Width=1,
            Height=1,
            Type=Name.XObject,
            Subtype=Name.Image,
        )
    )
    assert repr(pim).startswith('<pikepdf.PdfImage image mode=? size=1x1')
    with pytest.raises(NotImplementedError):
        pim.mode


# --- Decompression bomb protection (issue #733) ---------------------------


@pytest.fixture
def restore_pixel_limits():
    """Save/restore both pikepdf's and Pillow's pixel limits around a test."""
    import pikepdf.models.image as imgmod

    saved_pikepdf = imgmod._max_image_pixels
    saved_pil = Image.MAX_IMAGE_PIXELS
    try:
        yield imgmod
    finally:
        imgmod._max_image_pixels = saved_pikepdf
        Image.MAX_IMAGE_PIXELS = saved_pil


def _image_stream(pdf, *, bpc, colorspace, width, height, imbytes):
    return Stream(
        pdf,
        imbytes,
        BitsPerComponent=bpc,
        ColorSpace=colorspace,
        Width=width,
        Height=height,
        Type=Name.XObject,
        Subtype=Name.Image,
    )


def test_max_image_pixels_defaults_to_floor(restore_pixel_limits):
    imgmod = restore_pixel_limits
    imgmod._max_image_pixels = imgmod._UNSET  # simulate never-set
    assert PdfImage.MAX_IMAGE_PIXELS == max(500_000_000, Image.MAX_IMAGE_PIXELS)


def test_max_image_pixels_decouples_from_pil(restore_pixel_limits):
    PdfImage.MAX_IMAGE_PIXELS = 123
    assert PdfImage.MAX_IMAGE_PIXELS == 123
    # Once set, pikepdf's limit is independent of Pillow's.
    Image.MAX_IMAGE_PIXELS = 4_000_000_000
    assert PdfImage.MAX_IMAGE_PIXELS == 123


def test_max_image_pixels_none_disables_check(restore_pixel_limits):
    PdfImage.MAX_IMAGE_PIXELS = None
    pdf = pikepdf.new()
    img = PdfImage(
        _image_stream(
            pdf,
            bpc=4,
            colorspace=Name.DeviceGray,
            width=200000,
            height=200000,
            imbytes=b'\x00',
        )
    )
    # Setting None disables the guard; check returns without raising (and without
    # attempting the multi-gigabyte allocation).
    assert img._check_pixels(200000, 200000) is None


def test_decompression_bomb_exception_subclasses_pil():
    assert issubclass(pikepdf.DecompressionBombError, Image.DecompressionBombError)
    assert issubclass(pikepdf.DecompressionBombWarning, Image.DecompressionBombWarning)


def test_issue_733_4bit_bomb_raises(restore_pixel_limits):
    pdf = pikepdf.new()
    img = PdfImage(
        _image_stream(
            pdf,
            bpc=4,
            colorspace=Name.DeviceGray,
            width=200000,
            height=200000,
            imbytes=b'\x00',
        )
    )
    with pytest.raises(pikepdf.DecompressionBombError):
        img.as_pil_image()


def test_1bit_bomb_raises(restore_pixel_limits):
    pdf = pikepdf.new()
    img = PdfImage(
        _image_stream(
            pdf,
            bpc=1,
            colorspace=Name.DeviceGray,
            width=200000,
            height=200000,
            imbytes=b'\x00',
        )
    )
    with pytest.raises(pikepdf.DecompressionBombError):
        img.as_pil_image()


def test_8bit_rgb_bomb_raises(restore_pixel_limits):
    pdf = pikepdf.new()
    img = PdfImage(
        _image_stream(
            pdf,
            bpc=8,
            colorspace=Name.DeviceRGB,
            width=200000,
            height=200000,
            imbytes=b'\x00\x00\x00',
        )
    )
    with pytest.raises(pikepdf.DecompressionBombError):
        img.as_pil_image()


def test_warning_band_warns_not_raises(restore_pixel_limits):
    PdfImage.MAX_IMAGE_PIXELS = 2  # 2x2 image = 4 px: > limit, <= 2*limit
    pdf = pikepdf.new()
    img = PdfImage(
        _image_stream(
            pdf,
            bpc=8,
            colorspace=Name.DeviceGray,
            width=2,
            height=2,
            imbytes=b'\x00\x01\x02\x03',
        )
    )
    with pytest.warns(pikepdf.DecompressionBombWarning):
        im = img.as_pil_image()
    assert im.size == (2, 2)


def test_direct_path_honors_pikepdf_limit(congress, restore_pixel_limits):
    # congress.pdf is a DCTDecode (JPEG) image extracted via the direct path,
    # which Pillow decodes. A very low pikepdf limit must govern that path too.
    PdfImage.MAX_IMAGE_PIXELS = 10
    xobj, _ = congress
    with pytest.raises(pikepdf.DecompressionBombError):
        PdfImage(xobj).as_pil_image()


# --- Sub-byte unpacking of truncated image data ---------------------------


@pytest.mark.parametrize('bits', [2, 4])
def test_unpack_subbyte_rejects_truncated_data(bits):
    # The unpack buffer is sized from the declared /Width and /Height, so the
    # declared size must be backed by enough data before anything is allocated.
    with pytest.raises(ImageDecompressionError, match='requires'):
        unpack_subbyte_pixels(b'\x00', (200000, 200000), bits)


@pytest.mark.parametrize('bits', [2, 4])
@pytest.mark.parametrize('width,height', [(1, 1), (5, 3), (16, 16)])
def test_unpack_subbyte_accepts_exact_data(bits, width, height):
    packed_row_bytes = ceil(width * bits / 8)
    buffer, stride = unpack_subbyte_pixels(
        b'\x00' * (packed_row_bytes * height), (width, height), bits
    )
    assert stride == _next_multiple(width, 8 // bits)
    # One byte per pixel, each row padded out to stride.
    assert len(buffer) == stride * height


@pytest.mark.parametrize('size', [(0, 1), (1, 0), (-1, 1)])
def test_unpack_subbyte_rejects_nonpositive_size(size):
    with pytest.raises(ImageDecompressionError, match='invalid dimensions'):
        unpack_subbyte_pixels(b'\x00', size, 4)


def test_truncated_4bit_image_raises_under_pixel_limit(restore_pixel_limits):
    # 64x64 is only 4096 pixels, far below MAX_IMAGE_PIXELS, so the bomb check
    # passes -- but one byte of data cannot fill it.
    pdf = pikepdf.new()
    img = PdfImage(
        _image_stream(
            pdf,
            bpc=4,
            colorspace=Name.DeviceGray,
            width=64,
            height=64,
            imbytes=b'\x00',
        )
    )
    with pytest.raises(ImageDecompressionError):
        img.as_pil_image()


def test_truncated_4bit_image_raises_with_pixel_limit_disabled(restore_pixel_limits):
    # With the bomb guard disabled, the length check is the only thing standing
    # between a 796-byte PDF and an 80 GB allocation.
    PdfImage.MAX_IMAGE_PIXELS = None
    pdf = pikepdf.new()
    img = PdfImage(
        _image_stream(
            pdf,
            bpc=4,
            colorspace=Name.DeviceGray,
            width=200000,
            height=200000,
            imbytes=b'\x00',
        )
    )
    with pytest.raises(ImageDecompressionError):
        img.as_pil_image()


# --- Gap A: CalRGB / CalGray / CalCMYK colour spaces -----------------------

# A near-sRGB calibrated RGB space (D65 white, sRGB primaries, gamma 2.2).
D65_WHITEPOINT = [0.9505, 1.0, 1.089]
SRGB_GAMMA = [2.2, 2.2, 2.2]
# Matrix is column-major: [Xr Yr Zr  Xg Yg Zg  Xb Yb Zb]
SRGB_MATRIX = [
    0.4124, 0.2126, 0.0193,
    0.3576, 0.7152, 0.1192,
    0.1805, 0.0722, 0.9505,
]  # fmt: skip


def _cal_image(colorspace_array, bpc, width, height, imbytes):
    pdf = pikepdf.new()
    imobj = Stream(
        pdf,
        imbytes,
        BitsPerComponent=bpc,
        ColorSpace=colorspace_array,
        Width=width,
        Height=height,
        Type=Name.XObject,
        Subtype=Name.Image,
    )
    pim = PdfImage(imobj)
    pim._set_pdf_source(pdf)  # keep the owning Pdf alive
    return pim


def test_calgray_extract():
    cal = Array([Name.CalGray, Dictionary(WhitePoint=D65_WHITEPOINT, Gamma=2.2)])
    pim = _cal_image(cal, bpc=8, width=4, height=4, imbytes=bytes(range(16)))
    assert pim.colorspace == '/CalGray'
    assert pim.mode == 'L'
    im = pim.as_pil_image()
    assert im.mode == 'L'
    assert im.size == (4, 4)


def test_calgray_1bit_mode():
    cal = Array([Name.CalGray, Dictionary(WhitePoint=D65_WHITEPOINT)])
    pim = _cal_image(cal, bpc=1, width=8, height=2, imbytes=b'\xaa\x55')
    assert pim.mode == '1'
    assert pim.as_pil_image().mode == '1'


def test_calrgb_extract():
    cal = Array(
        [
            Name.CalRGB,
            Dictionary(WhitePoint=D65_WHITEPOINT, Gamma=SRGB_GAMMA, Matrix=SRGB_MATRIX),
        ]
    )
    pim = _cal_image(cal, bpc=8, width=2, height=2, imbytes=bytes(range(12)))
    assert pim.colorspace == '/CalRGB'
    assert pim.mode == 'RGB'
    im = pim.as_pil_image()
    assert im.mode == 'RGB'
    assert im.size == (2, 2)


def test_calcmyk_extract():
    # CalCMYK is a deprecated alias for DeviceCMYK; no profile is synthesized.
    cal = Array([Name.CalCMYK, Dictionary(WhitePoint=D65_WHITEPOINT)])
    pim = _cal_image(cal, bpc=8, width=2, height=2, imbytes=bytes(range(16)))
    assert pim.colorspace == '/CalCMYK'
    assert pim.mode == 'CMYK'
    im = pim.as_pil_image()
    assert im.mode == 'CMYK'
    assert 'icc_profile' not in im.info


def test_calcmyk_default_decode_array():
    cal = Array([Name.CalCMYK, Dictionary(WhitePoint=D65_WHITEPOINT)])
    pim = _cal_image(cal, bpc=8, width=2, height=2, imbytes=bytes(range(16)))
    assert pim._decode_array == (0.0, 1.0, 0.0, 1.0, 0.0, 1.0, 0.0, 1.0)


def test_calrgb_attaches_icc_profile():
    cal = Array(
        [
            Name.CalRGB,
            Dictionary(WhitePoint=D65_WHITEPOINT, Gamma=SRGB_GAMMA, Matrix=SRGB_MATRIX),
        ]
    )
    pim = _cal_image(cal, bpc=8, width=2, height=2, imbytes=bytes(range(12)))
    im = pim.as_pil_image()
    assert 'icc_profile' in im.info
    prof = ImageCms.ImageCmsProfile(BytesIO(im.info['icc_profile']))
    assert prof.profile.xcolor_space.strip() == 'RGB'


def test_calgray_attaches_icc_profile():
    cal = Array([Name.CalGray, Dictionary(WhitePoint=D65_WHITEPOINT, Gamma=2.2)])
    pim = _cal_image(cal, bpc=8, width=4, height=4, imbytes=bytes(range(16)))
    im = pim.as_pil_image()
    assert 'icc_profile' in im.info
    prof = ImageCms.ImageCmsProfile(BytesIO(im.info['icc_profile']))
    assert prof.profile.xcolor_space.strip() == 'GRAY'


def test_calrgb_icc_roundtrip_to_srgb():
    # Our CalRGB profile uses sRGB primaries / D65 white / gamma 2.2, so
    # converting a neutral mid-gray through it to sRGB should stay near 128.
    cal = Array(
        [
            Name.CalRGB,
            Dictionary(WhitePoint=D65_WHITEPOINT, Gamma=SRGB_GAMMA, Matrix=SRGB_MATRIX),
        ]
    )
    pim = _cal_image(cal, bpc=8, width=1, height=1, imbytes=bytes([128, 128, 128]))
    im = pim.as_pil_image()
    src = ImageCms.ImageCmsProfile(BytesIO(im.info['icc_profile']))
    srgb = ImageCms.createProfile('sRGB')
    converted = ImageCms.profileToProfile(im, src, srgb, outputMode='RGB')
    r, g, b = converted.getpixel((0, 0))
    assert abs(r - 128) <= 12
    assert abs(g - 128) <= 12
    assert abs(b - 128) <= 12


def test_cal_missing_whitepoint_falls_back():
    # Malformed CalRGB without the required WhitePoint: extraction still works
    # as a plain device space, but no ICC profile is synthesized.
    cal = Array([Name.CalRGB, Dictionary(Gamma=SRGB_GAMMA, Matrix=SRGB_MATRIX)])
    pim = _cal_image(cal, bpc=8, width=2, height=2, imbytes=bytes(range(12)))
    im = pim.as_pil_image()
    assert im.mode == 'RGB'
    assert 'icc_profile' not in im.info


# --- Gap B: 16-bit BitsPerComponent ----------------------------------------


def _bpc16_image(colorspace, width, height, imbytes, **kwargs):
    pdf = pikepdf.new()
    imobj = _image_stream(
        pdf, bpc=16, colorspace=colorspace, width=width, height=height, imbytes=imbytes
    )
    for k, v in kwargs.items():
        imobj[Name(f'/{k}')] = v
    pim = PdfImage(imobj)
    pim._set_pdf_source(pdf)
    return pim


def test_16bit_gray_extract():
    # 2x2 big-endian 16-bit grayscale: 0, 256, 32768, 65535
    imbytes = b'\x00\x00\x01\x00\x80\x00\xff\xff'
    pim = _bpc16_image(Name.DeviceGray, 2, 2, imbytes)
    assert pim.bits_per_component == 16
    assert pim.mode == 'I;16'
    im = pim.as_pil_image()
    assert im.mode == 'I;16'
    assert im.getpixel((0, 0)) == 0
    assert im.getpixel((1, 0)) == 256
    assert im.getpixel((0, 1)) == 32768
    assert im.getpixel((1, 1)) == 65535


def test_16bit_gray_png_roundtrip():
    imbytes = b'\x00\x00\x01\x00\x80\x00\xff\xff'
    pim = _bpc16_image(Name.DeviceGray, 2, 2, imbytes)
    bio = BytesIO()
    ext = pim.extract_to(stream=bio)
    assert ext == '.png'
    bio.seek(0)
    im = Image.open(bio)
    assert im.mode == 'I;16'
    assert im.getpixel((1, 1)) == 65535


def test_16bit_gray_decode_reversal():
    imbytes = b'\x00\x00\x80\x00\xff\xff\x01\x00'
    pim = _bpc16_image(Name.DeviceGray, 2, 2, imbytes, Decode=[1.0, 0.0])
    im = pim.as_pil_image()
    assert im.getpixel((0, 0)) == 65535
    assert im.getpixel((1, 1)) == 65535 - 256


def test_16bit_gray_decode_arbitrary_warns():
    imbytes = b'\x00\x00\x80\x00\xff\xff\x01\x00'
    pim = _bpc16_image(Name.DeviceGray, 2, 2, imbytes, Decode=[0.0, 0.5])
    with pytest.warns(UserWarning, match='16-bit'):
        im = pim.as_pil_image()
    # arbitrary /Decode is not applied to 16-bit gray
    assert im.getpixel((0, 1)) == 65535


def test_16bit_rgb_downconvert_warns():
    # 1x1 16-bit RGB: R=0x1234 G=0x5678 B=0x9abc -> high bytes 0x12,0x56,0x9a
    imbytes = b'\x12\x34\x56\x78\x9a\xbc'
    pim = _bpc16_image(Name.DeviceRGB, 1, 1, imbytes)
    assert pim.mode == 'RGB'
    with pytest.warns(UserWarning, match='16-bit'):
        im = pim.as_pil_image()
    assert im.mode == 'RGB'
    assert im.getpixel((0, 0)) == (0x12, 0x56, 0x9A)


def test_16bit_cmyk_downconvert():
    imbytes = b'\x10\x00\x20\x00\x30\x00\x40\x00'
    pim = _bpc16_image(Name.DeviceCMYK, 1, 1, imbytes)
    assert pim.mode == 'CMYK'
    with pytest.warns(UserWarning, match='16-bit'):
        im = pim.as_pil_image()
    assert im.mode == 'CMYK'
    assert im.getpixel((0, 0)) == (0x10, 0x20, 0x30, 0x40)


# --- Gap C: /Lab colour space ----------------------------------------------


def _lab_image(width, height, imbytes, range_=None, bpc=8):
    pdf = pikepdf.new()
    d = Dictionary(WhitePoint=[0.9505, 1.0, 1.089])
    if range_ is not None:
        d[Name.Range] = range_
    imobj = _image_stream(
        pdf,
        bpc=bpc,
        colorspace=Array([Name.Lab, d]),
        width=width,
        height=height,
        imbytes=imbytes,
    )
    pim = PdfImage(imobj)
    pim._set_pdf_source(pdf)
    return pim


def test_lab_default_range_mode():
    pim = _lab_image(1, 1, b'\x80\x80\x80')
    assert pim.colorspace == '/Lab'
    assert pim.mode == 'LAB'


def test_lab_decode_array_default():
    pim = _lab_image(1, 1, b'\x80\x80\x80')
    assert pim._decode_array == (0.0, 100.0, -100.0, 100.0, -100.0, 100.0)


def test_lab_decode_array_with_range():
    pim = _lab_image(1, 1, b'\x80\x80\x80', range_=[-128, 127, -128, 127])
    assert pim._decode_array == (0.0, 100.0, -128.0, 127.0, -128.0, 127.0)


def test_lab_remap_zero_point():
    # Sample (128, 128, 128) ~ L=50, a=0, b=0 -> Pillow LAB neutral ~ (128,128,128)
    pim = _lab_image(1, 1, b'\x80\x80\x80')
    im = pim.as_pil_image()
    assert im.mode == 'LAB'
    L, a, b = im.getpixel((0, 0))
    assert abs(L - 128) <= 2
    assert abs(a - 128) <= 2
    assert abs(b - 128) <= 2


def test_lab_extract_to_tiff():
    pim = _lab_image(2, 2, b'\x80\x80\x80' * 4)
    bio = BytesIO()
    ext = pim.extract_to(stream=bio)
    assert ext == '.tiff'


def test_lab_indexed_rejected():
    pdf = pikepdf.new()
    lab = Array([Name.Lab, Dictionary(WhitePoint=[0.9505, 1.0, 1.089])])
    imobj = Stream(
        pdf,
        bytes(range(16)),
        BitsPerComponent=8,
        ColorSpace=Array([Name.Indexed, lab, 15, bytes(range(48))]),
        Width=4,
        Height=4,
        Type=Name.XObject,
        Subtype=Name.Image,
    )
    pim = PdfImage(imobj)
    with pytest.raises((NotImplementedError, UnsupportedImageTypeError)):
        pim.extract_to(stream=BytesIO())


# --- Gap D: SMask / Mask / colour-key transparency -------------------------


def _image_with_smask(
    base_cs,
    base_bytes,
    w,
    h,
    smask_bytes,
    smw=None,
    smh=None,
    smask_decode=None,
):
    pdf = pikepdf.new()
    smw = smw or w
    smh = smh or h
    smask = Stream(
        pdf,
        smask_bytes,
        BitsPerComponent=8,
        ColorSpace=Name.DeviceGray,
        Width=smw,
        Height=smh,
        Type=Name.XObject,
        Subtype=Name.Image,
    )
    if smask_decode is not None:
        smask.Decode = smask_decode
    imobj = Stream(
        pdf,
        base_bytes,
        BitsPerComponent=8,
        ColorSpace=base_cs,
        Width=w,
        Height=h,
        Type=Name.XObject,
        Subtype=Name.Image,
        SMask=smask,
    )
    pim = PdfImage(imobj)
    pim._set_pdf_source(pdf)
    return pim


def test_smask_produces_rgba():
    pim = _image_with_smask(
        Name.DeviceRGB, b'\xff\x00\x00' * 4, 2, 2, b'\x00\x55\xaa\xff'
    )
    im = pim.as_pil_image()
    assert im.mode == 'RGBA'
    assert im.getpixel((0, 0)) == (255, 0, 0, 0)
    assert im.getpixel((1, 0)) == (255, 0, 0, 0x55)
    assert im.getpixel((0, 1)) == (255, 0, 0, 0xAA)
    assert im.getpixel((1, 1)) == (255, 0, 0, 255)


def test_smask_gray_produces_la():
    pim = _image_with_smask(
        Name.DeviceGray, b'\x10\x20\x30\x40', 2, 2, b'\x00\xff\x00\xff'
    )
    im = pim.as_pil_image()
    assert im.mode == 'LA'
    assert im.getpixel((0, 0)) == (0x10, 0)
    assert im.getpixel((1, 0)) == (0x20, 255)


def test_smask_resampled():
    pim = _image_with_smask(
        Name.DeviceRGB, b'\x7f\x7f\x7f' * 16, 4, 4, b'\x00\xff\xff\x00', smw=2, smh=2
    )
    im = pim.as_pil_image()
    assert im.mode == 'RGBA'
    assert im.size == (4, 4)
    # Resampled alpha is not uniform.
    alphas = {im.getpixel((x, y))[3] for x in range(4) for y in range(4)}
    assert len(alphas) > 1


def test_smask_honors_its_own_decode():
    # SMask sample 0 with Decode [1 0] maps to alpha 255 (opaque).
    pim = _image_with_smask(
        Name.DeviceRGB, b'\x00\x00\xff', 1, 1, b'\x00', smask_decode=[1, 0]
    )
    im = pim.as_pil_image()
    assert im.getpixel((0, 0)) == (0, 0, 255, 255)


def test_apply_mask_false_returns_opaque():
    pim = _image_with_smask(
        Name.DeviceRGB, b'\xff\x00\x00' * 4, 2, 2, b'\x00\x55\xaa\xff'
    )
    im = pim.as_pil_image(apply_mask=False)
    assert im.mode == 'RGB'


def test_extract_to_alpha_is_png():
    pim = _image_with_smask(
        Name.DeviceRGB, b'\xff\x00\x00' * 4, 2, 2, b'\x00\x55\xaa\xff'
    )
    bio = BytesIO()
    ext = pim.extract_to(stream=bio)
    assert ext == '.png'
    bio.seek(0)
    assert Image.open(bio).mode == 'RGBA'


def test_cmyk_with_smask_converts_rgba():
    pim = _image_with_smask(
        Name.DeviceCMYK, b'\x00\x00\x00\x00' * 4, 2, 2, b'\x00\x55\xaa\xff'
    )
    with pytest.warns(UserWarning, match='alpha'):
        im = pim.as_pil_image()
    assert im.mode == 'RGBA'
    assert im.getpixel((0, 0))[3] == 0


def _stencil_mask_pim(mask_byte, mask_decode=None):
    pdf = pikepdf.new()
    mask = Stream(
        pdf,
        mask_byte,
        ImageMask=True,
        BitsPerComponent=1,
        Width=1,
        Height=1,
        Type=Name.XObject,
        Subtype=Name.Image,
    )
    if mask_decode is not None:
        mask.Decode = mask_decode
    imobj = Stream(
        pdf,
        b'\x00\x00\xff',
        BitsPerComponent=8,
        ColorSpace=Name.DeviceRGB,
        Width=1,
        Height=1,
        Type=Name.XObject,
        Subtype=Name.Image,
        Mask=mask,
    )
    pim = PdfImage(imobj)
    pim._set_pdf_source(pdf)
    return pim


def test_stencil_mask_polarity():
    # Stencil sample 0 (default Decode) paints -> opaque.
    opaque = _stencil_mask_pim(b'\x00').as_pil_image()
    assert opaque.getpixel((0, 0)) == (0, 0, 255, 255)
    # Stencil sample 1 masks out -> transparent.
    transparent = _stencil_mask_pim(b'\x80').as_pil_image()
    assert transparent.getpixel((0, 0))[3] == 0


def test_colorkey_mask_8bit():
    pdf = pikepdf.new()
    # 2x2 RGB: red, green, blue, white
    base = b'\xff\x00\x00\x00\xff\x00\x00\x00\xff\xff\xff\xff'
    imobj = Stream(
        pdf,
        base,
        BitsPerComponent=8,
        ColorSpace=Name.DeviceRGB,
        Width=2,
        Height=2,
        Type=Name.XObject,
        Subtype=Name.Image,
        Mask=Array([250, 255, 0, 0, 0, 0]),  # mask out pure-red pixels
    )
    pim = PdfImage(imobj)
    pim._set_pdf_source(pdf)
    im = pim.as_pil_image()
    assert im.mode == 'RGBA'
    assert im.getpixel((0, 0))[3] == 0  # red masked
    assert im.getpixel((1, 0))[3] == 255  # green kept
    assert im.getpixel((1, 1))[3] == 255  # white kept


def test_both_smask_and_mask_smask_wins():
    pdf = pikepdf.new()
    smask = Stream(
        pdf,
        b'\x80',
        BitsPerComponent=8,
        ColorSpace=Name.DeviceGray,
        Width=1,
        Height=1,
        Type=Name.XObject,
        Subtype=Name.Image,
    )
    mask = Stream(
        pdf,
        b'\x80',  # would be fully transparent if used
        ImageMask=True,
        BitsPerComponent=1,
        Width=1,
        Height=1,
        Type=Name.XObject,
        Subtype=Name.Image,
    )
    imobj = Stream(
        pdf,
        b'\x00\x00\xff',
        BitsPerComponent=8,
        ColorSpace=Name.DeviceRGB,
        Width=1,
        Height=1,
        Type=Name.XObject,
        Subtype=Name.Image,
        SMask=smask,
        Mask=mask,
    )
    pim = PdfImage(imobj)
    pim._set_pdf_source(pdf)
    im = pim.as_pil_image()
    # SMask (alpha 0x80) takes precedence over the explicit Mask.
    assert im.getpixel((0, 0)) == (0, 0, 255, 0x80)
