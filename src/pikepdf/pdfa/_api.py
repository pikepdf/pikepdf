# SPDX-FileCopyrightText: 2026 James R. Barlow
# SPDX-License-Identifier: MPL-2.0

"""Entry points of the PDF/A validator."""

from __future__ import annotations

import logging
from pathlib import Path

import pikepdf
from pikepdf.pdfa._context import ValidationContext
from pikepdf.pdfa._engine import check_document
from pikepdf.pdfa._flavour import Flavour
from pikepdf.pdfa._report import Deny, Finding, ValidationReport

log = logging.getLogger(__name__)


def validate_written(
    input_file: Path | str, flavour: Flavour | str
) -> ValidationReport:
    """Validate a saved PDF/A candidate file.

    Problems with the file never raise: unexpected errors become
    ``unsupported`` findings with rule id ``pikepdf:internal``.

    Args:
        input_file: The saved candidate file.
        flavour: ``'1b'``, ``'2b'`` or ``'3b'``.

    Returns:
        The report; ``report.passed`` is True if the file is approved.

    Raises:
        ValueError: If *flavour* is not a supported flavour.
    """
    flavour = Flavour(flavour)
    report = ValidationReport(flavour)
    try:
        # Keep inherited page attributes where they are: pikepdf would
        # otherwise copy them into each page, hiding page-tree inheritance.
        with (
            pikepdf.open(input_file, inherit_page_attributes=False) as pdf,
            pikepdf.implicit_conversion(),
        ):
            check_document(ValidationContext(flavour, pdf, report))
    except Deny as e:
        report.findings.append(e.finding)
    except Exception as e:  # pylint: disable=broad-except
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
