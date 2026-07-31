# SPDX-FileCopyrightText: 2022 James R. Barlow
# SPDX-License-Identifier: MPL-2.0

"""Producing a base image from a PDF image: filter analysis and extraction.

Two strategies live here:

* **Direct extraction** copies the compressed stream into a standalone image
  file (``.jpg``/``.jp2``/``.tif``) without decoding pixels, when the codec
  permits it (:func:`extract_direct`, :func:`extract_direct_jpx`).
* **Transcoding** decodes the stream to pixels and builds a Pillow image
  (:func:`extract_transcoded` and its ``_transcoded_*`` helpers).

Each function takes the image (``pim``) and reads its metadata through the
properties, so :class:`PdfJpxImage`'s overrides flow through. Pillow is imported
lazily so that ``import pikepdf`` does not import Pillow.
"""

from __future__ import annotations

import warnings
from io import BytesIO
from typing import TYPE_CHECKING, BinaryIO, cast

from pikepdf import jbig2
from pikepdf._core import Pdf, PdfError, StreamDecodeLevel
from pikepdf._exceptions import DependencyError
from pikepdf.models import _transcoding
from pikepdf.models._image_exceptions import (
    HifiPrintImageNotTranscodableError,
    ImageDecompressionError,
    InvalidPdfImageError,
    UnsupportedImageTypeError,
)
from pikepdf.models.image._bomb import _pillow_pixel_limit
from pikepdf.models.image._shared import (
    TERMINAL_FILTERS,
    RGBDecodeArray,
)
from pikepdf.objects import Array, Name

if TYPE_CHECKING:
    from PIL import Image

    from pikepdf.models.image._classes import PdfImage


def remove_simple_filters(pim: PdfImage):
    """Strip generalized/specialized filters, leaving the terminal codec.

    Returns ``(data, remaining_filters)``. Any number of simple
    (qpdf-decodable) filters wrapping a single terminal codec are peeled
    away; if there is no terminal codec, every filter is decoded. Two or
    more terminal codecs in one chain cannot be decoded by any reader.
    """
    indices = [n for n, filt in enumerate(pim.filters) if filt in TERMINAL_FILTERS]
    if len(indices) > 1:
        raise UnsupportedImageTypeError(
            f"Object {pim.obj.objgen} has two or more terminal image codecs "
            f"in one filter chain: {pim.filters}. Such a chain cannot be "
            "decoded, because each codec produces final image samples."
        )
    if len(indices) == 0:
        # No terminal codec, so every filter is simple - decode them all
        return pim.obj.read_bytes(StreamDecodeLevel.specialized), []

    n = indices[0]
    if n == 0:
        # The only filter is the terminal codec, so return it untouched
        return pim.obj.read_raw_bytes(), pim.filters

    # Put a copy in a temporary PDF so we don't permanently modify pim.
    # qpdf tolerates a /DecodeParms array that is absent or shorter than
    # /Filter (it treats the missing entries as null), so a plain slice is
    # safe; explicit empty <<>> entries, by contrast, make it unfilterable.
    with Pdf.new() as tmp_pdf:
        obj_copy = tmp_pdf.copy_foreign(pim.obj)
        obj_copy.Filter = Array([Name(str(filt)) for filt in pim.filters[:n]])
        obj_copy.DecodeParms = Array(pim.decode_parms[:n])
        return obj_copy.read_bytes(StreamDecodeLevel.specialized), pim.filters[n:]


def extract_direct(
    pim: PdfImage, *, stream: BinaryIO, apply_decode_array: bool = True
) -> str | None:
    """Attempt to extract the image directly to a usable image file.

    Returns the file extension and writes the file to *stream* if the image
    can be produced without transcoding (honoring *apply_decode_array*),
    otherwise returns None so the caller can transcode. CCITTFax can always
    honor /Decode by setting the TIFF photometry tag; DCT/JPX cannot
    represent a non-identity /Decode in a copied stream, so they decline
    when one must be applied.

    Args:
        pim: the image to extract
        stream: Writable file stream to write data to, e.g. an open file
        apply_decode_array: Whether the produced file should reflect the
            image's /Decode array.
    """

    def normal_dct_rgb() -> bool:
        # Normal DCTDecode RGB images have the default value of
        # /ColorTransform 1 and are actually in YUV. Such a file can be
        # saved as a standard JPEG. RGB JPEGs without YUV conversion can't
        # be saved as JPEGs, and are probably bugs. Some software in the
        # wild actually produces RGB JPEGs in PDFs (probably a bug).
        DEFAULT_CT_RGB = 1
        ct = DEFAULT_CT_RGB
        if pim.filter_decodeparms[0][1] is not None:
            ct = pim.filter_decodeparms[0][1].get('/ColorTransform', DEFAULT_CT_RGB)
        return pim.mode == 'RGB' and ct == DEFAULT_CT_RGB

    def normal_dct_cmyk() -> bool:
        # Normal DCTDecode CMYKs have /ColorTransform 0 and can be saved.
        # There is a YUVK colorspace but CMYK JPEGs don't generally use it
        DEFAULT_CT_CMYK = 0
        ct = DEFAULT_CT_CMYK
        if pim.filter_decodeparms[0][1] is not None:
            ct = pim.filter_decodeparms[0][1].get('/ColorTransform', DEFAULT_CT_CMYK)
        return pim.mode == 'CMYK' and ct == DEFAULT_CT_CMYK

    data, filters = remove_simple_filters(pim)

    if filters == ['/CCITTFaxDecode']:
        if pim.colorspace == '/ICCBased':
            icc = pim._iccstream.read_bytes()
        else:
            icc = None
        stream.write(
            generate_ccitt_header_from_image(
                pim, data, icc=icc, apply_decode_array=apply_decode_array
            )
        )
        stream.write(data)
        return '.tif'
    if filters == ['/DCTDecode'] and (
        pim.mode == 'L' or normal_dct_rgb() or normal_dct_cmyk()
    ):
        # /Decode is intentionally not applied to JPEG: the codec carries its
        # own color semantics (notably the Adobe APP14 marker for inverted
        # CMYK), which Pillow already honors; re-applying /Decode would
        # double-invert. See _postprocess.apply_decode_array.
        stream.write(data)
        return '.jpg'

    return None


def extract_direct_jpx(
    pim: PdfImage, *, stream: BinaryIO, apply_decode_array: bool = True
) -> str | None:
    """Direct extraction for JPEG 2000 (JPXDecode) images."""
    # apply_decode_array is accepted for signature compatibility; /Decode is
    # deferred to the JPEG 2000 codec (see _postprocess.apply_decode_array).
    data, filters = remove_simple_filters(pim)
    if filters != ['/JPXDecode']:
        return None
    stream.write(data)
    return '.jp2'


def _transcoded_1248bits(pim: PdfImage) -> Image.Image:
    """Extract an image when there are 1/2/4/8 bits packed in byte data."""
    stride = 0  # tell Pillow to calculate stride from line width
    scale = 0 if pim.mode == 'L' else 1
    if pim.bits_per_component in (2, 4):
        buffer, stride = _transcoding.unpack_subbyte_pixels(
            pim.read_bytes(), pim.size, pim.bits_per_component, scale
        )
    elif pim.bits_per_component == 8:
        buffer = cast(memoryview, pim.get_stream_buffer())
    else:
        raise InvalidPdfImageError("BitsPerComponent must be 1, 2, 4, or 8")

    if pim.mode == 'P' and pim.palette is not None:
        base_mode, palette = pim.palette
        im = _transcoding.image_from_buffer_and_palette(
            buffer,
            pim.size,
            stride,
            base_mode,
            palette,
        )
    else:
        im = _transcoding.image_from_byte_buffer(buffer, pim.size, stride)
    return im


def _transcoded_16bit(pim: PdfImage) -> Image.Image:
    """Extract a 16-bit-per-component image.

    16-bit grayscale is produced losslessly as Pillow ``I;16``. Pillow has no
    48/64-bit raw mode, so 16-bit RGB/CMYK are reduced to 8-bit (high byte)
    with a warning.
    """
    from PIL import Image

    if pim.indexed:
        raise UnsupportedImageTypeError("16-bit indexed images are not supported")
    if pim.mode == 'I;16':
        return _transcoding.image_from_int16_buffer(pim.read_bytes(), pim.size)
    if pim.mode in ('RGB', 'CMYK'):
        warnings.warn(
            f"16-bit {pim.mode} image reduced to 8-bit: Pillow has no "
            "48/64-bit-per-pixel mode.",
            UserWarning,
            stacklevel=3,
        )
        data8 = _transcoding.downconvert_int16_to_8bit(pim.read_bytes())
        return Image.frombuffer(pim.mode, pim.size, data8, 'raw', pim.mode, 0, 1)
    raise UnsupportedImageTypeError(repr(pim) + ", " + repr(pim.obj))


def _transcoded_lab(pim: PdfImage) -> Image.Image:
    """Extract a /Lab image as a Pillow ``LAB`` image.

    PDF Lab samples decode (via the /Decode array) to physical L in [0, 100]
    and a*/b* in the colour space's /Range. Pillow's ``LAB`` mode instead
    stores L as 0..255 and a*/b* as 0..255 (with 128 representing zero), so
    each band is remapped with a lookup table. The /Decode remap is therefore
    baked in here and skipped by ``_postprocess.apply_decode_array``.
    """
    from PIL import Image

    if pim.bits_per_component == 16:
        raw = _transcoding.downconvert_int16_to_8bit(pim.read_bytes())
    elif pim.bits_per_component == 8:
        raw = pim.read_bytes()
    else:
        raise UnsupportedImageTypeError("Lab images must be 8 or 16 bits per component")

    decode = cast(RGBDecodeArray, pim._decode_array)

    def lut(dmin: float, dmax: float, *, lightness: bool) -> list[int]:
        out = []
        for s in range(256):
            phys = dmin + (s / 255.0) * (dmax - dmin)
            val = phys / 100.0 * 255.0 if lightness else phys + 128.0
            out.append(int(round(min(255.0, max(0.0, val)))))
        return out

    # Interpret the interleaved L,a,b bytes as a 3-band image and split.
    src = Image.frombuffer('RGB', pim.size, raw, 'raw', 'RGB', 0, 1)
    l_band, a_band, b_band = src.split()
    return Image.merge(
        'LAB',
        (
            l_band.point(lut(decode[0], decode[1], lightness=True)),
            a_band.point(lut(decode[2], decode[3], lightness=False)),
            b_band.point(lut(decode[4], decode[5], lightness=False)),
        ),
    )


def _transcoded_1bit(pim: PdfImage) -> Image.Image:
    from PIL import Image

    if not pim.image_mask and pim.mode in ('RGB', 'CMYK'):
        raise UnsupportedImageTypeError("1-bit RGB and CMYK are not supported")
    try:
        data = pim.read_bytes()
    except (RuntimeError, PdfError) as e:
        if (
            'read_bytes called on unfilterable stream' in str(e)
            and not jbig2.get_decoder().available()
        ):
            raise DependencyError(
                "jbig2dec - not installed or installed version is too old "
                "(older than version 0.15)"
            ) from None
        raise

    # Pillow's '1' mode stores a byte per pixel, and Image.frombytes allocates
    # the whole image before it discovers the data is short -- so, as in
    # unpack_subbyte_pixels, the declared /Width and /Height must be backed by
    # real data first. A 1-bit row occupies ceil(width / 8) bytes (rows begin on
    # a byte boundary, ISO 32000-2 §8.9.3).
    width, height = pim.size
    if width <= 0 or height <= 0:
        raise InvalidPdfImageError(f"Image has invalid dimensions {width}x{height}")
    expected = ((width + 7) // 8) * height
    if len(data) < expected:
        raise ImageDecompressionError(
            f"Image data is {len(data)} bytes, but a {width}x{height} image "
            f"at 1 bit per component requires {expected} bytes"
        )

    im = Image.frombytes('1', pim.size, data)

    if pim.palette is not None:
        base_mode, palette = pim.palette
        im = _transcoding.fix_1bit_palette_image(im, base_mode, palette)

    return im


def _transcoded_mask(pim: PdfImage) -> Image.Image:
    return _transcoded_1bit(pim)


def _transcoded_jpeg(pim: PdfImage) -> Image.Image:
    """Decode a DCTDecode (JPEG) image with Pillow.

    Used when the JPEG cannot be copied out as a standalone file -- for
    example a non-default /ColorTransform (a YCCK CMYK or a non-YCbCr RGB
    JPEG) -- so it must be decoded to pixels. Pillow's decoder honours the
    JPEG's own markers (the Adobe APP14 transform that signals YCbCr/YCCK and
    inverted CMYK), which the raw PDF parameters cannot convey.
    """
    from PIL import Image

    data, filters = remove_simple_filters(pim)
    if filters != ['/DCTDecode']:
        raise UnsupportedImageTypeError(repr(pim) + ", " + repr(pim.obj))
    with _pillow_pixel_limit(None):
        im = Image.open(BytesIO(data))
        im.load()
    return im


def extract_transcoded(pim: PdfImage) -> Image.Image:
    """Decode the image to pixels and build a Pillow image.

    Dispatches to the format-specific helper based on the image's mode, bit
    depth and filters, then attaches an ICC profile (real or synthesized from
    Cal* parameters) when one applies. /Decode is applied by ``as_pil_image``
    (the pixel-space chokepoint), not here, so it is applied exactly once.
    """
    from PIL import Image

    if pim.image_mask:
        return _transcoded_mask(pim)

    if pim.mode in {'DeviceN', 'Separation'}:
        raise HifiPrintImageNotTranscodableError()

    if '/DCTDecode' in pim.filters:
        # A JPEG that declined direct extraction (e.g. a non-default
        # /ColorTransform) is decoded by Pillow rather than read as raw
        # samples, which qpdf cannot produce for DCTDecode at this level.
        im = _transcoded_jpeg(pim)
    elif pim.colorspace == '/Lab' and not pim.indexed:
        im = _transcoded_lab(pim)
    elif pim.bits_per_component == 16:
        im = _transcoded_16bit(pim)
    elif pim.mode == 'RGB' and pim.bits_per_component == 8:
        # Cannot use the zero-copy .get_stream_buffer here, we have 3-byte
        # RGB and Pillow needs RGBX.
        im = Image.frombuffer('RGB', pim.size, pim.read_bytes(), 'raw', 'RGB', 0, 1)
    elif pim.mode == 'CMYK' and pim.bits_per_component == 8:
        im = Image.frombuffer(
            'CMYK', pim.size, pim.get_stream_buffer(), 'raw', 'CMYK', 0, 1
        )
    # elif pim.mode == '1':
    elif pim.bits_per_component == 1:
        im = _transcoded_1bit(pim)
    elif pim.mode in ('L', 'P') and pim.bits_per_component <= 8:
        im = _transcoded_1248bits(pim)
    else:
        raise UnsupportedImageTypeError(repr(pim) + ", " + repr(pim.obj))

    # Note: /Decode is applied by as_pil_image (the pixel-space chokepoint),
    # not here, so that it is applied exactly once across all code paths.
    if pim.colorspace == '/ICCBased' and pim.icc is not None:
        im.info['icc_profile'] = pim.icc.tobytes()
    else:
        cal_icc = pim._synthesize_cal_icc()
        if cal_icc is not None:
            im.info['icc_profile'] = cal_icc

    return im


def generate_ccitt_header_from_image(
    pim: PdfImage,
    data: bytes,
    icc: bytes | None = None,
    *,
    apply_decode_array: bool = True,
) -> bytes:
    """Construct a CCITT G3 or G4 header from the PDF metadata."""
    # https://stackoverflow.com/questions/2641770/
    # https://www.itu.int/itudoc/itu-t/com16/tiff-fx/docs/tiff6.pdf

    # Use the /DecodeParms that belong to the /CCITTFaxDecode filter itself.
    # When simple filters are stripped from in front of it, CCITTFaxDecode is
    # no longer at index 0, so its parameters are not decode_parms[0].
    ccitt_parms = next(
        (parms for filt, parms in pim.filter_decodeparms if filt == '/CCITTFaxDecode'),
        None,
    )
    if not ccitt_parms:
        raise ValueError("/CCITTFaxDecode without /DecodeParms")

    expected_defaults = [
        ("/EncodedByteAlign", False),
    ]
    for name, val in expected_defaults:
        if ccitt_parms.get(name, val) != val:
            raise UnsupportedImageTypeError(
                f"/CCITTFaxDecode with decode parameter {name} not equal {val}"
            )

    k = int(ccitt_parms.get("/K", 0))
    t4_options = None
    if k < 0:
        ccitt_group = 4  # Group 4
    elif k > 0:
        ccitt_group = 3  # Group 3 2-D
        t4_options = 1
    else:
        ccitt_group = 3  # Group 3 1-D
    black_is_one = ccitt_parms.get("/BlackIs1", False)
    decode = pim._decode_array
    # PDF spec says:
    # BlackIs1: A flag indicating whether 1 bits shall be interpreted as black
    # pixels and 0 bits as white pixels, the reverse of the normal
    # PDF convention for image data. Default value: false.
    # TIFF spec says:
    # use 0 for white_is_zero (=> black is 1) MINISWHITE
    # use 1 for black_is_zero (=> white is 1) MINISBLACK
    photometry = 1 if black_is_one else 0

    # If Decode is [1, 0] then the photometry is inverted. BlackIs1 is part
    # of CCITT decoding itself and always honored; the /Decode remap is
    # only baked in when the caller wants it applied.
    if apply_decode_array and len(decode) == 2 and decode == (1.0, 0.0):
        photometry = 1 - photometry

    img_size = len(data)
    if icc is None:
        icc = b''

    return _transcoding.generate_ccitt_header(
        pim.size,
        data_length=img_size,
        ccitt_group=ccitt_group,
        t4_options=t4_options,
        photometry=photometry,
        icc=icc,
    )
