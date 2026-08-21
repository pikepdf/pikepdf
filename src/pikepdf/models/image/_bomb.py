# SPDX-FileCopyrightText: 2022 James R. Barlow
# SPDX-License-Identifier: MPL-2.0

"""Decompression-bomb protection: the Pillow-coupled helpers and pixel budget.

pikepdf mirrors Pillow's ``MAX_IMAGE_PIXELS`` mechanism (issue #733), but with
its own limit (PDFs routinely hold high-DPI scans that exceed Pillow's default)
and its own exception types (which subclass Pillow's, so existing handlers keep
working). Pillow is imported lazily everywhere here so that ``import pikepdf``
does not import Pillow (see ``tests/test_lazy_load.py``).

The mutable limit state and the ``MAX_IMAGE_PIXELS`` metaclass live in the
package ``__init__`` (tests poke ``pikepdf.models.image._max_image_pixels``
directly, and the metaclass setter writes that same module global). The
stateless, Pillow-touching machinery lives here. :func:`check_pixels` reads the
limit through ``type(target).MAX_IMAGE_PIXELS``, so it needs neither the global
nor an import of the metaclass.
"""

from __future__ import annotations

import threading
import warnings
from contextlib import contextmanager
from typing import TYPE_CHECKING

from pikepdf._core import PikepdfError
from pikepdf._exceptions import PikepdfWarning

if TYPE_CHECKING:
    from pikepdf.models.image._classes import PdfImageBase

# The public-facing module path for the lazily-created bomb classes; kept stable
# so ``pikepdf.DecompressionBombError`` reports ``pikepdf.models.image`` as its
# module regardless of which internal module actually builds it.
_PUBLIC_MODULE = 'pikepdf.models.image'

# Built lazily so that ``import pikepdf`` does not import Pillow (see
# tests/test_lazy_load.py).
_bomb_classes: dict[str, type] = {}
_pil_limit_lock = threading.Lock()


def _decompression_bomb_classes() -> tuple[type, type]:
    """Return pikepdf's (DecompressionBombError, DecompressionBombWarning).

    These subclass Pillow's equivalents and are constructed on first use, so
    that merely importing pikepdf does not import Pillow.
    """
    if not _bomb_classes:
        from PIL import Image

        # Mixing in the pikepdf roots keeps `except PikepdfError` complete
        # without disturbing handlers written against Pillow's classes.
        _bomb_classes['error'] = type(
            'DecompressionBombError',
            (PikepdfError, Image.DecompressionBombError),
            {
                '__module__': _PUBLIC_MODULE,
                '__doc__': "Image has more pixels than "
                ":attr:`pikepdf.PdfImage.MAX_IMAGE_PIXELS` allows.",
            },
        )
        _bomb_classes['warning'] = type(
            'DecompressionBombWarning',
            (PikepdfWarning, Image.DecompressionBombWarning),
            {
                '__module__': _PUBLIC_MODULE,
                '__doc__': "Image has more pixels than "
                ":attr:`pikepdf.PdfImage.MAX_IMAGE_PIXELS` allows.",
            },
        )
    return _bomb_classes['error'], _bomb_classes['warning']


@contextmanager
def _pillow_pixel_limit(limit: int | None):
    """Temporarily set Pillow's global ``MAX_IMAGE_PIXELS`` for a decode.

    Used to make pikepdf's limit (not Pillow's default) govern the
    Pillow-decoded direct-extraction path. The lock spans only the brief window
    in which Pillow checks the image size (at ``Image.open``, before any pixels
    are decoded), so it does not serialize actual decoding.
    """
    from PIL import Image

    with _pil_limit_lock:
        saved = Image.MAX_IMAGE_PIXELS
        Image.MAX_IMAGE_PIXELS = limit
        try:
            yield
        finally:
            Image.MAX_IMAGE_PIXELS = saved


def check_pixels(target: PdfImageBase, width: int, height: int) -> None:
    """Guard against decompression-bomb images (issue #733).

    Mirrors :func:`PIL.Image._decompression_bomb_check`, but uses pikepdf's
    :attr:`MAX_IMAGE_PIXELS` (read from *target*'s class) and raises pikepdf's
    exception types.
    """
    limit = type(target).MAX_IMAGE_PIXELS
    if limit is None:
        return
    pixels = max(1, width) * max(1, height)
    error, warning = _decompression_bomb_classes()
    if pixels > 2 * limit:
        raise error(
            f"Image size ({pixels} pixels) exceeds limit of "
            f"{2 * limit} pixels; possible decompression bomb."
        )
    if pixels > limit:
        warnings.warn(
            f"Image size ({pixels} pixels) exceeds limit of "
            f"{limit} pixels; possible decompression bomb.",
            warning,
            stacklevel=3,
        )
