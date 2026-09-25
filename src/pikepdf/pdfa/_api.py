# SPDX-FileCopyrightText: 2026 James R. Barlow
# SPDX-License-Identifier: MPL-2.0

"""Entry points of the PDF/A validator."""

from __future__ import annotations

import logging
import os
import shutil
import tempfile
from collections.abc import Mapping
from os import PathLike
from pathlib import Path
from typing import Any, BinaryIO, cast

import pikepdf
from pikepdf import Pdf
from pikepdf._io import (
    atomic_write_verified,
    check_different_files,
    check_stream_is_usable,
)
from pikepdf.pdfa import _engine
from pikepdf.pdfa._flavour import Flavour
from pikepdf.pdfa._prepare import PrepareResult, prepare
from pikepdf.pdfa._report import Finding, PdfaError, Report
from pikepdf.pdfa._save_kwargs import resolve_save_kwargs
from pikepdf.pdfa._writemodel import WriteModel

log = logging.getLogger(__name__)


@pikepdf.explicit_conversion()
def check(pdf: Pdf, flavour: Flavour | str, **user_save_kwargs: Any) -> Report:
    """Check an open document against a PDF/A flavour as it would be saved.

    The check evaluates the file that ``pdf.save(path,
    **report.save_kwargs)`` would write: the stream filters qpdf rewrites,
    the trailer, the PDF version and the objects written (orphaned objects
    are not written, so they are not checked). Nothing is written and the
    document is not modified.

    ``check`` is pure and cheap. It describes the document at the moment of
    the call, so run it after the last metadata edit. It is advisory:
    ``save`` is the only call that promises anything, because it validates
    the bytes it writes.

    Problems with the document never raise: unexpected errors become
    ``unsupported`` findings with rule id ``pikepdf:internal``.

    Args:
        pdf: The document to check.
        flavour: ``'1b'``, ``'2b'`` or ``'3b'``.
        **user_save_kwargs: `pikepdf.Pdf.save` settings the caller intends
            to use, as accepted by `resolve_save_kwargs`.

    Returns:
        The report; ``report.save_kwargs`` holds the complete settings the
        verdict assumes.

    Raises:
        ValueError: If *flavour* is not a supported flavour, or a save
            setting conflicts with the flavour.
        TypeError: If a keyword is not a supported save setting.
    """
    flavour = Flavour(flavour)
    kw = resolve_save_kwargs(flavour, **user_save_kwargs)
    return _engine.run(pdf, flavour, WriteModel.predict(pdf, kw), save_kwargs=kw)


@pikepdf.explicit_conversion()
def validate_written(
    input_file: Path | str | BinaryIO,
    flavour: Flavour | str,
    save_kwargs: Mapping[str, Any] | None = None,
) -> Report:
    """Validate a saved PDF/A candidate file.

    Problems with the file never raise: unexpected errors become
    ``unsupported`` findings with rule id ``pikepdf:internal``.

    Args:
        input_file: The saved candidate file, or a seekable binary stream
            holding it.
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


_NO_ORIGINAL_FILENAME = (
    "Cannot save to original filename because the original file was "
    "not opening using Pdf.open(..., allow_overwriting_input=True). "
    "Either specify a new destination filename/file stream or open "
    "with allow_overwriting_input=True. If this Pdf was created using "
    "Pdf.new(), you must specify a destination object since there is "
    "no original filename to save to."
)


def _require_pass(report: Report) -> None:
    if report.verdict != 'pass':
        raise PdfaError(report)


def save(
    pdf: Pdf,
    filename_or_stream: Path | str | bytes | PathLike | BinaryIO | None,
    flavour: Flavour | str,
    *,
    output_intent: str | bytes | None = 'sRGB',
    output_condition_identifier: str | None = None,
    repair: bool = True,
    **user_save_kwargs: Any,
) -> Report:
    """Prepare a document for PDF/A, write it, and validate what was written.

    ``save`` is the only call that promises anything: it reopens the file it
    wrote and validates it, so a returned report always describes the bytes
    at the destination. The cost is one extra parse of the output.

    The steps are:

    1. Resolve the save settings with `resolve_save_kwargs`. A conflicting
       setting raises before the document is changed.
    2. If *repair* is True, run `prepare` on *pdf*. This modifies the
       in-memory document (output intents, metadata, annotations and so on);
       the changes remain whether or not the save succeeds. If *repair* is
       False, nothing is repaired, and the caller is responsible for making
       the document conform.
    3. Write the document to a temporary file and validate it. Only a
       ``'pass'`` verdict is accepted; ``'fail'`` and ``'not_checked'`` both
       raise `PdfaError`.
    4. Move the verified file into place (for a path), or copy its bytes into
       the stream.

    A failed save leaves an existing destination file untouched, and does not
    create a new one. A stream destination is written only on success.

    Args:
        pdf: The document to save.
        filename_or_stream: A path or a seekable, writable binary stream. If
            None, the document is saved over the file it was opened from,
            which requires ``pikepdf.open(..., allow_overwriting_input=True)``,
            as for `pikepdf.Pdf.save`.
        flavour: ``'1b'``, ``'2b'`` or ``'3b'``.
        output_intent: Passed to `prepare`.
        output_condition_identifier: Passed to `prepare`.
        repair: If True, run `prepare` before writing.
        **user_save_kwargs: `pikepdf.Pdf.save` settings, as accepted by
            `resolve_save_kwargs`.

    Returns:
        The report on the written file; it passed. ``report.save_kwargs``
        holds the settings used and ``report.prepared`` the `PrepareResult`
        (None if *repair* is False).

    Raises:
        PdfaError: If the written file did not pass; ``e.report`` explains
            why, and ``e.report.prepared`` holds the `PrepareResult` as for
            a successful save. Nothing was written to the destination.
        ValueError: If *flavour* is not a supported flavour, a save setting
            conflicts with the flavour, the output intent is invalid, or the
            destination is the input file and overwriting it was not allowed.
        TypeError: If a keyword is not a supported save setting, or the
            destination is not a path or binary stream.
    """
    flavour = Flavour(flavour)
    kw = resolve_save_kwargs(flavour, **user_save_kwargs)

    destination = filename_or_stream
    original = getattr(pdf, '_original_filename', None)
    if destination is None:
        if not original:
            raise ValueError(_NO_ORIGINAL_FILENAME)
        destination = original
    stream: BinaryIO | None = None
    path: Path | None = None
    if hasattr(destination, 'seek'):
        stream = cast(BinaryIO, destination)
        check_stream_is_usable(stream)
    elif isinstance(destination, str | bytes | PathLike):
        path = Path(os.fsdecode(destination))
        if not getattr(pdf, '_tmp_stream', None) and original is not None:
            check_different_files(original, path)
    else:
        raise TypeError("expected str, bytes or os.PathLike object")

    prepared: PrepareResult | None = None
    if repair:
        prepared = prepare(
            pdf,
            flavour,
            output_intent=output_intent,
            output_condition_identifier=output_condition_identifier,
        )

    try:
        if stream is not None:
            report = _save_to_stream(pdf, stream, flavour, kw)
        else:
            assert path is not None
            report = _save_to_path(pdf, path, flavour, kw)
    except PdfaError as e:
        e.report.prepared = prepared
        raise
    report.prepared = prepared
    return report


def _save_to_path(pdf: Pdf, path: Path, flavour: Flavour, kw: dict[str, Any]) -> Report:
    reports: list[Report] = []

    def verify(tmp: Path) -> None:
        # validate_written closes the Pdf it opens before returning, so the
        # temporary file can be replaced on Windows.
        report = validate_written(tmp, flavour, save_kwargs=kw)
        reports.append(report)
        _require_pass(report)

    with atomic_write_verified(path, verify) as tmp_stream:
        pdf.save(cast(BinaryIO, tmp_stream), **kw)
    return reports[-1]


def _save_to_stream(
    pdf: Pdf, stream: BinaryIO, flavour: Flavour, kw: dict[str, Any]
) -> Report:
    with tempfile.TemporaryFile() as tf:
        pdf.save(tf, **kw)
        tf.seek(0)
        report = validate_written(cast(BinaryIO, tf), flavour, save_kwargs=kw)
        _require_pass(report)
        tf.seek(0)
        shutil.copyfileobj(tf, stream)
    return report
