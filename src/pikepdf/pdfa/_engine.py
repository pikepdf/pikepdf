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

import logging
from collections.abc import Mapping
from typing import Any

import pikepdf
from pikepdf.pdfa._context import ValidationContext
from pikepdf.pdfa._flavour import Flavour
from pikepdf.pdfa._report import Deny, Finding, Report
from pikepdf.pdfa._schemas import SchemaSet
from pikepdf.pdfa._walker import DocumentWalker
from pikepdf.pdfa._writemodel import WriteModel
from pikepdf.pdfa._xmp import check_metadata

log = logging.getLogger(__name__)

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
    model = ctx.model
    if model.encrypted(pdf):
        raise Deny(
            Finding(ctx.rule('6.1.3-2', '6.1.3-2'), 'trailer', "file is encrypted")
        )
    if flavour.part == 1 and model.xref_stream(pdf):
        raise Deny(
            Finding(
                ctx.rule('6.1.4-3', None),
                'trailer',
                "cross-reference streams are not permitted in PDF/A-1",
            )
        )
    limit = _MAX_VERSION[flavour.part]
    version = model.version(pdf)
    if _pdf_version(version) > limit:
        raise Deny(
            Finding(
                ctx.rule(None, '6.1.2-1', 'pdf-version'),
                'header',
                f"PDF version {version} exceeds {limit[0]}.{limit[1]}",
                'unsupported' if flavour.part == 1 else 'violation',
            )
        )
    if len(model.objects(pdf)) > MAX_INDIRECT_OBJECTS:
        raise Deny(
            Finding(
                ctx.rule('6.1.12-7', '6.1.13-7'),
                'document',
                f"more than {MAX_INDIRECT_OBJECTS} indirect objects",
            )
        )
    DocumentWalker(ctx, SchemaSet.for_flavour(flavour)).walk()
    check_metadata(ctx)


def run(
    pdf: pikepdf.Pdf,
    flavour: Flavour | str,
    model: WriteModel | None = None,
    *,
    save_kwargs: Mapping[str, Any] | None = None,
) -> Report:
    """Check an open document against a PDF/A flavour.

    The document is not modified. Problems with the document never raise:
    unexpected errors become ``unsupported`` findings with rule id
    ``pikepdf:internal``.

    Args:
        pdf: The document to check.
        flavour: ``'1b'``, ``'2b'`` or ``'3b'``.
        model: What the document looks like once written; by default the
            in-memory document is taken to be what is written.
        save_kwargs: Recorded in ``report.save_kwargs``.

    Returns:
        The report.

    Raises:
        ValueError: If *flavour* is not a supported flavour.
    """
    flavour = Flavour(flavour)
    if model is None:
        model = WriteModel.identity()
    report = Report(flavour, save_kwargs=dict(save_kwargs or {}))
    ctx = ValidationContext(flavour, pdf, report, model)
    try:
        check_document(ctx)
    except Deny as e:
        report.findings.append(e.finding)
    except Exception as e:  # pylint: disable=broad-except
        log.debug("PDF/A validation raised", exc_info=True)
        report.findings.append(
            Finding(
                'pikepdf:internal',
                'document',
                f"{type(e).__name__}: {e}",
                'unsupported',
            )
        )
    if ctx.output_intent_cs is not None:
        report.output_intent = ctx.output_intent_cs.rstrip()
    return report
