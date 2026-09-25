# SPDX-FileCopyrightText: 2026 James R. Barlow
# SPDX-License-Identifier: MPL-2.0

"""Simple-font encodings: character code to glyph name tables.

The tables are built from ``_latin_enc.ENCODING`` (vendored from
pdfminer.six; ISO 32000-1 Annex D), whose rows are
``(name, standard, mac_roman, win_ansi, pdf_doc)``.
"""

from __future__ import annotations

from collections.abc import Mapping
from functools import cache
from types import MappingProxyType
from typing import Any

import pikepdf
from pikepdf.pdfa._latin_enc import ENCODING
from pikepdf.pdfa._shallow import pdf_repr

STANDARD = 'StandardEncoding'
MAC_ROMAN = 'MacRomanEncoding'
WIN_ANSI = 'WinAnsiEncoding'
PDF_DOC = 'PDFDocEncoding'

_COLUMNS = {STANDARD: 1, MAC_ROMAN: 2, WIN_ANSI: 3, PDF_DOC: 4}

# Codes that Annex D lists under two names. The footnotes of Table D.2 say
# these are additional encodings of SPACE and HYPHEN.
_PREFERRED = {
    (MAC_ROMAN, 202): 'space',
    (WIN_ANSI, 160): 'space',
    (WIN_ANSI, 173): 'hyphen',
}

MAX_CODE = 255


@cache
def encoding_table(name: str) -> Mapping[int, str]:
    """Return the code to glyph name table of a standard encoding.

    Args:
        name: ``StandardEncoding``, ``MacRomanEncoding``, ``WinAnsiEncoding``
            or ``PDFDocEncoding`` (without the leading slash).

    Raises:
        KeyError: If the encoding is not one of these.
    """
    column = _COLUMNS[name]
    table: dict[int, str] = {}
    for row in ENCODING:
        code: Any = row[column]
        if code is None:
            continue
        table.setdefault(int(code), str(row[0]))
    for (encoding, code), glyph in _PREFERRED.items():
        if encoding == name:
            table[code] = glyph
    return MappingProxyType(table)


@cache
def mac_roman_codes() -> Mapping[str, int]:
    """Return the inverse of MacRomanEncoding: glyph name to (lowest) code."""
    inverse: dict[str, int] = {}
    for code, glyph in sorted(encoding_table(MAC_ROMAN).items()):
        inverse.setdefault(glyph, code)
    for row in ENCODING:
        mac_code: Any = row[_COLUMNS[MAC_ROMAN]]
        if mac_code is not None:
            inverse.setdefault(str(row[0]), int(mac_code))
    return MappingProxyType(inverse)


class DifferencesError(ValueError):
    """A /Differences array is malformed."""


def parse_differences(differences: Any) -> dict[int, str]:
    """Parse a /Differences array into a code to glyph name mapping.

    Args:
        differences: The /Differences value: an array of integers, each
            followed by one or more names for consecutive codes.

    Returns:
        The glyph name for each code the array assigns.

    Raises:
        DifferencesError: If the value is not an array, starts with a name,
            contains anything other than integers and names, or assigns a
            code outside 0..255.
    """
    if not isinstance(differences, pikepdf.Array):
        raise DifferencesError("/Differences is not an array")
    result: dict[int, str] = {}
    code: int | None = None
    for item in differences:
        number = pikepdf.as_int(item)
        if number is not None:
            code = number
            continue
        if isinstance(item, pikepdf.Name):
            if code is None:
                raise DifferencesError("/Differences starts with a name")
            if not 0 <= code <= MAX_CODE:
                raise DifferencesError(f"/Differences assigns code {code}")
            try:
                glyph = str(item)[1:]
            except UnicodeDecodeError as e:
                raise DifferencesError("/Differences name is not UTF-8") from e
            result[code] = glyph
            code += 1
            continue
        raise DifferencesError(
            f"/Differences contains {pdf_repr(item)}, not an integer or name"
        )
    return result


def apply_differences(base: Mapping[int, str], differences: Any) -> dict[int, str]:
    """Return *base* overlaid with the assignments of a /Differences array.

    Raises:
        DifferencesError: See `parse_differences`.
    """
    result = dict(base)
    result.update(parse_differences(differences))
    return result
