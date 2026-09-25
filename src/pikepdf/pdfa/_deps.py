# SPDX-FileCopyrightText: 2026 James R. Barlow
# SPDX-License-Identifier: MPL-2.0

"""Check that the optional dependencies of pikepdf.pdfa are installed."""

from __future__ import annotations

from importlib.util import find_spec

_REQUIRED = ('jsonschema', 'referencing', 'fontTools')


def require() -> None:
    """Raise ImportError if an optional dependency of pikepdf.pdfa is missing."""
    missing = [name for name in _REQUIRED if find_spec(name) is None]
    if missing:
        raise ImportError(
            "pikepdf.pdfa requires jsonschema>=4.18, referencing and "
            "fonttools>=4.40; install them with: pip install 'pikepdf[pdfa]' "
            f"(missing: {', '.join(missing)})",
            name=missing[0],
        )
