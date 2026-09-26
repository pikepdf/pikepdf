# SPDX-FileCopyrightText: 2026 James R. Barlow
# SPDX-License-Identifier: MPL-2.0

"""Shared state for one validation run."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import pikepdf
from pikepdf.pdfa._flavour import Flavour
from pikepdf.pdfa._report import Finding, FindingKind, Report
from pikepdf.pdfa._writemodel import WriteModel

if TYPE_CHECKING:
    from pikepdf.pdfa._fonts import FontInfo

MAX_DEPTH = 64
MAX_INSTRUCTIONS = 20_000_000

# Form XObject objgen, text rendering mode, id() of the current FontInfo and
# overprint state
FormKey = tuple[tuple[int, int], int, int | None, tuple[bool, bool, int]]


@dataclass
class ValidationContext:
    """State shared by the checks of one validation run.

    Attributes:
        flavour: The PDF/A flavour being checked.
        pdf: The open candidate file.
        report: Findings are appended here.
        model: What the document looks like once written.
        output_intent_cs: ICC colour space signature of the PDF/A OutputIntent
            profile (``'RGB '``, ``'CMYK'`` or ``'GRAY'``), once known.
        visited: objgen of every indirect object already checked.
        max_depth: Deepest nesting of the object graph the walker follows.
        fonts: `FontInfo` of every indirect font reached, by objgen.
        direct_fonts: `FontInfo` of direct font dictionaries reached.
        forms: For each Form XObject walked, keyed by (objgen, text rendering
            mode, font objgen), the deepest q nesting it reached.
        icc_profiles: For each ICCBased profile stream checked, by objgen, its
            number of components, or None if it was denied.
        instructions: Content stream instructions checked so far.
        max_instructions: Budget of content stream instructions.
    """

    flavour: Flavour
    pdf: pikepdf.Pdf
    report: Report
    model: WriteModel = field(default_factory=WriteModel.identity)
    output_intent_cs: str | None = None
    visited: set[tuple[int, int]] = field(default_factory=set)
    max_depth: int = MAX_DEPTH
    fonts: dict[tuple[int, int], FontInfo] = field(default_factory=dict)
    direct_fonts: list[FontInfo] = field(default_factory=list)
    forms: dict[FormKey, int] = field(default_factory=dict)
    icc_profiles: dict[tuple[int, int], int | None] = field(default_factory=dict)
    instructions: int = 0
    max_instructions: int = MAX_INSTRUCTIONS

    @staticmethod
    def describe(obj: object) -> str:
        """Describe where an object lives: ``obj 12 0`` or ``direct``."""
        if isinstance(obj, pikepdf.Object) and obj.is_indirect:
            num, gen = obj.objgen
            return f'obj {num} {gen}'
        return 'direct'

    def rule(self, part1: str | None, part23: str | None, local: str = 'policy') -> str:
        """Return the rule id for the current flavour; see `Flavour.rule`."""
        return self.flavour.rule(part1, part23, local)

    def deny(
        self,
        rule_id: str,
        obj: str | pikepdf.Object,
        message: str,
        kind: FindingKind = 'violation',
    ) -> None:
        """Record a finding.

        Args:
            rule_id: Rule id of the finding.
            obj: A pikepdf object (described with `describe`) or a string
                that already describes the location.
            message: What was wrong.
            kind: ``violation`` or ``unsupported``.
        """
        where = obj if isinstance(obj, str) else self.describe(obj)
        self.report.findings.append(Finding(rule_id, where, message, kind))
