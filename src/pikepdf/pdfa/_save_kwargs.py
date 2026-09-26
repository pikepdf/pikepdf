# SPDX-FileCopyrightText: 2026 James R. Barlow
# SPDX-License-Identifier: MPL-2.0

"""Resolve the :meth:`pikepdf.Pdf.save` arguments for a PDF/A flavour."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pikepdf._core import ObjectStreamMode, StreamDecodeLevel
from pikepdf.pdfa._flavour import Flavour

# Pinned for every flavour: key -> (value, reason).
_COMMON_PINS: Mapping[str, tuple[object, str]] = {
    'preserve_pdfa': (True, 'the PDF/A version constraints must be kept'),
    'encryption': (None, 'PDF/A forbids encryption'),
    'qdf': (False, 'QDF mode writes uncompressed, annotated output'),
    'normalize_content': (
        False,
        'it rewrites content streams after the check',
    ),
    'stream_decode_level': (
        StreamDecodeLevel.generalized,
        'the validator evaluates filters as qpdf rewrites them at this level',
    ),
    'fix_metadata_version': (
        False,
        'it rewrites the XMP packet after the check',
    ),
}

# Additionally pinned for PDF/A-1 (ISO 19005-1 is based on PDF 1.4).
_PART1_PINS: Mapping[str, tuple[object, str]] = {
    'object_stream_mode': (
        ObjectStreamMode.disable,
        'PDF/A-1 is based on PDF 1.4, which has no object streams',
    ),
    'force_version': ('1.4', 'PDF/A-1 is based on PDF 1.4'),
}

# User choices and their defaults.
_USER_DEFAULTS: Mapping[str, object] = {
    'compress_streams': True,
    'recompress_flate': False,
    'linearize': False,
    'progress': None,
    'deterministic_id': False,
    'static_id': False,
    'min_version': '',
    'object_stream_mode': ObjectStreamMode.generate,
    'force_version': '',
}

PINNED_KEYS: frozenset[str] = frozenset(_COMMON_PINS)
"""Keys fixed for every flavour; a caller may only pass the pinned value."""

PART1_PINNED_KEYS: frozenset[str] = frozenset(_PART1_PINS)
"""Keys that are user choices for PDF/A-2 and -3 but pinned for PDF/A-1."""

USER_KEYS: frozenset[str] = frozenset(_USER_DEFAULTS)
"""Keys the caller may choose (subject to version limits)."""

_MAX_VERSION = {1: (1, 4), 2: (1, 7), 3: (1, 7)}


def _pins(flavour: Flavour) -> dict[str, tuple[object, str]]:
    pins = dict(_COMMON_PINS)
    if flavour.part == 1:
        pins.update(_PART1_PINS)
    return pins


def describe_pins(flavour: Flavour | str) -> dict[str, str]:
    """Return the keys pinned for ``flavour``, mapped to the reason for each."""
    return {k: reason for k, (_v, reason) in _pins(Flavour(flavour)).items()}


def _parse_version(key: str, value: object) -> tuple[int, int] | None:
    """Return ``(major, minor)`` for a version argument, or None if empty."""
    if isinstance(value, tuple):
        if (
            len(value) != 2
            or not isinstance(value[0], str)
            or not isinstance(value[1], int)
        ):
            raise ValueError(f"{key}={value!r} is not a valid PDF version")
        if value[1] != 0:
            raise ValueError(
                f"{key}={value!r}: extension levels are not supported, because "
                "they add /Extensions, which the PDF/A validator does not cover"
            )
        text = value[0]
    elif isinstance(value, str):
        text = value
    else:
        raise ValueError(f"{key}={value!r} is not a valid PDF version")
    if text == '':
        return None
    parts = text.split('.')
    if len(parts) != 2 or not all(p.isdigit() for p in parts):
        raise ValueError(f"{key}={value!r} is not a valid PDF version")
    return int(parts[0]), int(parts[1])


def _is_pinned_value(key: str, pinned: object, value: object) -> bool:
    if key == 'encryption':
        return value is None or value is False
    if key == 'force_version':
        return value == pinned or value == (pinned, 0)
    if isinstance(pinned, bool):
        return value is pinned
    return value == pinned


def resolve_save_kwargs(flavour: Flavour | str, **user: Any) -> dict[str, Any]:
    """Return the complete :meth:`pikepdf.Pdf.save` keyword arguments for PDF/A.

    Settings that could make the written file differ from what the validator
    checked, or that PDF/A forbids, are pinned; passing a pinned key with its
    pinned value is allowed, any other value raises :class:`ValueError`. The
    remaining settings are the caller's choice, with defaults. The result
    is the complete set of keyword arguments for :meth:`pikepdf.Pdf.save`,
    including ``progress`` and ``linearize``, so
    ``pdf.save(path, **resolve_save_kwargs('2b'))`` works directly. Pass
    your own choices into ``resolve_save_kwargs`` (for example
    ``resolve_save_kwargs('2b', linearize=True, progress=callback)``) rather
    than merging them into the result afterwards, so that they are checked
    against the flavour. The destination is not included.

    Raises:
        TypeError: A keyword is not an argument of :meth:`pikepdf.Pdf.save`.
        ValueError: A pinned setting conflicts, or a version is invalid or
            too high for the flavour.
    """
    flavour = Flavour(flavour)
    for key in user:
        if key not in PINNED_KEYS and key not in USER_KEYS:
            raise TypeError(
                f"resolve_save_kwargs() got an unexpected keyword argument '{key}'"
            )

    pins = _pins(flavour)
    for key, (pinned, reason) in pins.items():
        if key in user and not _is_pinned_value(key, pinned, user[key]):
            raise ValueError(
                f"{key}={user[key]!r} is not allowed for PDF/A-{flavour}: "
                f"it must be {pinned!r} because {reason}"
            )

    limit = _MAX_VERSION[flavour.part]
    for key in ('min_version', 'force_version'):
        if key in user and key not in pins:
            parsed = _parse_version(key, user[key])
            if parsed is not None and parsed > limit:
                raise ValueError(
                    f"{key}={user[key]!r} is not allowed for PDF/A-{flavour}: "
                    f"the version must not exceed {limit[0]}.{limit[1]}"
                )

    result: dict[str, Any] = dict(_USER_DEFAULTS)
    result.update({k: v for k, (v, _reason) in pins.items()})
    result.update(user)
    return result
