# SPDX-FileCopyrightText: 2026 James R. Barlow
# SPDX-License-Identifier: MPL-2.0

"""The character codes that a document's content streams show in each font.

Repairs that change a font's encoding use this to prove that no glyph drawn
changes. The scan over-approximates: it reads every Form XObject, tiling
pattern and Type 3 glyph procedure reachable from a resource dictionary,
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
    """Scan content streams, each once for each resource dictionary it uses.

    A resource dictionary is identified by its owner: the page, the stream or
    the Type 3 font it belongs to. A stream without its own /Resources uses
    those of the context that holds it, so it is scanned once for each such
    context.
    """

    def __init__(self) -> None:
        self.codes: defaultdict[tuple[int, int], set[int]] = defaultdict(set)
        self._scanned: set[tuple[object, object]] = set()
        self._listed: set[object] = set()

    def content(
        self,
        content: pikepdf.Page | Stream,
        content_key: object,
        resources: Dictionary,
        owner: object,
    ) -> None:
        """Scan a content stream with the resources of *owner*.

        The streams that those resources hold are scanned too.
        """
        if (content_key, owner) not in self._scanned:
            self._scanned.add((content_key, owner))
            self._instructions(content, resources)
        if owner not in self._listed:
            self._listed.add(owner)
            self._resources(resources, owner)

    def _instructions(
        self, content: pikepdf.Page | Stream, resources: Dictionary
    ) -> None:
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

    def _resources(self, resources: Dictionary, owner: object) -> None:
        for xobject in _category(resources, '/XObject').values():
            if isinstance(xobject, Stream) and xobject.get('/Subtype') == Name.Form:
                self.stream(xobject, resources, owner)
        for pattern in _category(resources, '/Pattern').values():
            if isinstance(pattern, Stream) and pattern.get('/PatternType') == 1:
                self.stream(pattern, resources, owner)
        for name, font in _category(resources, '/Font').items():
            if not isinstance(font, Dictionary) or font.get('/Subtype') != Name.Type3:
                continue
            procs = font.get('/CharProcs')
            if not isinstance(procs, Dictionary):
                continue
            glyph_resources, glyph_owner = resources, owner
            own = font.get('/Resources')
            if isinstance(own, Dictionary) and not isinstance(own, Stream):
                glyph_resources = own
                glyph_owner = (
                    ('Type3', font.objgen)
                    if font.is_indirect
                    else ('Type3', owner, name)
                )
            for proc in procs.values():
                if isinstance(proc, Stream):
                    self.stream(proc, glyph_resources, glyph_owner)

    def stream(self, stream: Stream, resources: Dictionary, owner: object) -> None:
        """Scan a stream held by the resources of *owner*."""
        own = stream.get('/Resources')
        if isinstance(own, Dictionary) and not isinstance(own, Stream):
            self.content(stream, stream.objgen, own, stream.objgen)
        else:
            self.content(stream, stream.objgen, resources, owner)


def _page_resources(page: Dictionary) -> Dictionary:
    node: object = page
    seen: set[tuple[int, int]] = set()
    while isinstance(node, Dictionary):
        resources = node.get('/Resources')
        if isinstance(resources, Dictionary) and not isinstance(resources, Stream):
            return resources
        if node.objgen in seen:
            break
        seen.add(node.objgen)
        node = node.get('/Parent')
    return Dictionary()


def _appearance_streams(annot: Dictionary) -> list[Stream]:
    appearance = annot.get('/AP')
    if not isinstance(appearance, Dictionary):
        return []
    streams: list[Stream] = []
    for value in appearance.values():
        if isinstance(value, Stream):
            streams.append(value)
        elif isinstance(value, Dictionary):
            streams.extend(v for v in value.values() if isinstance(v, Stream))
    return streams


def font_codes(pdf: pikepdf.Pdf) -> dict[tuple[int, int], set[int]] | None:
    """Return the character codes shown in each indirect font, by objgen.

    Fonts that no content shows text in are absent. Returns None if some
    text is shown in a font the scan cannot identify, or a content stream
    cannot be parsed.
    """
    scan = _Scan()
    try:
        for page in pdf.pages:
            resources = _page_resources(page.obj)
            owner = ('page', page.obj.objgen)
            scan.content(page, owner, resources, owner)
            annots = page.obj.get('/Annots')
            if not isinstance(annots, Array):
                continue
            for annot in annots:
                if not isinstance(annot, Dictionary):
                    continue
                for stream in _appearance_streams(annot):
                    # An appearance stream uses only its own resources
                    scan.stream(stream, Dictionary(), ('appearance', stream.objgen))
    except _Incomplete:
        return None
    return dict(scan.codes)
