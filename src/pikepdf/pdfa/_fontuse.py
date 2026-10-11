# SPDX-FileCopyrightText: 2026 James R. Barlow
# SPDX-License-Identifier: MPL-2.0

"""The character codes that a document's content streams show in each font.

Repairs that change a font's encoding use this to prove that no glyph drawn
changes. The scan over-approximates: it reads every content scope that
`pikepdf.Pdf.content_scopes` reports -- each Form XObject, tiling pattern,
Type 3 glyph procedure and soft mask reachable from a resource dictionary,
whether or not anything draws it, and every annotation appearance stream.
Showing text in a font it cannot identify makes the scan incomplete.
"""

from __future__ import annotations

from collections import defaultdict

import pikepdf
from pikepdf import Array, Dictionary, Name, Stream, String

TEXT_SHOWING = frozenset({'Tj', "'", '"', 'TJ'})


class _Incomplete(Exception):
    """The scan cannot tell which font some text is shown in."""


def _category(resources: Dictionary, name: str) -> Dictionary:
    value = resources.get(name)
    if isinstance(value, Dictionary) and not isinstance(value, Stream):
        return value
    return Dictionary()


class _Scan:
    """Record the character codes that content streams show in each font."""

    def __init__(self) -> None:
        self.codes: defaultdict[tuple[int, int], set[int]] = defaultdict(set)

    def instructions(self, content: pikepdf.Object, resources: Dictionary) -> None:
        try:
            instructions = pikepdf.parse_content_stream(content)
        except (pikepdf.PdfError, TypeError, ValueError) as e:
            raise _Incomplete from e
        fonts = _category(resources, '/Font')
        font: Dictionary | None = None
        stack: list[Dictionary | None] = []
        for instruction in instructions:
            if not isinstance(instruction, pikepdf.ContentStreamInstruction):
                continue  # an inline image
            op = str(instruction.operator)
            operands = instruction.operands
            if op == 'q':
                stack.append(font)
            elif op == 'Q':
                if stack:
                    font = stack.pop()
            elif op == 'Tf':
                if not operands or not isinstance(operands[0], Name):
                    raise _Incomplete
                selected = fonts.get(operands[0])
                if not isinstance(selected, Dictionary):
                    raise _Incomplete
                font = selected
            elif op == 'gs':
                font = self._extgstate_font(resources, list(operands), font)
            elif op in TEXT_SHOWING:
                if font is None or not operands:
                    raise _Incomplete
                self._show(font, operands[-1])

    @staticmethod
    def _extgstate_font(
        resources: Dictionary, operands: list[object], font: Dictionary | None
    ) -> Dictionary | None:
        """The font after a gs operator, which may set one."""
        if not operands or not isinstance(operands[0], Name):
            raise _Incomplete
        state = _category(resources, '/ExtGState').get(operands[0])
        if not isinstance(state, Dictionary):
            raise _Incomplete
        if '/Font' not in state:
            return font
        value = state.get('/Font')
        if (
            isinstance(value, Array)
            and len(value) >= 1
            and isinstance(value[0], Dictionary)
        ):
            return value[0]
        raise _Incomplete

    def _show(self, font: Dictionary, operand: object) -> None:
        if not font.is_indirect:
            return
        # Anything but a string shows no glyphs
        items = operand if isinstance(operand, Array) else [operand]
        codes = self.codes[font.objgen]
        for item in items:
            if isinstance(item, String):
                codes.update(bytes(item))


def font_codes(pdf: pikepdf.Pdf) -> dict[tuple[int, int], set[int]] | None:
    """Return the character codes shown in each indirect font, by objgen.

    Fonts that no content shows text in are absent. Returns None if some
    text is shown in a font the scan cannot identify, or a content stream
    cannot be parsed.
    """
    scan = _Scan()
    try:
        for scope in pdf.content_scopes():
            resources = scope.resources
            scan.instructions(
                scope.content, resources if resources is not None else Dictionary()
            )
    except _Incomplete:
        return None
    return dict(scan.codes)
