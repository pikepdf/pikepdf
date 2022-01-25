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
    for n, val in enumerate(in_):
        out[4 * n] = int((val >> 6) * scale)
        out[4 * n + 1] = int(((val >> 4) & 0b11) * scale)
        out[4 * n + 2] = int(((val >> 2) & 0b11) * scale)
        out[4 * n + 3] = int((val & 0b11) * scale)


def _4bit_inner_loop(in_: BytesLike, out: MutableBytesLike, scale: int) -> None:
    for n, val in enumerate(in_):
        out[2 * n] = int((val >> 4) * scale)
        out[2 * n + 1] = int((val & 0b1111) * scale)


def image_from_byte_buffer(buffer: BytesLike, size: Tuple[int, int], stride):
    ystep = 1  # image is top to bottom in memory
    return Image.frombuffer('L', size, buffer, "raw", 'L', stride, ystep)


def image_from_buffer_and_palette(
    base_mode: str,
    palette: BytesLike,
    buffer: BytesLike,
    size: Tuple[int, int],
    bits: int,
    stride: int,
) -> Image.Image:
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
