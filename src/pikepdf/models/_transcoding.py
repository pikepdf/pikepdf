# SPDX-FileCopyrightText: 2022 James R. Barlow
# SPDX-License-Identifier: MPL-2.0

from __future__ import annotations

import struct
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, NamedTuple

from pikepdf._core import _unpack_subbyte_2bit, _unpack_subbyte_4bit
from pikepdf.models._image_exceptions import ImageDecompressionError

if TYPE_CHECKING:
    from PIL import Image


BytesLike = bytes | memoryview
MutableBytesLike = bytearray | memoryview


def _next_multiple(n: int, k: int) -> int:
    """Return the multiple of k that is greater than or equal n.

    >>> _next_multiple(101, 4)
    104
    >>> _next_multiple(100, 4)
    100
    """
    div, mod = divmod(n, k)
    if mod > 0:
        div += 1
    return div * k


def unpack_subbyte_pixels(
    packed: BytesLike, size: tuple[int, int], bits: int, scale: int = 0
) -> tuple[BytesLike, int]:
    """Unpack subbyte *bits* pixels into full bytes and rescale.

    When scale is 0, the appropriate scale is calculated.
    e.g. for 2-bit, the scale is adjusted so that
        0b00 = 0.00 = 0x00
        0b01 = 0.33 = 0x55
        0b10 = 0.66 = 0xaa
        0b11 = 1.00 = 0xff
    When scale is 1, no scaling is applied, appropriate when
    the bytes are palette indexes.

    Raises:
        ImageDecompressionError: if *size* is not positive, or *packed* is
            shorter than a *size* image at *bits* per component requires.
    """
    width, height = size
    if width <= 0 or height <= 0:
        raise ImageDecompressionError(f"Image has invalid dimensions {width}x{height}")
    bits_per_byte = 8 // bits
    stride = _next_multiple(width, bits_per_byte)

    # Each row of image data begins on a byte boundary (ISO 32000-2 §8.9.3),
    # so a row occupies ceil(width * bits / 8) packed bytes. Requiring that many
    # bytes per row *before* allocating bounds the allocation by the data
    # actually present: width and height are attacker-controlled /Width and
    # /Height, and a crafted PDF can declare an enormous image backed by a
    # handful of stream bytes, exhausting memory (a DoS). The pixel limit in
    # PdfImage.MAX_IMAGE_PIXELS caps plausible images; this catches the
    # implausible ones, and applies even when that limit is disabled.
    packed_row_bytes = (width * bits + 7) // 8
    expected = packed_row_bytes * height
    if len(packed) < expected:
        raise ImageDecompressionError(
            f"Image data is {len(packed)} bytes, but a {width}x{height} image "
            f"at {bits} bits per component requires {expected} bytes"
        )

    # Unpacking produces one byte per pixel, with each row padded out to
    # *stride* bytes, so bits_per_byte * packed_row_bytes == stride.
    buffer = bytearray(stride * height)
    max_read = len(buffer) // bits_per_byte
    if scale == 0:
        # 255 // (2**bits - 1) is exact for bits in {1, 2, 4, 8}:
        # 2-bit -> 85, 4-bit -> 17, so a nibble * scale always fits in a byte.
        scale = 255 // ((2**bits) - 1)
    if bits == 4:
        _4bit_inner_loop(packed[:max_read], buffer, scale)
    elif bits == 2:
        _2bit_inner_loop(packed[:max_read], buffer, scale)
    else:
        # Only 2- and 4-bit samples are unpacked here. 1-bit images never reach
        # this function: extract_transcoded routes them to _transcoded_1bit,
        # which relies on Pillow's native packed '1' mode (bit 0 -> 0, bit
        # 1 -> 255) rather than expanding each bit to a full byte. 2- and 4-bit
        # have no equivalent packed Pillow mode, and their values must be
        # rescaled to span 0-255 (e.g. 2-bit 0b01 -> 0x55), so they are unpacked
        # here. 8-bit is already byte-aligned and needs no unpacking.
        raise NotImplementedError(bits)
    return memoryview(buffer), stride


def _2bit_inner_loop(in_: BytesLike, out: MutableBytesLike, scale: int) -> None:
    """Unpack 2-bit values to their 8-bit equivalents.

    Thus *out* must be 4x at long as *in*.
    """
    _unpack_subbyte_2bit(in_, out, scale)


def _4bit_inner_loop(in_: BytesLike, out: MutableBytesLike, scale: int) -> None:
    """Unpack 4-bit values to their 8-bit equivalents.

    Thus *out* must be 2x at long as *in*.
    """
    _unpack_subbyte_4bit(in_, out, scale)


def image_from_byte_buffer(buffer: BytesLike, size: tuple[int, int], stride: int):
    """Use Pillow to create one-component image from a byte buffer.

    *stride* is the number of bytes per row, and is essential for packed bits
    with odd image widths.
    """
    from PIL import Image

    ystep = 1  # image is top to bottom in memory
    # Even if the image is type 'P' (palette), we create it as a 'L' grayscale
    # at this step. The palette is attached later.
    try:
        return Image.frombuffer('L', size, buffer, "raw", 'L', stride, ystep)
    except ValueError as e:
        if 'buffer is not large enough' in str(e):
            # If Pillow says the buffer is not large enough, then we're going
            # to guess that it's padded to a multiple of 4 bytes. In practice
            # the image may just be corrupted.
            try:
                return Image.frombuffer(
                    'L', size, buffer, "raw", 'L', (size[0] + 3) // 4, ystep
                )
            except ValueError as e2:
                raise ImageDecompressionError(str(e2)) from e2
        else:
            raise ImageDecompressionError() from e


def image_from_int16_buffer(buffer: BytesLike, size: tuple[int, int]):
    """Create a 16-bit grayscale image from a buffer of big-endian samples.

    PDF stores 16-bit samples most-significant-byte first (ISO 32000-2 §8.9.3).
    The data is read big-endian and normalized to native ``I;16`` via a 32-bit
    ``I`` intermediate: Pillow's direct ``I;16B`` -> ``I;16`` conversion clips to
    8 bits, but going through ``I`` is lossless.
    """
    from PIL import Image

    try:
        im = Image.frombuffer('I;16', size, buffer, 'raw', 'I;16B', 0, 1)
        return im.convert('I').convert('I;16')
    except ValueError as e:
        raise ImageDecompressionError() from e


def downconvert_int16_to_8bit(buffer: BytesLike) -> bytes:
    """Reduce big-endian 16-bit samples to 8-bit by keeping the high byte.

    Pillow has no 48/64-bit-per-pixel raw mode for RGB/CMYK, so multi-component
    16-bit images are lossily reduced to 8-bit: the high (most significant) byte
    of every 2-byte big-endian sample is taken.
    """
    mv = memoryview(buffer)
    return bytes(mv[0::2])


def colorkey_alpha(
    raw: BytesLike, size: tuple[int, int], nbands: int, ranges: list[int]
) -> Image.Image:
    """Build an ``L`` alpha band from a colour-key mask over 8-bit samples.

    A sample is masked out (alpha 0) when every component falls within its
    ``[min, max]`` range from *ranges* (``[min1 max1 ... minn maxn]``), per
    ISO 32000-2 §8.9.6.4; otherwise it is opaque (alpha 255).
    """
    from PIL import Image

    width, height = size
    count = width * height
    out = bytearray(count)
    mv = memoryview(raw)
    for px in range(count):
        masked = True
        for c in range(nbands):
            v = mv[px * nbands + c]
            if not (ranges[2 * c] <= v <= ranges[2 * c + 1]):
                masked = False
                break
        out[px] = 0 if masked else 255
    return Image.frombuffer('L', size, bytes(out), 'raw', 'L', 0, 1)


def _make_rgb_palette(gray_palette: BytesLike) -> bytes:
    palette = b''
    for entry in gray_palette:
        palette += bytes([entry]) * 3
    return palette


def _depalettize_cmyk(buffer: BytesLike, palette: BytesLike):
    with memoryview(buffer) as mv:
        output = bytearray(4 * len(mv))
        for n, pal_idx in enumerate(mv):
            output[4 * n : 4 * (n + 1)] = palette[4 * pal_idx : 4 * (pal_idx + 1)]
    return output


def image_from_buffer_and_palette(
    buffer: BytesLike,
    size: tuple[int, int],
    stride: int,
    base_mode: str,
    palette: BytesLike,
) -> Image.Image:
    """Construct an image from a byte buffer and apply the palette.

    1/2/4-bit images must be unpacked (no scaling!) to byte buffers first, such
    that every 8-bit integer is an index into the palette.
    """
    if base_mode == 'RGB':
        im = image_from_byte_buffer(buffer, size, stride)
        im.putpalette(palette, rawmode=base_mode)
    elif base_mode == 'L':
        # Pillow does not fully support palettes with rawmode='L'.
        # Convert to RGB palette.
        gray_palette = _make_rgb_palette(palette)
        im = image_from_byte_buffer(buffer, size, stride)
        im.putpalette(gray_palette, rawmode='RGB')
    elif base_mode == 'CMYK':
        from PIL import Image

        # Pillow does not support CMYK with palettes; convert manually
        output = _depalettize_cmyk(buffer, palette)
        im = Image.frombuffer('CMYK', size, data=output, decoder_name='raw')
    else:
        raise NotImplementedError(f'palette with {base_mode}')
    return im


def fix_1bit_palette_image(
    im: Image.Image, base_mode: str, palette: BytesLike
) -> Image.Image:
    """Apply palettes to 1-bit images."""
    if base_mode == 'CMYK':
        from PIL import Image

        # Pillow cannot attach a CMYK palette to a 'P' image, so depalettize
        # manually the way the 2/4/8-bit path does. The two 1-bit levels come
        # back from Pillow as 0/255; remap them to palette indices 0/1 before
        # the CMYK lookup.
        indices = im.convert('L').point(lambda v: 1 if v else 0).tobytes()
        output = _depalettize_cmyk(indices, palette)
        return Image.frombuffer('CMYK', im.size, data=output, decoder_name='raw')
    im = im.convert('P')
    if base_mode == 'RGB':
        # Pillow maps the two 1-bit levels to indices 0 and 255 during the
        # convert('P') above, so place palette entry 0 at index 0 and entry 1
        # (when the image has two colours) at index 255, with the rest black.
        # A single-colour palette (hival 0, 3 bytes) leaves every pixel at
        # index 0.
        expanded = bytearray(256 * 3)
        expanded[0:3] = palette[0:3]
        if len(palette) >= 6:
            expanded[255 * 3 : 256 * 3] = palette[3:6]
        im.putpalette(bytes(expanded), rawmode='RGB')
    elif base_mode == 'L':
        try:
            im.putpalette(palette, rawmode='L')
        except ValueError as e:
            if 'unrecognized raw mode' in str(e):
                rgb_palette = _make_rgb_palette(palette)
                im.putpalette(rgb_palette, rawmode='RGB')
    else:
        # Fail loudly rather than return an unpalettized image, matching
        # image_from_buffer_and_palette (the 2/4/8-bit path).
        raise NotImplementedError(f'palette with {base_mode}')
    return im


def generate_ccitt_header(
    size: tuple[int, int],
    *,
    data_length: int,
    ccitt_group: int,
    t4_options: int | None,
    photometry: int,
    icc: bytes,
) -> bytes:
    """Generate binary CCITT header for image with given parameters."""
    tiff_header_struct = '<' + '2s' + 'H' + 'L' + 'H'
    from PIL.TiffTags import TAGS_V2 as TIFF_TAGS

    tag_keys = {tag.name: key for key, tag in TIFF_TAGS.items()}  # type: ignore
    ifd_struct = '<HHLL'

    class IFD(NamedTuple):
        key: int
        typecode: Any
        count_: int
        data: int | Callable[[], int | None]

    ifds: list[IFD] = []

    def header_length(ifd_count) -> int:
        return (
            struct.calcsize(tiff_header_struct)
            + struct.calcsize(ifd_struct) * ifd_count
            + 4
        )

    def add_ifd(tag_name: str, data: int | Callable[[], int | None], count: int = 1):

        key = tag_keys[tag_name]
        typecode = TIFF_TAGS[key].type  # type: ignore
        ifds.append(IFD(key, typecode, count, data))

    image_offset = None
    width, height = size
    add_ifd('ImageWidth', width)
    add_ifd('ImageLength', height)
    add_ifd('BitsPerSample', 1)
    add_ifd('Compression', ccitt_group)
    add_ifd('FillOrder', 1)
    if t4_options is not None:
        add_ifd('T4Options', t4_options)
    add_ifd('PhotometricInterpretation', photometry)
    add_ifd('StripOffsets', lambda: image_offset)
    add_ifd('RowsPerStrip', height)
    add_ifd('StripByteCounts', data_length)

    icc_offset = 0
    if icc:
        add_ifd('ICCProfile', lambda: icc_offset, count=len(icc))

    icc_offset = header_length(len(ifds))
    image_offset = icc_offset + len(icc)

    ifd_args = [(arg() if callable(arg) else arg) for ifd in ifds for arg in ifd]
    tiff_header = struct.pack(
        (tiff_header_struct + ifd_struct[1:] * len(ifds) + 'L'),
        b'II',  # Byte order indication: Little endian
        42,  # Version number (always 42)
        8,  # Offset to first IFD
        len(ifds),  # Number of tags in IFD
        *ifd_args,
        0,  # Last IFD
    )

    if icc:
        tiff_header += icc
    return tiff_header
