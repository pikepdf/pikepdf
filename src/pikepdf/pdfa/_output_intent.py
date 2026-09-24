# SPDX-FileCopyrightText: 2026 James R. Barlow
# SPDX-License-Identifier: MPL-2.0

"""PDF/A output intents."""

from __future__ import annotations

from pikepdf import Array, Dictionary, Name, Pdf, Stream
from pikepdf.pdfa._catalogue import data_file

SRGB_ICC_PROFILE_NAME = 'sRGB.icc'


def load_srgb() -> bytes:
    """Load the sRGB ICC profile from package data."""
    return data_file(SRGB_ICC_PROFILE_NAME).read_bytes()


def add_srgb_output_intent(pdf: Pdf) -> None:
    """Make an sRGB PDF/A output intent the document's only output intent.

    Equivalent to `replace_output_intents`: existing output intents (such as
    a PDF/X intent with a CMYK profile) are discarded, since PDF/A requires
    every output intent to share one destination profile.

    Args:
        pdf: An open pikepdf.Pdf object
    """
    replace_output_intents(pdf)


def replace_output_intents(pdf: Pdf) -> None:
    """Replace the catalog's /OutputIntents with a single sRGB PDF/A intent.

    The new intent is a GTS_PDFA1 OutputIntent whose destination profile is
    the sRGB ICC profile shipped with pikepdf. An output intent of another
    kind or with another profile cannot be kept, because PDF/A requires all
    output intents to use the same profile.

    Args:
        pdf: An open pikepdf.Pdf object
    """
    icc_stream = Stream(pdf, load_srgb())
    icc_stream[Name.N] = 3  # RGB has 3 components
    output_intent = Dictionary(
        {
            '/Type': Name.OutputIntent,
            '/S': Name('/GTS_PDFA1'),
            '/OutputConditionIdentifier': 'sRGB',
            '/DestOutputProfile': icc_stream,
        }
    )
    pdf.Root[Name.OutputIntents] = Array([pdf.make_indirect(output_intent)])
