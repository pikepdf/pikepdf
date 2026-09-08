# SPDX-FileCopyrightText: 2022 James R. Barlow
# SPDX-License-Identifier: MPL-2.0

# Module-level functions bound in src/core/pikepdf.cpp.
# See pikepdf/_core/__init__.pyi for how this stub package is laid out.

# pylint: disable=no-method-argument,unused-argument,no-self-use,too-many-public-methods
# ruff: noqa: D418
# mypy: disable-error-code="misc"

from __future__ import annotations

from collections.abc import Iterable
from typing import Any, Literal

from pikepdf._core._qpdf import Pdf

def _translate_qpdf_logic_error(arg0: str) -> str: ...
def get_decimal_precision() -> int:
    """Set the number of decimal digits to use when converting floats."""

def pdf_doc_to_utf8(pdfdoc: bytes) -> str:
    """Low-level function to convert PDFDocEncoding to UTF-8.

    Use the pdfdoc codec instead of using this directly.
    """

def qpdf_version() -> str: ...
def set_access_default_mmap(mmap: bool) -> bool: ...
def get_access_default_mmap() -> bool: ...
def _set_explicit_conversion_mode(mode: bool) -> bool: ...
def _get_explicit_conversion_mode() -> bool: ...
def _get_effective_explicit_mode() -> bool: ...
def _get_effective_explicit_mode_for(pdf: Pdf) -> bool: ...
def _push_thread_conversion_mode(explicit: bool) -> int: ...
def _pop_thread_conversion_mode(token: int, /) -> None: ...
def set_decimal_precision(prec: int) -> int:
    """Get the number of decimal digits to use when converting floats."""

def utf8_to_pdf_doc(utf8: str, unknown: bytes) -> tuple[bool, bytes]: ...
def _unparse_content_stream(contentstream: Iterable[Any]) -> bytes: ...
def set_flate_compression_level(
    level: Literal[-1, 0, 1, 2, 3, 4, 5, 6, 7, 8, 9],
) -> int:
    """Set compression level whenever Flate compression is used.

    Args:
        level: -1 (default), 0 (no compression), 1 to 9 (increasing compression)
    """
