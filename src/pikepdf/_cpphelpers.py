# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
#
# Copyright (C) 2017, James R. Barlow (https://github.com/jbarlow83/)

"""
Support functions called by the C++ library binding layer. Not intended to be
called from Python, and subject to change at any time.
"""

from typing import Callable, Dict, Union
from warnings import warn

from pikepdf import Dictionary, Name, Pdf


def update_xmp_pdfversion(pdf: Pdf, version: str) -> None:

    if Name.Metadata not in pdf.Root:
        return  # Don't create an empty XMP object just to store the version

    with pdf.open_metadata(set_pikepdf_as_editor=False, update_docinfo=False) as meta:
        if 'pdf:PDFVersion' in meta:
            meta['pdf:PDFVersion'] = version


def _alpha(n: int) -> str:
    """Excel-style column numbering A..Z, AA..AZ..BA..ZZ.., AAA."""
    if n < 1:
        raise ValueError(f"Can't represent {n} in alphabetic numbering")
    p = []
    while n > 0:
        n, r = divmod(n - 1, 26)
        p.append(r)
    base = ord('A')
    ords = [(base + v) for v in reversed(p)]
    return ''.join(chr(o) for o in ords)


def _roman(n: int) -> str:
    """Converts integer n to Roman numeral representation as a string."""
    if not (1 <= n <= 5000):
        raise ValueError(f"Can't represent {n} in Roman numerals")
    roman_numerals = (
        (1000, 'M'),
        (900, 'CM'),
        (500, 'D'),
        (400, 'CD'),
        (100, 'C'),
        (90, 'XC'),
        (50, 'L'),
        (40, 'XL'),
        (10, 'X'),
        (9, 'IX'),
        (5, 'V'),
        (4, 'IV'),
        (1, 'I'),
    )
    roman = ""
    for value, numeral in roman_numerals:
        while n >= value:
            roman += numeral
            n -= value
    return roman


LABEL_STYLE_MAP: Dict[Name, Callable[[int], str]] = {
    Name.D: str,
    Name.A: _alpha,
    Name.a: lambda x: _alpha(x).lower(),
    Name.R: _roman,
    Name.r: lambda x: _roman(x).lower(),
}


def label_from_label_dict(label_dict: Union[int, Dictionary]) -> str:
    """Convert a label dictionary returned by QPDF into a text string."""

    if isinstance(label_dict, int):
        return str(label_dict)

    label = ''
    if Name.P in label_dict:
        prefix = label_dict[Name.P]
        label += str(prefix)

    # If there is no S, return only the P portion
    if Name.S in label_dict:
        # St defaults to 1
        numeric_value = label_dict[Name.St] if Name.St in label_dict else 1
        if not isinstance(numeric_value, int):
            warn(
                "Page label dictionary has invalid non-integer start value", UserWarning
            )
            numeric_value = 1

        style = label_dict[Name.S]
        if isinstance(style, Name):
            style_fn = LABEL_STYLE_MAP[style]
            value = style_fn(numeric_value)
            label += value
        else:
            warn("Page label dictionary has invalid page label style", UserWarning)

    return label
