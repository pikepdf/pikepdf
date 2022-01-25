# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
#
# Copyright (C) 2022, James R. Barlow (https://github.com/jbarlow83/)


from typing import Tuple


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
    packed: bytes, size: Tuple[int, int], bits: int, scale: int = 0
):
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


def _2bit_inner_loop(in_: bytes, out: bytearray, scale: int) -> None:
    for n, val in enumerate(in_):
        out[4 * n] = int((val >> 6) * scale)
        out[4 * n + 1] = int(((val >> 4) & 0b11) * scale)
        out[4 * n + 2] = int(((val >> 2) & 0b11) * scale)
        out[4 * n + 3] = int((val & 0b11) * scale)


def _4bit_inner_loop(in_: bytes, out: bytearray, scale: int) -> None:
    for n, val in enumerate(in_):
        out[2 * n] = int((val >> 4) * scale)
        out[2 * n + 1] = int((val & 0b1111) * scale)
