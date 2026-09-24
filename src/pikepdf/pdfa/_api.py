# SPDX-FileCopyrightText: 2026 James R. Barlow
# SPDX-License-Identifier: MPL-2.0

"""Entry points of the PDF/A validator."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pikepdf
from pikepdf import Pdf
from pikepdf.pdfa import _engine
from pikepdf.pdfa._declare import declare_pdfa_metadata
from pikepdf.pdfa._flavour import Flavour
from pikepdf.pdfa._output_intent import replace_output_intents
from pikepdf.pdfa._repair import (
    add_cidsets_for_subset_cidfonts,
    repair_annotation_flags,
    strip_image_interpolation,
)
from pikepdf.pdfa._report import Finding, Report

log = logging.getLogger(__name__)


def validate_written(
    input_file: Path | str,
    flavour: Flavour | str,
    save_kwargs: Mapping[str, Any] | None = None,
) -> Report:
    """Validate a saved PDF/A candidate file.

    Problems with the file never raise: unexpected errors become
    ``unsupported`` findings with rule id ``pikepdf:internal``.

    Args:
        input_file: The saved candidate file.
        flavour: ``'1b'``, ``'2b'`` or ``'3b'``.
        save_kwargs: The `pikepdf.Pdf.save` settings the file was written
            with, recorded in ``report.save_kwargs``.

    Returns:
        The report; ``report.passed`` is True if the file is approved.

    Raises:
        ValueError: If *flavour* is not a supported flavour.
    """
    flavour = Flavour(flavour)
    try:
        # Keep inherited page attributes where they are: pikepdf would
        # otherwise copy them into each page, hiding page-tree inheritance.
        with pikepdf.open(input_file, inherit_page_attributes=False) as pdf:
            report = _engine.run(pdf, flavour, save_kwargs=save_kwargs)
    except Exception as e:  # pylint: disable=broad-except
        report = Report(flavour, save_kwargs=dict(save_kwargs or {}))
        report.findings.append(
            Finding(
                'pikepdf:internal',
                str(input_file),
                f"{type(e).__name__}: {e}",
                'unsupported',
            )
        )
    if report.passed:
        log.debug("PDF/A-%s validation passed: %s", flavour.value, input_file)
    return report


validate = validate_written


def convert(
    input_file: Path | str, output_file: Path | str, flavour: Flavour | str
) -> Path:
    """Attempt to convert a PDF to PDF/A by adding and repairing structures.

    The conversion replaces the output intents with an sRGB PDF/A intent,
    removes image interpolation, removes annotations that are hidden or not
    viewable and sets the Print flag on the others, adds the /CIDSet that
    PDF/A-1 requires on subset CIDFonts, rewrites the XMP packet with only
    what PDF/A permits, attaches the local time zone to document dates
    without one, declares PDF/A conformance in XMP, sets the DocInfo entries
    with XMP equivalents from XMP, and saves with the settings of the flavour
    (no object or cross-reference streams for PDF/A-1).

    This works for PDFs that are already mostly PDF/A compliant but lack the
    formal declarations. It does NOT perform color conversion, font
    embedding, or other transformations, so the result must be validated
    before it is used.

    Temporary: Phases 5-8 replace this function with ``resolve_save_kwargs``,
    ``prepare`` and ``save``.

    Args:
        input_file: Path to input PDF
        output_file: Path where output PDF should be written
        flavour: PDF/A flavour, ``'1b'``, ``'2b'`` or ``'3b'``

    Returns:
        Path to the output file

    Raises:
        pikepdf.PdfError: If the PDF cannot be opened or modified
    """
    flavour = Flavour(flavour)
    output_file = Path(output_file)
    with Pdf.open(input_file) as pdf:
        replace_output_intents(pdf)
        strip_image_interpolation(pdf)
        repair_annotation_flags(pdf)
        if flavour.part == 1:
            add_cidsets_for_subset_cidfonts(pdf)
        declare_pdfa_metadata(pdf, flavour)
        pdf.save(output_file, **save_settings(flavour))

    log.debug('Speculative PDF/A conversion complete: %s', output_file)
    return output_file


def save_settings(flavour: Flavour | str) -> dict[str, Any]:
    """Return `pikepdf.Pdf.save` settings for the given flavour.

    Essentially, don't use features that are incompatible with a given
    PDF/A specification.

    Temporary: Phases 5-8 replace this function with ``resolve_save_kwargs``.
    """
    if Flavour(flavour).part == 1:
        # Trigger recompression to ensure object streams are removed, because
        # Acrobat complains about them in PDF/A-1b validation.
        return dict(
            preserve_pdfa=True,
            compress_streams=True,
            stream_decode_level=pikepdf.StreamDecodeLevel.generalized,
            object_stream_mode=pikepdf.ObjectStreamMode.disable,
            force_version='1.4',
        )
    return dict(
        preserve_pdfa=True,
        compress_streams=True,
        object_stream_mode=pikepdf.ObjectStreamMode.generate,
    )
