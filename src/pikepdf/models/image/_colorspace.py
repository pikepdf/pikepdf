# SPDX-FileCopyrightText: 2022 James R. Barlow
# SPDX-License-Identifier: MPL-2.0

"""Colour-space interpretation for PDF images.

These functions translate a PDF image's ``/ColorSpace`` (and related metadata)
into the Pillow ``mode``, palette, default ``/Decode`` array, and ICC profile.
Each takes the image (``pim``) and reads its metadata through the *properties*
(``pim.colorspace``, ``pim.indexed``, ``pim._colorspaces``, ...), never by
re-deriving from ``pim.obj``. That "image as protocol" seam is what lets the
:class:`PdfJpxImage` and :class:`PdfInlineImage` metadata overrides flow through
unchanged: the property the function reads is the overridden one.
"""

from __future__ import annotations

from io import BytesIO
from typing import TYPE_CHECKING, cast

from pikepdf.models import _cal_icc
from pikepdf.models._image_exceptions import UnsupportedImageTypeError
from pikepdf.models.image._shared import (
    DecodeArray,
    PaletteData,
    _ensure_list,
)
from pikepdf.objects import Dictionary

if TYPE_CHECKING:
    from PIL.ImageCms import ImageCmsProfile

    from pikepdf.models.image._classes import PdfImage, PdfImageBase


def decode_array(pim: PdfImageBase) -> DecodeArray:
    """Extract the /Decode array."""
    decode: list = pim._metadata('Decode', _ensure_list, [])
    if decode and len(decode) in (2, 6, 8):
        return cast(DecodeArray, tuple(float(value) for value in decode))

    # Indexed images have a single component (the palette index); their
    # default /Decode maps stored samples across the index range, not the
    # base colour space's range (ISO 32000-2 Table 88). Check this before the
    # colorspace branches, since pim.colorspace reports the *base* space.
    if pim.indexed:
        return (0.0, float((1 << pim.bits_per_component) - 1))

    if pim.colorspace in ('/DeviceGray', '/CalGray'):
        return (0.0, 1.0)
    if pim.colorspace in ('/DeviceRGB', '/CalRGB'):
        return (0.0, 1.0, 0.0, 1.0, 0.0, 1.0)
    if pim.colorspace in ('/DeviceCMYK', '/CalCMYK'):
        return (0.0, 1.0, 0.0, 1.0, 0.0, 1.0, 0.0, 1.0)
    if pim.colorspace == '/Lab':
        amin, amax, bmin, bmax = lab_range(pim)
        return (0.0, 100.0, amin, amax, bmin, bmax)
    if pim.colorspace == '/ICCBased':
        # The default /Decode is the identity for every channel, so its
        # length is the only thing that matters: it equals the profile's
        # component count /N (1=gray, 3=RGB/Lab, 4=CMYK). Read /N directly
        # rather than opening the profile.
        try:
            iccstream = cast(Dictionary, pim._colorspaces[1])
            n = int(iccstream['/N'])
        except (TypeError, KeyError, ValueError, IndexError):
            n = 0
        if n in (1, 3, 4):
            return cast(DecodeArray, (0.0, 1.0) * n)
    if pim.image_mask:
        return (0.0, 1.0)  # Default for image masks; per RM 8.9.6.2

    raise NotImplementedError(
        "Don't how to retrieve default /Decode array for image" + repr(pim)
    )


def lab_range(pim: PdfImageBase) -> tuple[float, float, float, float]:
    """Return the /Lab colour space's (amin, amax, bmin, bmax) Range.

    Defaults to (-100, 100, -100, 100) per ISO 32000-2 Table 64 when the
    colour space does not specify a /Range.
    """
    try:
        lab_dict = cast(Dictionary, pim._colorspaces[1])
        rng = lab_dict.get('/Range')
        if rng is not None:
            amin, amax, bmin, bmax = (float(v) for v in rng)
            return amin, amax, bmin, bmax
    except (AttributeError, KeyError, TypeError, ValueError):
        pass
    return (-100.0, 100.0, -100.0, 100.0)


def colorspace(pim: PdfImageBase) -> str | None:
    """PDF name of the colorspace that best describes this image."""
    if pim.image_mask:
        return None  # Undefined for image masks
    if pim._colorspaces:
        if pim._colorspaces[0] in pim.MAIN_COLORSPACES:
            return pim._colorspaces[0]
        if pim._colorspaces[0] == '/Indexed':
            subspace = pim._colorspaces[1]
            if isinstance(subspace, str) and subspace in pim.MAIN_COLORSPACES:
                return subspace
            if isinstance(subspace, list) and subspace[0] in (
                '/ICCBased',
                '/DeviceN',
                '/CalGray',
                '/CalRGB',
                '/Lab',
            ):
                return subspace[0]
        if pim._colorspaces[0] == '/DeviceN':
            return '/DeviceN'

    raise NotImplementedError(
        "not sure how to get colorspace: " + repr(pim._colorspaces)
    )


def colorspace_has_name(pim: PdfImageBase, name) -> bool:
    """Return True if the (base) colorspace references *name*."""
    try:
        cs = pim._colorspaces
        if cs[0] == '/Indexed' and cs[1][0] == name:
            return True
        if cs[0] == name:
            return True
    except (IndexError, AttributeError, KeyError):
        pass
    return False


def approx_mode_from_icc(pim: PdfImageBase) -> str:
    """Infer the Pillow mode from an ICCBased colorspace's profile."""
    if pim.indexed:
        icc_profile = pim._colorspaces[1][1]
    else:
        icc_profile = pim._colorspaces[1]
    icc_profile_nchannels = int(icc_profile['/N'])

    if icc_profile_nchannels == 1:
        return 'L'

    # Multiple channels, need to open the profile and look. (Pillow's stubs omit
    # ImageCmsProfile.profile and do not narrow the Optional; both exist/hold at
    # runtime in this ICCBased, multi-channel context.)
    mode_from_xcolor_space = {'RGB ': 'RGB', 'CMYK': 'CMYK'}
    xcolor_space = pim.icc.profile.xcolor_space  # type: ignore[union-attr]
    return mode_from_xcolor_space.get(xcolor_space, '')


def mode(pim: PdfImageBase) -> str:
    """``PIL.Image.mode`` equivalent for this image, where possible.

    If an ICC profile is attached to the image, we still attempt to resolve a Pillow
    mode.
    """
    m = ''
    if pim.is_device_n:
        m = 'DeviceN'
    elif pim.is_separation:
        m = 'Separation'
    elif pim.indexed:
        m = 'P'
    elif pim.colorspace in ('/DeviceGray', '/CalGray') and pim.bits_per_component == 1:
        m = '1'
    elif pim.colorspace in ('/DeviceGray', '/CalGray') and pim.bits_per_component == 16:
        m = 'I;16'
    elif pim.colorspace in ('/DeviceGray', '/CalGray') and pim.bits_per_component > 1:
        m = 'L'
    elif pim.colorspace in ('/DeviceRGB', '/CalRGB'):
        m = 'RGB'
    elif pim.colorspace in ('/DeviceCMYK', '/CalCMYK'):
        m = 'CMYK'
    elif pim.colorspace == '/Lab':
        m = 'LAB'
    elif pim.colorspace == '/ICCBased':
        try:
            m = approx_mode_from_icc(pim)
        except (ValueError, TypeError) as e:
            raise NotImplementedError(
                "Not sure how to handle PDF image of this type"
            ) from e
    if m == '':
        raise NotImplementedError(
            "Not sure how to handle PDF image of this type"
        ) from None
    return m


def palette(pim: PdfImageBase) -> PaletteData | None:
    """Retrieve the color palette for this image if applicable."""
    if not pim.indexed:
        return None
    try:
        _idx, base, _hival, lookup = pim._colorspaces
    except ValueError as e:
        raise ValueError('Not sure how to interpret this palette') from e
    if pim.icc or pim.is_device_n or pim.is_separation or isinstance(base, list):
        base = str(base[0])
    else:
        base = str(base)
    lookup = bytes(lookup)
    if base not in pim.MAIN_COLORSPACES and base not in pim.PRINT_COLORSPACES:
        raise NotImplementedError(f"not sure how to interpret this palette: {base}")
    if base in ('/DeviceRGB', '/CalRGB'):
        base = 'RGB'
    elif base in ('/DeviceGray', '/CalGray'):
        base = 'L'
    elif base == '/DeviceCMYK':
        base = 'CMYK'
    elif base == '/DeviceN':
        base = 'DeviceN'
    elif base == '/Separation':
        base = 'Separation'
    elif base == '/ICCBased':
        base = approx_mode_from_icc(pim)
    else:
        raise NotImplementedError(f"not sure how to interpret this palette: {base}")
    return PaletteData(base, lookup)


def iccstream(pim: PdfImage):
    """Locate the ICC profile stream within an ICCBased colorspace."""
    if pim.colorspace == '/ICCBased':
        if not pim.indexed:
            return pim._colorspaces[1]
        assert isinstance(pim._colorspaces[1], list)
        return pim._colorspaces[1][1]
    raise NotImplementedError("Don't know how to find ICC stream for image")


def icc(pim: PdfImage) -> ImageCmsProfile | None:
    """If an ICC profile is attached, return a Pillow object that describes it.

    Most of the information may be found in ``icc.profile``. Caches the result on
    ``pim._icc``.
    """
    if pim.colorspace not in ('/ICCBased', '/Indexed'):
        return None
    if not pim._icc:
        iccstream_ = pim._iccstream
        iccbuffer = iccstream_.get_stream_buffer()
        iccbytesio = BytesIO(iccbuffer)
        try:
            from PIL.ImageCms import ImageCmsProfile

            pim._icc = ImageCmsProfile(iccbytesio)
        except OSError as e:
            if str(e) == 'cannot open profile from string':
                # ICC profile is corrupt
                raise UnsupportedImageTypeError(
                    "ICC profile corrupt or not readable"
                ) from e
    return pim._icc


def synthesize_cal_icc(pim: PdfImage) -> bytes | None:
    """Build an ICC profile from CalRGB/CalGray parameters, if possible.

    The Cal* parameters (WhitePoint, Gamma, Matrix) describe a calibrated
    colour space. pikepdf decodes the samples as the device equivalent and
    attaches this profile so the calibration is preserved for downstream
    consumers. Returns None for non-Cal*, indexed, or malformed (no
    WhitePoint) images.
    """
    if pim.indexed or pim.colorspace not in ('/CalRGB', '/CalGray'):
        return None
    try:
        cal = cast(Dictionary, pim._colorspaces[1])
        white = cal.get('/WhitePoint')
        if white is None:
            return None
        white_point = tuple(float(v) for v in white)
        if len(white_point) != 3:
            return None
        if pim.colorspace == '/CalGray':
            gamma = float(cal.get('/Gamma', 1.0))
            return _cal_icc.build_calgray_icc(white_point, gamma)
        gamma_rgb = tuple(float(v) for v in cal.get('/Gamma', [1.0, 1.0, 1.0]))
        matrix = [float(v) for v in cal.get('/Matrix', [1, 0, 0, 0, 1, 0, 0, 0, 1])]
        return _cal_icc.build_calrgb_icc(white_point, gamma_rgb, matrix)
    except (AttributeError, KeyError, TypeError, ValueError):
        return None
