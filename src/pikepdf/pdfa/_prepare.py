# SPDX-FileCopyrightText: 2026 James R. Barlow
# SPDX-License-Identifier: MPL-2.0

"""Preparing an open document for PDF/A, without changing its content."""

from __future__ import annotations

import logging
from collections import Counter
from dataclasses import dataclass, field

import pikepdf
from pikepdf import Pdf
from pikepdf.pdfa._declare import declare_pdfa_metadata
from pikepdf.pdfa._flavour import Flavour
from pikepdf.pdfa._output_intent import (
    has_output_intent,
    parse_output_intent,
    replace_output_intents,
)
from pikepdf.pdfa._repair import (
    add_cidsets_for_subset_cidfonts,
    describe_removed_annotations,
    repair_annotation_flags,
    strip_image_interpolation,
)

log = logging.getLogger(__name__)


def _plural(count: int, noun: str) -> str:
    return f"{count} {noun}{'' if count == 1 else 's'}"


@dataclass(frozen=True)
class PrepareResult:
    """What `prepare` changed.

    Attributes:
        output_intent_replaced: True if the output intents were replaced.
            False if the requested intent was already the document's only
            output intent, or if the output intents were kept.
        output_intent: The colour space (``'RGB'``, ``'CMYK'`` or
            ``'GRAY'``) of the requested output intent, whether it was
            installed now or already present; None if the document's output
            intents were kept.
        interpolation_removed: The number of images whose /Interpolate
            entry was removed.
        annotations_removed: The number of hidden or non-viewable
            annotations removed, by subtype (without the leading slash).
        annotations_removed_pages: The pages (1-based) annotations were
            removed from.
        print_flags_set: The number of annotations given the Print flag.
        cidsets_added: The number of /CIDSet streams added to subset
            CIDFonts (PDF/A-1 only).
        xmp_dropped: Labels (``prefix:name``) of the XMP properties removed
            because PDF/A does not permit them.
        xmp_unreadable: True if an XMP packet that could not be read was
            replaced.
        xmp_problem: Why the XMP packet could not be read, if
            *xmp_unreadable*; otherwise None.
        dates_zoned: The number of document dates given the local time zone.
        pdfa_declared: True if the metadata did not already declare the
            flavour's PDF/A conformance.
    """

    output_intent_replaced: bool = False
    output_intent: str | None = None
    interpolation_removed: int = 0
    annotations_removed: Counter[str] = field(default_factory=Counter)
    annotations_removed_pages: frozenset[int] = frozenset()
    print_flags_set: int = 0
    cidsets_added: int = 0
    xmp_dropped: tuple[str, ...] = ()
    xmp_unreadable: bool = False
    xmp_problem: str | None = None
    dates_zoned: int = 0
    pdfa_declared: bool = False

    @property
    def changed(self) -> bool:
        """True if `prepare` changed anything but the metadata timestamps.

        `prepare` always records pikepdf as the producer and the time in
        xmp:MetadataDate; that alone does not count as a change.
        """
        return bool(
            self.output_intent_replaced
            or self.interpolation_removed
            or self.annotations_removed
            or self.print_flags_set
            or self.cidsets_added
            or self.xmp_dropped
            or self.xmp_unreadable
            or self.dates_zoned
            or self.pdfa_declared
        )

    def messages(self) -> list[tuple[str, str]]:
        """Return a ``(level, sentence)`` pair for each kind of change made.

        The level suggests how prominently to report the change:
        ``'warning'`` for annotations removed, which discards content;
        ``'info'`` for Print flags set, XMP properties removed and an
        unreadable XMP packet replaced; ``'debug'`` for the rest. It is
        one of the lowercase names of the `logging` levels, so
        ``logging.getLevelName(level.upper())`` gives the level number.
        """
        messages: list[tuple[str, str]] = []
        if self.output_intent_replaced:
            messages.append(
                (
                    'debug',
                    f"Replaced the output intents with a single "
                    f"{self.output_intent} PDF/A output intent",
                )
            )
        if self.interpolation_removed:
            messages.append(
                (
                    'debug',
                    "Removed interpolation from "
                    f"{_plural(self.interpolation_removed, 'image')}, "
                    "which PDF/A does not permit",
                )
            )
        if self.annotations_removed:
            messages.append(
                (
                    'warning',
                    describe_removed_annotations(
                        self.annotations_removed, self.annotations_removed_pages
                    ),
                )
            )
        if self.print_flags_set:
            messages.append(
                (
                    'info',
                    "Set the Print flag on "
                    f"{_plural(self.print_flags_set, 'annotation')}, "
                    "as PDF/A requires",
                )
            )
        if self.cidsets_added:
            messages.append(
                (
                    'debug',
                    "Added a /CIDSet to "
                    f"{_plural(self.cidsets_added, 'subset CIDFont')}, "
                    "as PDF/A-1 requires",
                )
            )
        if self.xmp_unreadable:
            sentence = "Replaced XMP metadata that could not be read"
            if self.xmp_problem:
                sentence += f": {self.xmp_problem}"
            messages.append(('info', sentence))
        if self.xmp_dropped:
            messages.append(
                (
                    'info',
                    "Removed XMP metadata that is not permitted in PDF/A: "
                    + ', '.join(self.xmp_dropped),
                )
            )
        if self.dates_zoned:
            messages.append(
                (
                    'debug',
                    "Assumed the local time zone for "
                    f"{_plural(self.dates_zoned, 'date')} without one",
                )
            )
        if self.pdfa_declared:
            messages.append(('debug', "Declared PDF/A conformance in the XMP metadata"))
        return messages

    def describe(self) -> list[str]:
        """Return one sentence for each kind of change made.

        The sentences of `messages`, without their levels.
        """
        return [sentence for _, sentence in self.messages()]


def prepare(
    pdf: Pdf,
    flavour: Flavour | str,
    *,
    output_intent: bytes | str | None = 'sRGB',
    output_condition_identifier: str | None = None,
) -> PrepareResult:
    """Apply the repairs that make a document acceptable to PDF/A, in memory.

    The repairs change structure and metadata, never page content: the
    output intents are replaced with a single PDF/A output intent, image
    interpolation is removed, hidden or non-viewable annotations are removed
    and the Print flag is set on the others, PDF/A-1 subset CIDFonts are
    given a /CIDSet, and the XMP metadata is rewritten with only what the
    flavour permits and a declaration of PDF/A conformance (level B), with
    the DocInfo entries set to agree with it.

    Calling `prepare` again on the same document makes no further changes
    (except the time recorded in xmp:MetadataDate). The document must still
    be saved with settings suited to the flavour and validated; `prepare`
    does not convert colour, embed fonts or fix page content.

    Args:
        pdf: The document to change.
        flavour: ``'1b'``, ``'2b'`` or ``'3b'``.
        output_intent: ``'sRGB'`` (any case) for the sRGB profile shipped
            with pikepdf, the bytes of an ICC output profile (RGB, CMYK or
            gray; version 2 for PDF/A-1, up to version 4 otherwise), or None
            to keep the document's output intents as they are.
        output_condition_identifier: The /OutputConditionIdentifier of the
            output intent; by default ``'sRGB'`` for the sRGB profile, else
            the profile's description, or ``'Custom'``.

    Returns:
        What was changed.

    Raises:
        ValueError: If *flavour* is not a supported flavour, or
            *output_intent* is not usable. The document is not changed.
        TypeError: If *output_intent* is of the wrong type.
    """
    pdfa_flavour = Flavour(flavour)
    spec = parse_output_intent(
        output_intent, pdfa_flavour, identifier=output_condition_identifier
    )
    with pikepdf.implicit_conversion():
        # Reading the page count makes qpdf correct /Count when saving
        len(pdf.pages)
        replaced = False
        if spec is not None and not has_output_intent(pdf, spec):
            replace_output_intents(pdf, spec)
            replaced = True
        interpolation_removed = strip_image_interpolation(pdf)
        annotations = repair_annotation_flags(pdf)
        cidsets_added = 0
        if pdfa_flavour.part == 1:
            cidsets_added = add_cidsets_for_subset_cidfonts(pdf)
        declaration = declare_pdfa_metadata(pdf, pdfa_flavour)
    return PrepareResult(
        output_intent_replaced=replaced,
        output_intent=spec.colour_space if spec is not None else None,
        interpolation_removed=interpolation_removed,
        annotations_removed=annotations.removed,
        annotations_removed_pages=frozenset(annotations.removed_pages),
        print_flags_set=annotations.print_flags_set,
        cidsets_added=cidsets_added,
        xmp_dropped=declaration.xmp_dropped,
        xmp_unreadable=declaration.xmp_unreadable,
        xmp_problem=declaration.xmp_problem,
        dates_zoned=declaration.dates_zoned,
        pdfa_declared=declaration.pdfa_declared,
    )
