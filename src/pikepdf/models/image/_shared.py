# SPDX-FileCopyrightText: 2022 James R. Barlow
# SPDX-License-Identifier: MPL-2.0

"""Shared leaf symbols for the image package: helpers and type aliases.

This module has no intra-package dependencies (it imports only stdlib,
:mod:`pikepdf.objects` and :func:`pikepdf.unbox`), so it can be imported by
every other module in the ``image`` package without risking an import cycle.
The image exceptions live one level up, in
:mod:`pikepdf.models._image_exceptions`, so that
:mod:`pikepdf.models._transcoding` can raise them without importing this
package.
"""

from __future__ import annotations

from collections.abc import Callable
from decimal import Decimal
from typing import Any, NamedTuple, TypeVar

from pikepdf._explicit_conv import unbox
from pikepdf.objects import (
    Array,
    Dictionary,
    Name,
    Object,
    Stream,
    String,
)

T = TypeVar('T')

RGBDecodeArray = tuple[float, float, float, float, float, float]
GrayDecodeArray = tuple[float, float]
CMYKDecodeArray = tuple[float, float, float, float, float, float, float, float]
DecodeArray = RGBDecodeArray | GrayDecodeArray | CMYKDecodeArray

# Filters that are *terminal* image codecs: each is a complete, irreducible
# compression scheme that produces final image samples and cannot be composed
# with another terminal codec. qpdf cannot strip these as generalized/
# specialized filters, so they are handled by pikepdf/Pillow at extraction time.
TERMINAL_FILTERS = frozenset(
    {'/DCTDecode', '/JPXDecode', '/JBIG2Decode', '/CCITTFaxDecode'}
)


def _array_str(value: Object | str | list):
    """Simplify pikepdf objects to array of str. Keep streams, dictionaries intact."""

    def _convert(item):
        # Unbox first, so a PDF number or boolean is the same native value
        # whichever conversion mode delivered it.
        item = unbox(item)
        if isinstance(item, list | Array):
            return [_convert(subitem) for subitem in item]
        if isinstance(item, Stream | Dictionary | bytes | int | Decimal):
            return item
        if isinstance(item, Name | str):
            return str(item)
        if isinstance(item, String):
            return bytes(item)
        raise NotImplementedError(value)

    result = _convert(value)
    if not isinstance(result, list):
        result = [result]
    return result


def _ensure_list(value: list[Object] | Dictionary | Array | Object) -> list[Object]:
    """Ensure value is a list of pikepdf.Object, if it was not already.

    To support DecodeParms which can be present as either an array of dicts or a single
    dict. It's easier to convert to an array of one dict.
    """
    if isinstance(value, list):
        return value
    return list(value.wrap_in_array().as_list())


def _metadata_from_obj(
    obj: Object, name: str, type_: Callable[[Any], T], default: Any
) -> T:
    """Retrieve metadata from a dictionary or stream and wrangle types.

    *obj* is the underlying image object: a Stream (image XObject), or a
    Dictionary (inline image). Any Object with attribute access works.

    The value is unboxed before *type_* converts it, so the result does not
    depend on the conversion mode. A missing or null entry gives *default*;
    a value *type_* cannot convert raises NotImplementedError.
    """
    val = unbox(getattr(obj, name, default))
    try:
        return type_(val)
    except TypeError as e:
        raise NotImplementedError('Metadata access for ' + name) from e


class PaletteData(NamedTuple):
    """Returns the color space and binary representation of the palette.

    ``base_colorspace`` is typically ``"RGB"`` or ``"L"`` (for grayscale).

    ``palette`` is typically 256 or 256*3=768 bytes, for grayscale and RGB color
    respectively, with each unit/triplet being the grayscale/RGB triplet values.
    """

    base_colorspace: str
    palette: bytes
