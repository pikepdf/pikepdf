# SPDX-FileCopyrightText: 2026 James R. Barlow
# SPDX-License-Identifier: MPL-2.0

"""Document-level checks and the entry point into the object walk.

The validator approves a file only if every construct it encounters is
recognized and known to conform. Anything it does not recognize is reported
as a finding, so a denial may be a false alarm but an approval should never be.
File-level syntax (header, cross-reference table, stream lengths) is trusted
because the files it checks are freshly written by qpdf.
"""

from __future__ import annotations

import pikepdf
from pikepdf.pdfa._context import ValidationContext
from pikepdf.pdfa._report import Deny, Finding
from pikepdf.pdfa._schemas import SchemaSet
from pikepdf.pdfa._walker import DocumentWalker
from pikepdf.pdfa._xmp import check_metadata

MAX_INDIRECT_OBJECTS = 8_388_607
_MAX_VERSION = {1: (1, 4), 2: (1, 7), 3: (1, 7)}


def _pdf_version(version: str) -> tuple[int, int]:
    major, _, minor = version.partition('.')
    return int(major), int(minor or 0)


def check_document(ctx: ValidationContext) -> None:
    """Check the whole document, adding findings to ``ctx.report``.

    Raises:
        Deny: If a finding makes further checks pointless.
    """
    pdf = ctx.pdf
    flavour = ctx.flavour
    if pdf.is_encrypted:
        raise Deny(
            Finding(ctx.rule('6.1.3-2', '6.1.3-2'), 'trailer', "file is encrypted")
        )
    if flavour.part == 1 and pdf.trailer.get('/Type') == pikepdf.Name.XRef:
        raise Deny(
            Finding(
                ctx.rule('6.1.4-3', None),
                'trailer',
                "cross-reference streams are not permitted in PDF/A-1",
            )
        )
    limit = _MAX_VERSION[flavour.part]
    if _pdf_version(pdf.pdf_version) > limit:
        raise Deny(
            Finding(
                ctx.rule(None, '6.1.2-1', 'pdf-version'),
                'header',
                f"PDF version {pdf.pdf_version} exceeds {limit[0]}.{limit[1]}",
                'unsupported' if flavour.part == 1 else 'violation',
            )
        )
    if len(pdf.objects) > MAX_INDIRECT_OBJECTS:
        raise Deny(
            Finding(
                ctx.rule('6.1.12-7', '6.1.13-7'),
                'document',
                f"more than {MAX_INDIRECT_OBJECTS} indirect objects",
            )
        )
    DocumentWalker(ctx, SchemaSet.for_flavour(flavour)).walk()
    check_metadata(ctx)
