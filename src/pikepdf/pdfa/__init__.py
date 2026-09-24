# SPDX-FileCopyrightText: 2026 James R. Barlow
# SPDX-License-Identifier: MPL-2.0

"""Allowlist validator for PDF/A-1b, 2b and 3b files.

The validator approves a file only if every construct it encounters is
recognized and known to conform. Anything it does not recognize is reported
as a finding, so a denial may be a false alarm but an approval should never be.

This module needs optional dependencies; install them with
``pip install 'pikepdf[pdfa]'``.
"""

from __future__ import annotations

from pikepdf.pdfa import _deps

_deps.require()

from pikepdf.pdfa._api import (  # noqa: E402
    check,
    save,
    validate_written,
)
from pikepdf.pdfa._flavour import Flavour  # noqa: E402
from pikepdf.pdfa._prepare import PrepareResult, prepare  # noqa: E402
from pikepdf.pdfa._report import (  # noqa: E402
    Finding,
    PdfaError,
    Report,
    ValidationReport,
)
from pikepdf.pdfa._save_kwargs import resolve_save_kwargs  # noqa: E402

__all__ = [
    'Finding',
    'Flavour',
    'PdfaError',
    'PrepareResult',
    'Report',
    'ValidationReport',
    'check',
    'prepare',
    'resolve_save_kwargs',
    'save',
    'validate_written',
]
