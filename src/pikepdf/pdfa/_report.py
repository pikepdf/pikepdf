# SPDX-FileCopyrightText: 2026 James R. Barlow
# SPDX-License-Identifier: MPL-2.0

"""Validation findings and reports."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, NamedTuple

from pikepdf.pdfa._flavour import Flavour

FindingKind = Literal['violation', 'unsupported']


class Finding(NamedTuple):
    """One reason a file was not approved.

    Attributes:
        rule: veraPDF rule id (``ISO_19005_2:6.2.8-3``),
            ``pikepdf:schema-<role>`` for an unrecognized construct in a schema
            role, ``pikepdf:<name>`` for a local policy, or ``pikepdf:internal``
            for an unexpected error.
        where: Human-readable location, e.g. ``obj 12 0 (Page) /AA``.
        message: What was wrong.
        kind: ``violation`` if the construct breaks PDF/A; ``unsupported`` if
            it may be valid PDF/A but the validator does not check it.
    """

    rule: str
    where: str
    message: str
    kind: FindingKind = 'violation'

    def __str__(self) -> str:
        return f"[{self.kind}] {self.rule} at {self.where}: {self.message}"


@dataclass
class ValidationReport:
    """Result of validating one file against one PDF/A flavour."""

    flavour: Flavour
    findings: list[Finding] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        """True if nothing was found that prevents approval."""
        return not self.findings

    def summary(self, limit: int = 20) -> str:
        """Return a multi-line description of the result."""
        if self.passed:
            return f"PDF/A-{self.flavour.value}: passed"
        lines = [f"PDF/A-{self.flavour.value}: {len(self.findings)} finding(s)"]
        lines.extend(f"  {finding}" for finding in self.findings[:limit])
        if len(self.findings) > limit:
            lines.append(f"  ... and {len(self.findings) - limit} more")
        return '\n'.join(lines)


class Deny(Exception):
    """Abort validation with a finding that makes further checks pointless."""

    def __init__(self, finding: Finding):
        super().__init__(str(finding))
        self.finding = finding
