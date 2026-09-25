# SPDX-FileCopyrightText: 2026 James R. Barlow
# SPDX-License-Identifier: MPL-2.0

"""PDF/A flavours supported by the validator."""

from __future__ import annotations

from enum import StrEnum


class Flavour(StrEnum):
    """A PDF/A part and conformance level that the validator can check."""

    PDFA_1B = '1b'
    PDFA_2B = '2b'
    PDFA_3B = '3b'

    @property
    def part(self) -> int:
        """ISO 19005 part number (1, 2 or 3)."""
        return int(self.value[0])

    @property
    def spec(self) -> str:
        """Specification prefix used in veraPDF rule ids, e.g. ``ISO_19005_2``."""
        return f'ISO_19005_{self.part}'

    def rule(self, part1: str | None, part23: str | None, local: str = 'policy') -> str:
        """Return the rule id for this flavour.

        Args:
            part1: Clause and test number in ISO 19005-1 (e.g. ``'6.1.4-3'``),
                or None if PDF/A-1 has no equivalent veraPDF rule.
            part23: Clause and test number shared by ISO 19005-2 and -3.
            local: Suffix for an ``pikepdf:`` id used when the flavour has no
                corresponding veraPDF rule.
        """
        clause = part1 if self.part == 1 else part23
        if clause is None:
            return f'pikepdf:{local}'
        return f'{self.spec}:{clause}'
