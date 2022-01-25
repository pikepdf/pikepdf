# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
#
# Copyright (C) 2022, James R. Barlow (https://github.com/jbarlow83/)


from typing import Tuple, Union

from PIL import Image

BytesLike = Union[bytes, memoryview]
MutableBytesLike = Union[bytearray, memoryview]


def _next_multiple(n: int, k: int) -> int:
    """Returns the multiple of k that is greater than or equal n.

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
    packed: BytesLike, size: Tuple[int, int], bits: int, scale: int = 0
) -> Tuple[BytesLike, int]:
    """Unpack subbyte *bits* pixels into full bytes and rescale.

    When scale is 0, the appropriate scale is calculated.
    e.g. for 2-bit, the scale is adjusted so that
        0b00 = 0.00 = 0x00
        0b01 = 0.33 = 0x55
        0b10 = 0.66 = 0xaa
        0b11 = 1.00 = 0xff
    When scale is 1, no scaling is applied, appropriate when
    the bytes are palette indexes.
    """
    width, height = size
    bits_per_byte = 8 // bits
    stride = _next_multiple(width, bits_per_byte)
    buffer = bytearray(bits_per_byte * stride * height)
    max_read = len(buffer) // bits_per_byte
    if scale == 0:
        scale = 255 / ((2 ** bits) - 1)
    if bits == 2:
        _2bit_inner_loop(packed[:max_read], buffer, scale)
    elif bits == 4:
        _4bit_inner_loop(packed[:max_read], buffer, scale)
    else:
        raise NotImplementedError(bits)
    return memoryview(buffer), stride


def _2bit_inner_loop(in_: BytesLike, out: MutableBytesLike, scale: int) -> None:
    """Unpack 2-bit values to their 8-bit equivalents.

    Thus *out* must be 4x at long as *in*.
    """
    for n, val in enumerate(in_):
        out[4 * n] = int((val >> 6) * scale)
        out[4 * n + 1] = int(((val >> 4) & 0b11) * scale)
        out[4 * n + 2] = int(((val >> 2) & 0b11) * scale)
        out[4 * n + 3] = int((val & 0b11) * scale)


def _4bit_inner_loop(in_: BytesLike, out: MutableBytesLike, scale: int) -> None:
    """Unpack 4-bit values to their 8-bit equivalents.

    Thus *out* must be 2x at long as *in*.
    """
    for n, val in enumerate(in_):
        out[2 * n] = int((val >> 4) * scale)
        out[2 * n + 1] = int((val & 0b1111) * scale)


def image_from_byte_buffer(buffer: BytesLike, size: Tuple[int, int], stride: int):
    """Use Pillow to create image from a byte buffer.

    If the buffer conti

    *stride* is the number of bytes per row, and is essential for packed bits
    with odd image widths.
    """
    ystep = 1  # image is top to bottom in memory
    return Image.frombuffer('L', size, buffer, "raw", 'L', stride, ystep)


def image_from_buffer_and_palette(
    buffer: BytesLike,
    size: Tuple[int, int],
    stride: int,
    bits: int,
    base_mode: str,
    palette: BytesLike,
) -> Image.Image:
    """Construct an image from a byte buffer and palette."""

    # Reminder Pillow palette byte order unintentionally changed in 8.3.0
    # https://github.com/python-pillow/Pillow/issues/5595
    # 8.2.0: all aligned by channel (very nonstandard)
    # 8.3.0: all channels for one color followed by the next color (e.g. RGBRGBRGB)

    if base_mode == 'RGB':
        im = image_from_byte_buffer(buffer, size, stride)
        im.putpalette(palette, rawmode=base_mode)
    elif base_mode == 'L':
        # Pillow does not fully support palettes with rawmode='L'.
        # Convert to RGB palette.
        gray_palette = palette
        palette = b''
        shift = 8 - bits
        for entry in gray_palette:
            palette += bytes([entry << shift]) * 3
        im = image_from_byte_buffer(buffer, size, stride)
        im.putpalette(palette, rawmode='RGB')
    elif base_mode == 'CMYK':
        # Pillow does not support CMYK with palettes; convert manually
        with memoryview(buffer) as mv:
            output = bytearray(4 * len(mv))
            for n, pal_idx in enumerate(mv):
                output[4 * n : 4 * (n + 1)] = palette[4 * pal_idx : 4 * (pal_idx + 1)]
        im = Image.frombuffer('CMYK', size, data=output, decoder_name='raw')
    else:
        raise NotImplementedError(f'palette with {base_mode}')
    return im


def fix_1bit_palette_image(
    im: Image.Image, base_mode: str, palette: BytesLike
) -> Image.Image:
    """Apply palettes to 1-bit images."""
    if base_mode == 'RGB' and palette != b'\x00\x00\x00\xff\xff\xff':
        im = im.convert('P')
        im.putpalette(palette, rawmode=base_mode)
        gp = im.getpalette()
        if gp:
            gp[765:768] = gp[3:6]  # work around Pillow bug
            im.putpalette(gp)
    elif base_mode == 'L' and palette != b'\x00\xff':
        im = im.convert('P')
        im.putpalette(palette, rawmode=base_mode)
        gp = im.getpalette()
        if gp:
            gp[255] = gp[1]  # work around Pillow bug
            im.putpalette(gp)
    return im
