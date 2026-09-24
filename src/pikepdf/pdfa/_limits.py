# SPDX-FileCopyrightText: 2026 James R. Barlow
# SPDX-License-Identifier: MPL-2.0

"""Implementation limits on PDF objects (ISO 19005-1 6.1.12, ISO 19005-2 6.1.13).

Every indirect object of the file is checked, with the direct arrays and
dictionaries it contains, and so are content stream operands. Values nested
deeper than `MAX_NESTING` are not checked, so such nesting is denied.
"""

from __future__ import annotations

import itertools
from collections.abc import Iterable
from decimal import Decimal
from typing import Any

import pikepdf
from pikepdf.pdfa._context import ValidationContext
from pikepdf.pdfa._flavour import Flavour
from pikepdf.pdfa._report import FindingKind

MIN_INTEGER = -(2**31)
MAX_INTEGER = 2**31 - 1
MAX_REAL = {1: Decimal(32767), 2: Decimal('3.403e38')}
MIN_REAL = Decimal('1.175e-38')  # PDF/A-2 and -3 only
MAX_STRING = {1: 65535, 2: 32767}
MAX_NAME = 127
MAX_ARRAY_1B = 8191
MAX_DICT_1B = 4095
MAX_NESTING = 64

# Keys of ``RULES``: (ISO 19005-1 clause, ISO 19005-2/3 clause)
RULES = {
    'integer': ('6.1.12-1', '6.1.13-1'),
    'real': ('6.1.12-2', '6.1.13-2'),
    'string': ('6.1.12-3', '6.1.13-3'),
    'name': ('6.1.12-4', '6.1.13-4'),
    'array': ('6.1.12-5', None),
    'dict': ('6.1.12-6', None),
    'small-real': (None, '6.1.13-5'),
}


def _name_length(name: Any) -> int:
    """Length in bytes of a name without its slash, after #xx expansion."""
    try:
        return len(str(name).encode('utf-8')) - 1
    except UnicodeDecodeError:
        raw = name.unparse()
        return len(raw) - 1 - 2 * raw.count(b'#')


def _key_length(key: str) -> int:
    return len(key.encode('utf-8', 'surrogateescape')) - 1


class LimitChecker:
    """Check values against the implementation limits of one flavour."""

    def __init__(self, flavour: Flavour):
        self.flavour = flavour
        part = 1 if flavour.part == 1 else 2
        self.max_real = MAX_REAL[part]
        self.min_real = MIN_REAL if part == 2 else None
        self.max_string = MAX_STRING[part]
        self.containers = part == 1

    def rule(self, key: str) -> str:
        """Return the rule id of a limit for this flavour."""
        if key == 'depth':
            return 'pikepdf:depth'
        part1, part23 = RULES[key]
        return self.flavour.rule(part1, part23, f'limit-{key}')

    @staticmethod
    def kind(key: str) -> FindingKind:
        """Return the kind of finding for a problem key."""
        return 'unsupported' if key == 'depth' else 'violation'

    def scalar(self, value: Any) -> tuple[str, str] | None:
        """Check a scalar; return (rule key, message) if it breaks a limit."""
        if isinstance(value, bool):
            return None
        if isinstance(value, int):
            if not MIN_INTEGER <= value <= MAX_INTEGER:
                return 'integer', f"integer {value} is out of range"
            return None
        if isinstance(value, Decimal | float):
            magnitude = abs(Decimal(value) if isinstance(value, float) else value)
            if magnitude > self.max_real:
                return 'real', f"real {value} exceeds {self.max_real}"
            if self.min_real is not None and 0 < magnitude < self.min_real:
                return 'small-real', f"real {value} is closer to zero than 1.175e-38"
            return None
        if isinstance(value, pikepdf.String):
            size = len(bytes(value))
            if size > self.max_string:
                return 'string', f"string of {size} bytes exceeds {self.max_string}"
            return None
        if isinstance(value, pikepdf.Name):
            size = _name_length(value)
            if size > MAX_NAME:
                return 'name', f"name of {size} bytes exceeds {MAX_NAME}"
            return None
        return None

    def problems(self, value: Any, depth: int = 0) -> list[tuple[str, str]]:
        """Return every limit a value breaks, looking into direct containers."""
        found: list[tuple[str, str]] = []
        self._collect(value, depth, found, top=True)
        return found

    def _collect(
        self, value: Any, depth: int, found: list[tuple[str, str]], top: bool = False
    ) -> None:
        if isinstance(value, pikepdf.Object) and value.is_indirect and not top:
            return  # checked as an object of its own
        if depth > MAX_NESTING:
            found.append(
                ('depth', f"arrays and dictionaries nested deeper than {MAX_NESTING}")
            )
            return
        if isinstance(value, pikepdf.Stream):
            self._collect_dict(value.stream_dict, depth, found)
        elif isinstance(value, pikepdf.Dictionary):
            self._collect_dict(value, depth, found)
        elif isinstance(value, pikepdf.Array):
            if self.containers and len(value) > MAX_ARRAY_1B:
                found.append(
                    ('array', f"array of {len(value)} elements exceeds {MAX_ARRAY_1B}")
                )
            for item in value:
                self._collect(item, depth + 1, found)
        else:
            problem = self.scalar(value)
            if problem is not None:
                found.append(problem)

    def _collect_dict(
        self, value: pikepdf.Dictionary, depth: int, found: list[tuple[str, str]]
    ) -> None:
        # items(), not get(): keys that are not UTF-8 cannot be looked up
        items = list(value.items())
        if self.containers and len(items) > MAX_DICT_1B:
            found.append(
                ('dict', f"dictionary of {len(items)} entries exceeds {MAX_DICT_1B}")
            )
        for key, item in items:
            if _key_length(key) > MAX_NAME:
                found.append(('name', f"name {key[:32]!r}... exceeds {MAX_NAME} bytes"))
            self._collect(item, depth + 1, found)


def check_document_limits(ctx: ValidationContext) -> None:
    """Check every indirect object written to the file and the trailer."""
    checker = LimitChecker(ctx.flavour)
    objects: Iterable[Any] = itertools.chain(
        [ctx.pdf.trailer], ctx.model.objects(ctx.pdf)
    )
    for obj in objects:
        reported: set[str] = set()
        for key, message in checker.problems(obj):
            if key in reported:
                continue
            reported.add(key)
            where = ctx.describe(obj) if obj.is_indirect else 'trailer'
            ctx.deny(checker.rule(key), where, message, checker.kind(key))
