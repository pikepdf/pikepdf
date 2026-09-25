# SPDX-FileCopyrightText: 2022 James R. Barlow
# SPDX-License-Identifier: MPL-2.0

"""Pixel-space post-processing of a decoded image: /Decode array and masks.

These run after a base Pillow image has been produced (by direct extraction or
transcoding). They read the image's metadata through ``pim``'s properties, so
they apply uniformly across all extraction paths. Pillow is imported lazily so
that ``import pikepdf`` does not import Pillow.
"""

from __future__ import annotations

import warnings
from typing import TYPE_CHECKING

from pikepdf.models import _transcoding
from pikepdf.models.image._shared import _array_list
from pikepdf.objects import Array, Stream

if TYPE_CHECKING:
    from PIL import Image

    from pikepdf.models.image._classes import PdfImage


def apply_decode_array(pim: PdfImage, im: Image.Image) -> Image.Image:
    """Apply the /Decode array to a decoded image, in pixel space.

    The /Decode array linearly remaps each stored sample value to an output
    color value (PDF 1.7 §8.9.5.2). The default array is the identity map
    and a no-op. This operates in Pillow's 8-bit-per-band space via a
    per-band lookup table, so it works uniformly whether the pixels came
    from transcoding or from decoding a JPEG/JPX stream.

    Indexed images are skipped: their /Decode array remaps palette
    *indices*, not color values, which is a different operation that is not
    supported here. A non-identity /Decode on an Indexed image emits a
    warning rather than being silently misapplied.
    """
    from PIL import ImageChops

    # Only images carrying an explicit /Decode need adjustment; without one
    # the default (identity) map applies and the data is already correct.
    raw_decode = pim._metadata('Decode', _array_list, [])
    if not raw_decode:
        return im

    # JPEG and JPEG 2000 carry their own color/inversion semantics (notably
    # the Adobe APP14 marker for inverted CMYK), which Pillow already honors
    # when decoding. Applying /Decode on top would double-apply it, so defer
    # to the codec. Such images are extracted directly without transcoding.
    if any(filt in ('/DCTDecode', '/JPXDecode') for filt in pim.filters):
        return im

    # /Lab images bake their /Decode remap into the LAB transcode.
    if pim.colorspace == '/Lab':
        return im

    if pim.indexed:
        maxval = float((1 << pim.bits_per_component) - 1)
        if tuple(float(v) for v in raw_decode) != (0.0, maxval):
            warnings.warn(
                "/Decode array on an Indexed image is not applied: it remaps "
                "palette indices, which pikepdf does not support. The image "
                "is returned without applying /Decode.",
                UserWarning,
                stacklevel=2,
            )
        return im

    decode = pim._decode_array
    nbands = len(im.getbands())
    if len(decode) != 2 * nbands:
        # Length disagrees with the decoded image; refuse to guess.
        return im

    # Identity map: nothing to do.
    if all(decode[2 * i : 2 * i + 2] == (0.0, 1.0) for i in range(nbands)):
        return im

    # 16-bit grayscale cannot use the 8-bit lookup table below. Honour the
    # only common non-identity map, the reversal [1, 0] (via a 32-bit
    # intermediate, since Pillow cannot point() an I;16 image); warn and skip
    # any arbitrary map.
    if im.mode == 'I;16':
        if decode == (1.0, 0.0):
            out = im.convert('I').point(lambda p: 65535 - p).convert('I;16')
            out.info.update(im.info)
            return out
        warnings.warn(
            "A non-trivial /Decode array on a 16-bit grayscale image is not applied.",
            UserWarning,
            stacklevel=2,
        )
        return im

    # Bilevel images can only represent two values, so the sole meaningful
    # non-identity map is the reversal [1, 0]; handle it without leaving
    # mode '1'. Any other map requires the 8-bit lookup-table path below.
    if im.mode == '1' and decode == (1.0, 0.0):
        out = ImageChops.invert(im)
        out.info.update(im.info)
        return out

    if im.mode == '1':
        im = im.convert('L')
        nbands = 1

    lut: list[int] = []
    for i in range(nbands):
        dmin, dmax = decode[2 * i], decode[2 * i + 1]
        lut.extend(
            round(min(1.0, max(0.0, dmin + (p / 255.0) * (dmax - dmin))) * 255)
            for p in range(256)
        )
    out = im.point(lut)
    out.info.update(im.info)
    return out


def apply_mask(pim: PdfImage, im: Image.Image) -> Image.Image:
    """Composite an attached /SMask or /Mask into an alpha channel.

    Returns *im* unchanged when no mask is present. Modes that cannot carry
    an alpha channel (CMYK, LAB, I;16) are converted to RGBA with a warning.
    """
    alpha = build_alpha_band(pim, im.size)
    if alpha is None:
        return im

    info = dict(im.info)
    if im.mode == 'L':
        im.putalpha(alpha)
    elif im.mode == 'RGB':
        im.putalpha(alpha)
    elif im.mode == 'P':
        im = im.convert('RGB')
        im.putalpha(alpha)
    else:
        warnings.warn(
            f"A {im.mode} image carries a mask but that mode cannot hold an "
            "alpha channel; converting to RGBA.",
            UserWarning,
            stacklevel=3,
        )
        im = im.convert('RGB')
        im.putalpha(alpha)
    im.info.update(info)
    return im


def build_alpha_band(pim: PdfImage, base_size: tuple[int, int]) -> Image.Image | None:
    """Build an ``L`` alpha band from /SMask or /Mask, resized to *base_size*.

    Precedence: a soft mask (/SMask) wins over an explicit or colour-key
    /Mask; combining both is not supported. /SMaskInData (JPEG 2000) is left
    to the codec and handled when Pillow surfaces the alpha itself. Returns
    None when no usable mask is present.
    """
    from PIL import ImageChops

    # Deferred import to avoid an import cycle: PdfImage (in this package)
    # constructs the mask sub-images, but this module is imported while the
    # class module is still loading.
    from pikepdf.models.image import PdfImage

    smask = pim.obj.get('/SMask')
    if isinstance(smask, Stream):
        if '/Matte' in smask:
            warnings.warn(
                "/SMask has a /Matte entry (pre-multiplied alpha) which "
                "pikepdf does not undo; colours near edges may be off.",
                UserWarning,
                stacklevel=4,
            )
        smask_pim = PdfImage(smask)
        alpha = smask_pim.as_pil_image(apply_mask=False).convert('L')
        if alpha.size != base_size:
            alpha = alpha.resize(base_size)
        return alpha

    mask = pim.obj.get('/Mask')
    if isinstance(mask, Stream):
        mask_pim = PdfImage(mask)
        mask_im = mask_pim.as_pil_image(apply_mask=False).convert('L')
        # A stencil mask paints where the decoded sample is 0 and masks out
        # where it is 1, so alpha is the inverse of the mask's luminance.
        alpha = ImageChops.invert(mask_im)
        if alpha.size != base_size:
            alpha = alpha.resize(base_size)
        return alpha
    if isinstance(mask, Array):
        return colorkey_alpha(pim, mask, base_size)

    return None


def colorkey_alpha(
    pim: PdfImage, mask: Array, base_size: tuple[int, int]
) -> Image.Image | None:
    """Build an alpha band from a colour-key /Mask range array (8-bit only)."""
    if (
        pim.bits_per_component != 8
        or pim.indexed
        or pim.mode
        not in (
            'L',
            'RGB',
            'CMYK',
        )
    ):
        warnings.warn(
            "Colour-key /Mask is only supported for 8-bit L/RGB/CMYK images; "
            "it was not applied.",
            UserWarning,
            stacklevel=4,
        )
        return None
    nbands = {'L': 1, 'RGB': 3, 'CMYK': 4}[pim.mode]
    ranges = [int(v) for v in mask]
    if len(ranges) != 2 * nbands:
        return None
    return _transcoding.colorkey_alpha(pim.read_bytes(), base_size, nbands, ranges)
