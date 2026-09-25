# SPDX-FileCopyrightText: 2026 James R. Barlow
# SPDX-License-Identifier: MPL-2.0

"""Validation findings and reports."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal, NamedTuple

from pikepdf.pdfa._flavour import Flavour

if TYPE_CHECKING:
    from pikepdf.pdfa._prepare import PrepareResult

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


Verdict = Literal['pass', 'fail', 'not_checked']


@dataclass
class Report:
    """Result of checking one document against one PDF/A flavour.

    Attributes:
        flavour: The PDF/A flavour checked.
        findings: Every reason the document was not approved.
        save_kwargs: The `pikepdf.Pdf.save` keyword arguments the check
            assumed, or that were used to write the file.
        output_intent: ICC colour space signature of the PDF/A OutputIntent
            profile (``'RGB'``, ``'CMYK'`` or ``'GRAY'``), or None if unknown.
        prepared: What `prepare` changed before `save` wrote the file, or
            None if the report did not come from `save` or nothing was
            prepared.
    """

    flavour: Flavour
    findings: list[Finding] = field(default_factory=list)
    save_kwargs: dict[str, Any] = field(default_factory=dict)
    output_intent: str | None = None
    prepared: PrepareResult | None = None

    @property
    def verdict(self) -> Verdict:
        """``'pass'``, ``'fail'`` or ``'not_checked'``.

        ``'fail'`` if any finding is a violation; ``'not_checked'`` if there
        are findings but all of them are constructs the validator does not
        check; ``'pass'`` if there are no findings.
        """
        if any(f.kind == 'violation' for f in self.findings):
            return 'fail'
        if self.findings:
            return 'not_checked'
        return 'pass'

    @property
    def passed(self) -> bool:
        """True if nothing was found that prevents approval."""
        return self.verdict == 'pass'

    @property
    def violations(self) -> tuple[Finding, ...]:
        """Findings of constructs that break PDF/A."""
        return tuple(f for f in self.findings if f.kind == 'violation')

    @property
    def unsupported(self) -> tuple[Finding, ...]:
        """Findings of constructs the validator does not check."""
        return tuple(f for f in self.findings if f.kind == 'unsupported')

    def summary(self, limit: int = 20) -> str:
        """Return a multi-line description of the result.

        Args:
            limit: Maximum number of findings to list.
        """
        header = f"PDF/A-{self.flavour.value}: {self.verdict}"
        if not self.findings:
            return header
        lines = [
            f"{header} ({len(self.violations)} violation(s), "
            f"{len(self.unsupported)} unsupported)"
        ]
        lines.extend(f"  {finding}" for finding in self.findings[:limit])
        if len(self.findings) > limit:
            lines.append(f"  ... and {len(self.findings) - limit} more")
        return '\n'.join(lines)


ValidationReport = Report


class PdfaError(Exception):
    """A document did not pass PDF/A validation.

    Attributes:
        report: The `Report` that explains why.
    """

    def __init__(self, report: Report):
        super().__init__(report.summary())
        self.report = report


class Deny(Exception):
    """Abort validation with a finding that makes further checks pointless."""

    def __init__(self, finding: Finding):
        super().__init__(str(finding))
        self.finding = finding
