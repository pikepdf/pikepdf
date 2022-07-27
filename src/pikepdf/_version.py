# SPDX-FileCopyrightText: 2022 James R. Barlow
# SPDX-License-Identifier: MPL-2.0

from __future__ import annotations

try:
    from importlib_metadata import version as _package_version  # type: ignore
except ImportError:
    from importlib.metadata import version as _package_version

__version__ = _package_version('pikepdf')

__all__ = ['__version__']
