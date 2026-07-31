# SPDX-FileCopyrightText: 2022 James R. Barlow
# SPDX-License-Identifier: MPL-2.0

"""Extract images embedded in PDF."""

from __future__ import annotations

from abc import ABCMeta
from typing import TYPE_CHECKING, cast

from pikepdf.models._image_exceptions import (
    HifiPrintImageNotTranscodableError,
    ImageDecompressionError,
    InvalidPdfImageError,
    UnsupportedImageTypeError,
)
from pikepdf.models.image._bomb import _decompression_bomb_classes
from pikepdf.models.image._shared import (
    CMYKDecodeArray,
    DecodeArray,
    PaletteData,
    RGBDecodeArray,
)

if TYPE_CHECKING:
    from PIL import Image

    # Created lazily at runtime by _decompression_bomb_classes()/__getattr__ to
    # keep Pillow out of ``import pikepdf``; declared here for static analysis.
    DecompressionBombError = Image.DecompressionBombError
    DecompressionBombWarning = Image.DecompressionBombWarning


def __getattr__(name: str):
    """Lazily expose the Pillow-derived exception classes as module attributes.

    This must live on the package ``__init__`` because ``pikepdf/__init__.py``
    resolves the bomb classes via ``getattr(image, name)`` on this module.
    """
    if name in ('DecompressionBombError', 'DecompressionBombWarning'):
        error, warning = _decompression_bomb_classes()
        return error if name.endswith('Error') else warning
    raise AttributeError(f'module {__name__!r} has no attribute {name!r}')


# Decompression-bomb limit state (issue #733). These module globals and the
# ``MAX_IMAGE_PIXELS`` metaclass live here, rather than in ``_bomb``, because the
# tests poke ``pikepdf.models.image._max_image_pixels`` directly (read and
# write) and the metaclass setter writes that same module global. The stateless,
# Pillow-coupled machinery lives in ``_bomb`` (see ``check_pixels``).
_UNSET = object()
_max_image_pixels: object | int | None = _UNSET
_PIKEPDF_PIXEL_FLOOR = 500_000_000


class _PdfImageMeta(ABCMeta):
    """Metaclass providing the class-level ``MAX_IMAGE_PIXELS`` property."""

    @property
    def MAX_IMAGE_PIXELS(cls) -> int | None:
        """Maximum number of pixels pikepdf will decode from a single image.

        Analogous to :data:`PIL.Image.MAX_IMAGE_PIXELS`. Images larger than
        twice this value raise :class:`pikepdf.DecompressionBombError`; images
        larger than this value emit :class:`pikepdf.DecompressionBombWarning`.
        Set to ``None`` to disable the check entirely.

        Until it is assigned, this defaults to
        ``max(500_000_000, PIL.Image.MAX_IMAGE_PIXELS)`` -- Pillow's default is
        often too low for high-DPI scanned PDFs. Once assigned, the value is
        independent of Pillow's setting.
        """
        if _max_image_pixels is _UNSET:
            from PIL import Image

            pil = Image.MAX_IMAGE_PIXELS
            if pil is None:
                return _PIKEPDF_PIXEL_FLOOR
            return max(_PIKEPDF_PIXEL_FLOOR, pil)
        return cast('int | None', _max_image_pixels)

    @MAX_IMAGE_PIXELS.setter
    def MAX_IMAGE_PIXELS(cls, value: int | None) -> None:
        global _max_image_pixels
        _max_image_pixels = value


# Imported after _PdfImageMeta and the bomb-limit globals are defined above,
# because _classes imports _PdfImageMeta from this module (the base-before-
# subclass circular-import pattern). Hence the late, non-top-of-file import.
from pikepdf.models.image._classes import (  # noqa: E402
    PdfImage,
    PdfImageBase,
    PdfInlineImage,
    PdfJpxImage,
)

__all__ = [
    'CMYKDecodeArray',
    'DecodeArray',
    'DecompressionBombError',
    'DecompressionBombWarning',
    'HifiPrintImageNotTranscodableError',
    'ImageDecompressionError',
    'InvalidPdfImageError',
    'PaletteData',
    'PdfImage',
    'PdfImageBase',
    'PdfInlineImage',
    'PdfJpxImage',
    'RGBDecodeArray',
    'UnsupportedImageTypeError',
]
