# SPDX-FileCopyrightText: 2026 James R. Barlow
# SPDX-License-Identifier: MPL-2.0

"""Content stream checks.

`ContentWalker` parses page content and the Form XObjects it draws, checking
every operator against the ISO 32000-1 Table A.1 allowlist with its operand
types, tracking the graphics state that matters for PDF/A (q/Q nesting, the
current font and text rendering mode, the colour spaces in use) and
recording every character code shown so the font checks can verify the
glyphs at the end of the document.

The parsing and the per-instruction checks that need no state (operand
types, the operator allowlist, implementation limits) run in C++, in
`pikepdf._core._ContentChecker`, which hands back only the instructions that
need attention here, so most operands never become Python objects.

qpdf rewrites the objects of the file but copies content stream bytes
unchanged, and its content parser forgives some syntax that veraPDF does
not, so `scan_raw_content` checks the raw bytes too.
"""

from __future__ import annotations

import re
import warnings
from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import Any

import pikepdf
from pikepdf._core import _ContentChecker
from pikepdf._core import _scan_raw_content as scan_raw_content
from pikepdf.pdfa._colour import (
    DEFAULT_SPACES,
    ColourSpaceInfo,
    check_image_colour,
    resolve_colourspace,
)
from pikepdf.pdfa._context import ValidationContext
from pikepdf.pdfa._fonts import FontInfo, load_font
from pikepdf.pdfa._limits import (
    MAX_ARRAY_1B,
    MAX_DICT_1B,
    MAX_INTEGER,
    MAX_NAME,
    MAX_NESTING,
    MIN_INTEGER,
    LimitChecker,
)
from pikepdf.pdfa._report import FindingKind
from pikepdf.pdfa._shallow import pdf_repr, pdf_str

MAX_Q_DEPTH = 28
MAX_FORM_DEPTH = 32
RENDERING_INTENTS = frozenset(
    {'/RelativeColorimetric', '/AbsoluteColorimetric', '/Perceptual', '/Saturation'}
)
INLINE_IMAGE_KEYS = frozenset(
    {
        '/BitsPerComponent',
        '/ColorSpace',
        '/Decode',
        '/DecodeParms',
        '/Filter',
        '/Height',
        '/ImageMask',
        '/Intent',
        '/Interpolate',
        '/Width',
    }
)
INLINE_IMAGE_FILTERS = frozenset(
    {
        '/ASCIIHexDecode',
        '/ASCII85Decode',
        '/FlateDecode',
        '/RunLengthDecode',
        '/CCITTFaxDecode',
        '/DCTDecode',
    }
)
FORBIDDEN_FILTERS = frozenset({'/LZWDecode', '/Crypt'})

_WHITESPACE = b'\x00\t\n\x0c\r '
# An EI operator inside inline image data
_EMBEDDED_EI = re.compile(
    rb'['
    + re.escape(_WHITESPACE)
    + rb']EI(?=['
    + re.escape(_WHITESPACE + b'()<>[]{}/%')
    + rb']|\Z)'
)

# Operand signatures: n number, i integer, N name, s string, a array,
# D dictionary or name. Operators with variable operands are handled by
# their handlers ('*').
OPERATORS: dict[str, str] = {
    # general graphics state
    'w': 'n',
    'J': 'i',
    'j': 'i',
    'M': 'n',
    'd': 'an',
    'ri': 'N',
    'i': 'n',
    'gs': 'N',
    # special graphics state
    'q': '',
    'Q': '',
    'cm': 'nnnnnn',
    # path construction
    'm': 'nn',
    'l': 'nn',
    'c': 'nnnnnn',
    'v': 'nnnn',
    'y': 'nnnn',
    'h': '',
    're': 'nnnn',
    # path painting
    'S': '',
    's': '',
    'f': '',
    'F': '',
    'f*': '',
    'B': '',
    'B*': '',
    'b': '',
    'b*': '',
    'n': '',
    # clipping paths
    'W': '',
    'W*': '',
    # text objects
    'BT': '',
    'ET': '',
    # text state
    'Tc': 'n',
    'Tw': 'n',
    'Tz': 'n',
    'TL': 'n',
    'Tf': 'Nn',
    'Tr': 'i',
    'Ts': 'n',
    # text positioning
    'Td': 'nn',
    'TD': 'nn',
    'Tm': 'nnnnnn',
    'T*': '',
    # text showing
    'Tj': 's',
    'TJ': 'a',
    "'": 's',
    '"': 'nns',
    # Type 3 fonts
    'd0': 'nn',
    'd1': 'nnnnnn',
    # colour
    'CS': 'N',
    'cs': 'N',
    'SC': '*',
    'SCN': '*',
    'sc': '*',
    'scn': '*',
    'G': 'n',
    'g': 'n',
    'RG': 'nnn',
    'rg': 'nnn',
    'K': 'nnnn',
    'k': 'nnnn',
    # shading patterns
    'sh': 'N',
    # XObjects
    'Do': 'N',
    # marked content
    'MP': 'N',
    'DP': 'ND',
    'BMC': 'N',
    'BDC': 'ND',
    'EMC': '',
    # compatibility
    'BX': '',
    'EX': '',
}
DEVICE_OPERATORS = {
    'g': '/DeviceGray',
    'G': '/DeviceGray',
    'rg': '/DeviceRGB',
    'RG': '/DeviceRGB',
    'k': '/DeviceCMYK',
    'K': '/DeviceCMYK',
}
TEXT_POSITIONING = frozenset({'Td', 'TD', 'Tm', 'T*'})
TEXT_SHOWING = frozenset({'Tj', 'TJ', "'", '"'})


def _is_number(obj: Any) -> bool:
    """True for an Integer or Real; a Boolean is not a number.

    A Real is a number even if its digits overflow a double; the limit checks
    report it as out of range.
    """
    return isinstance(obj, pikepdf.Integer | pikepdf.Real)


@dataclass(frozen=True)
class GraphicsState:
    """The part of the graphics state the checks track.

    Attributes:
        font: The current font, if Tf has been used.
        tr: The text rendering mode.
        fill: Components of the fill colour space, if known.
        stroke: Components of the stroke colour space, if known.
        overprint: Stroke and fill overprint (OP, op) and overprint mode
            (OPM), as set by graphics state parameter dictionaries.
    """

    font: FontInfo | None = None
    tr: int = 0
    fill: int | None = 1
    stroke: int | None = 1
    overprint: tuple[bool, bool, int] = (False, False, 0)


class _Resources:
    """The resources of one content stream, with 6.2.2-2 lookups.

    Args:
        resources: The /Resources dictionary, or None if the stream has none.
        explicit: False if the resources are inherited rather than directly
            associated with the stream.
        why: Explanation used when a lookup fails because of *explicit*.
    """

    def __init__(self, resources: Any, explicit: bool, why: str = ''):
        self.dict = resources if isinstance(resources, pikepdf.Dictionary) else None
        self.explicit = explicit
        self.why = why
        # Fonts by resource name, so that a direct font dictionary is loaded
        # (and a missing one reported) once per content stream
        self.fonts: dict[str, FontInfo | None] = {}

    def category(self, category: str) -> Any:
        if self.dict is None:
            return None
        value = self.dict.get(category)
        return value if isinstance(value, pikepdf.Dictionary) else None

    def lookup(
        self, ctx: ValidationContext, category: str, name: Any, where: str
    ) -> Any:
        """Return the named resource, or None after reporting why not."""
        if not self.explicit and ctx.flavour.part != 1:
            ctx.deny(
                ctx.rule(None, '6.2.2-2', 'resource-missing'),
                where,
                f"{category} {name} is not in an explicitly associated "
                f"/Resources dictionary ({self.why})",
            )
            return None
        table = self.category(category)
        value = table.get(name) if table is not None else None
        if value is None:
            if not self.explicit:
                ctx.deny(
                    'pikepdf:resource-missing',
                    where,
                    f"{category} {name} is not available ({self.why})",
                    'unsupported',
                )
            else:
                ctx.deny(
                    ctx.rule(None, '6.2.2-2', 'resource-missing'),
                    where,
                    f"{category} {name} is not in the content stream's resources",
                )
        return value


class _StreamWalk:
    """State of the walk through one content stream."""

    def __init__(
        self,
        walker: ContentWalker,
        resources: _Resources,
        state: GraphicsState,
        base_depth: int,
        recursion: int,
        where: str,
    ):
        self.walker = walker
        self.ctx = walker.ctx
        self.resources = resources
        self.state = state
        self.saved: list[GraphicsState] = []
        self.base_depth = base_depth
        self.max_depth = 0
        self.recursion = recursion
        self.where = where
        self.in_text = False
        self.compat = 0
        self.reported: set[tuple[str, str]] = set()
        # Colour spaces already resolved in this stream, by operand
        self.colour_spaces: dict[str, ColourSpaceInfo | None] = {}

    def deny(self, rule: str, message: str, kind: FindingKind = 'violation') -> None:
        """Report a finding once per (rule, message) for this stream."""
        if (rule, message) in self.reported:
            return
        self.reported.add((rule, message))
        self.ctx.deny(rule, self.where, message, kind)

    def syntax(self, message: str) -> None:
        self.deny('pikepdf:content-syntax', message)

    def run(self, stream: Any) -> int:
        """Check a stream (or page); return the deepest relative q nesting."""
        ctx = self.ctx
        try:
            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter('always')
                events, count = self.walker.checker.check(stream)
        except (pikepdf.PdfError, ValueError, TypeError) as e:
            self.deny('pikepdf:content-parse', f"cannot parse content: {e}")
            return self.max_depth
        if caught:
            self.deny('pikepdf:content-parse', f"content stream: {caught[0].message}")
            return self.max_depth
        self.check_raw(stream, [event[2] for event in events if event[0] == 'inline'])
        # Each event names the instruction it is about. Instructions between
        # events count towards the budget too, and a Form XObject drawn by
        # an earlier instruction may have used some of it.
        counted = 0
        for event in events:
            kind, index = event[0], event[1]
            if index >= counted:
                ctx.instructions += index + 1 - counted
                counted = index + 1
                if self.over_budget():
                    return self.max_depth
            if kind == 'op':
                _HANDLERS[event[2]](self, event[2], event[3])
            elif kind == 'limits':
                self.check_limits(event[2])
            elif kind == 'undefined':
                self.deny(
                    ctx.rule('6.2.10-1', '6.2.2-1'),
                    f"operator {event[2]!r} is not defined in ISO 32000-1",
                )
            elif kind == 'operands':
                self.deny(
                    'pikepdf:content-operands',
                    f"operator {event[2]} has operands {pdf_repr(event[3])}",
                )
            else:
                self.inline_image(event[2].iimage)
        ctx.instructions += count - counted
        if self.over_budget():
            return self.max_depth
        if self.in_text:
            self.syntax("BT without ET")
        return self.max_depth

    def over_budget(self) -> bool:
        """Deny the content if it has used up the instruction budget."""
        ctx = self.ctx
        if ctx.instructions <= ctx.max_instructions:
            return False
        self.deny(
            'pikepdf:content-budget',
            f"more than {ctx.max_instructions} content instructions",
            'unsupported',
        )
        return True

    def check_raw(self, stream: Any, inline_images: list[Any]) -> None:
        """Check what the content parser does not report.

        That is hex string syntax, and inline image data that another parser
        could end early.
        """
        ctx = self.ctx
        images: list[bytes] = []
        for instruction in inline_images:
            try:
                raw = instruction.iimage.read_raw_bytes()
            except (pikepdf.PdfError, AttributeError) as e:
                self.deny('pikepdf:inline-image', f"inline image: {e}", 'unsupported')
                return
            if _EMBEDDED_EI.search(b' ' + raw) is not None:
                self.deny(
                    'pikepdf:inline-image',
                    "inline image data contains EI, so where it ends is ambiguous",
                    'unsupported',
                )
            images.append(raw)
        try:
            data = stream.read_bytes()
        except pikepdf.PdfError as e:
            self.deny('pikepdf:content-parse', f"cannot read content: {e}")
            return
        for clause, message in scan_raw_content(data, images):
            if clause == 'inline-image':
                self.deny('pikepdf:inline-image', message, 'unsupported')
            else:
                self.deny(ctx.rule(clause, clause), message)

    def check_limits(self, operand: Any) -> None:
        limits = self.walker.limits
        if isinstance(operand, pikepdf.Array | pikepdf.Dictionary):
            problems = limits.problems(operand)
        else:
            problem = limits.scalar(operand)
            if problem is None:
                return
            problems = [problem]
        for key, message in problems:
            self.deny(limits.rule(key), message, limits.kind(key))

    # --- graphics state -----------------------------------------------------

    def op_q(self, op: str, operands: list[Any]) -> None:
        self.saved.append(self.state)
        depth = len(self.saved)
        self.max_depth = max(self.max_depth, depth)
        if self.base_depth + depth > MAX_Q_DEPTH:
            self.deny(
                self.ctx.rule('6.1.12-8', '6.1.13-8'),
                f"q/Q nesting exceeds {MAX_Q_DEPTH}",
            )

    def op_Q(self, op: str, operands: list[Any]) -> None:
        if not self.saved:
            self.syntax("Q without matching q")
            return
        self.state = self.saved.pop()

    def op_d(self, op: str, operands: list[Any]) -> None:
        if not all(_is_number(item) for item in operands[0]):
            self.deny('pikepdf:content-operands', "dash array item is not a number")

    def op_ri(self, op: str, operands: list[Any]) -> None:
        if str(operands[0]) not in RENDERING_INTENTS:
            self.deny(
                self.ctx.rule('6.2.9-1', '6.2.6-1'),
                f"rendering intent {operands[0]} is not one of the four standard ones",
            )

    def op_gs(self, op: str, operands: list[Any]) -> None:
        where = f'{self.where} gs {operands[0]}'
        params = self.resources.lookup(self.ctx, '/ExtGState', operands[0], where)
        if params is None:
            return
        if not isinstance(params, pikepdf.Dictionary):
            self.deny(
                'pikepdf:schema-ExtGState',
                f"ExtGState {operands[0]} is not a dictionary",
            )
            return
        # The dictionary itself is checked by the ExtGState role; here only
        # the state that combines across dictionaries is tracked.
        stroke, fill, mode = self.state.overprint
        if '/OP' in params:
            stroke = params.get_bool('/OP') is True
            if '/op' not in params:
                fill = stroke
        if '/op' in params:
            fill = params.get_bool('/op') is True
        if '/OPM' in params:
            # Only the Integer 0 selects mode 0; any other value may be 1.
            mode = 0 if params.get_int('/OPM') == 0 else 1
        self.state = replace(self.state, overprint=(stroke, fill, mode))
        if mode == 1 and (stroke or fill):
            self.deny(
                self.ctx.rule(None, '6.2.4.2-2', 'overprint-mode'),
                "overprint mode 1 with overprinting on is not supported "
                "(PDF/A forbids it for ICCBased CMYK colour)",
                'unsupported',
            )

    def op_d0(self, op: str, operands: list[Any]) -> None:
        self.deny('pikepdf:d0-d1', f"{op} outside a Type 3 glyph description")

    op_d1 = op_d0

    # --- text ---------------------------------------------------------------

    def op_BT(self, op: str, operands: list[Any]) -> None:
        if self.in_text:
            self.syntax("nested BT")
        self.in_text = True

    def op_ET(self, op: str, operands: list[Any]) -> None:
        if not self.in_text:
            self.syntax("ET without BT")
        self.in_text = False

    def op_Tf(self, op: str, operands: list[Any]) -> None:
        name = operands[0]
        key = name.unparse().decode('latin-1')
        if key in self.resources.fonts:
            info = self.resources.fonts[key]
        else:
            where = f'{self.where} Tf {key}'
            font = self.resources.lookup(self.ctx, '/Font', name, where)
            info = None
            if font is not None:
                info = load_font(font, self.ctx, f'{self.where} font {key}')
            self.resources.fonts[key] = info
        self.state = replace(self.state, font=info)

    def op_Tr(self, op: str, operands: list[Any]) -> None:
        mode = int(operands[0])
        if not 0 <= mode <= 7:
            self.deny('pikepdf:content-operands', f"text rendering mode {mode}")
            return
        self.state = replace(self.state, tr=mode)

    def text_positioning(self, op: str, operands: list[Any]) -> None:
        if not self.in_text:
            self.syntax(f"{op} outside BT/ET")

    def text_showing(self, op: str, operands: list[Any]) -> None:
        if not self.in_text:
            self.syntax(f"{op} outside BT/ET")
            return
        font = self.state.font
        if font is None:
            self.deny('pikepdf:text-no-font', f"{op} with no current font")
            return
        if op == 'TJ':
            strings = []
            for item in operands[0]:
                if isinstance(item, pikepdf.String):
                    strings.append(bytes(item))
                elif not _is_number(item):
                    self.deny(
                        'pikepdf:content-operands', f"TJ array item {pdf_repr(item)}"
                    )
                    return
        else:
            strings = [bytes(operands[-1])]
        for data in strings:
            font.record(font.decode_string(data, self.ctx), self.state.tr)

    # --- colour -------------------------------------------------------------

    def colour_space(self, name: pikepdf.Name, where: str) -> ColourSpaceInfo | None:
        """Resolve a colour space operand once per content stream."""
        key = name.unparse().decode('latin-1')
        if key in self.colour_spaces:
            return self.colour_spaces[key]
        info = resolve_colourspace(
            name, self.resources.category('/ColorSpace'), self.ctx, where
        )
        self.colour_spaces[key] = info
        return info

    def op_g(self, op: str, operands: list[Any]) -> None:
        family = DEVICE_OPERATORS[op]
        info = self.colour_space(pikepdf.Name(family), f'{self.where} {op}')
        components = info.components if info is not None else None
        if op.islower():
            self.state = replace(self.state, fill=components)
        else:
            self.state = replace(self.state, stroke=components)

    op_G = op_rg = op_RG = op_k = op_K = op_g

    def op_cs(self, op: str, operands: list[Any]) -> None:
        name = operands[0]
        info = self.colour_space(name, f'{self.where} {op} {name}')
        components = info.components if info is not None else None
        if op == 'cs':
            self.state = replace(self.state, fill=components)
        else:
            self.state = replace(self.state, stroke=components)

    op_CS = op_cs

    def op_sc(self, op: str, operands: list[Any]) -> None:
        if op in ('scn', 'SCN') and operands and isinstance(operands[-1], pikepdf.Name):
            self.deny(
                'pikepdf:pattern', f"{op} with a pattern {operands[-1]}", 'unsupported'
            )
            return
        if not operands or not all(_is_number(o) for o in operands):
            self.deny(
                'pikepdf:content-operands', f"{op} has operands {pdf_repr(operands)}"
            )
            return
        expected = self.state.fill if op.islower() else self.state.stroke
        if expected is not None and len(operands) != expected:
            self.deny(
                'pikepdf:content-operands',
                f"{op} has {len(operands)} operands; the colour space has "
                f"{expected} components",
            )

    op_scn = op_SC = op_SCN = op_sc

    def op_sh(self, op: str, operands: list[Any]) -> None:
        self.deny('pikepdf:shading', "shadings (sh) are not supported", 'unsupported')

    # --- XObjects -----------------------------------------------------------

    def op_Do(self, op: str, operands: list[Any]) -> None:
        name = operands[0]
        where = f'{self.where} Do {name}'
        if self.in_text:
            self.deny('pikepdf:content-syntax', "Do inside BT/ET", 'unsupported')
        xobject = self.resources.lookup(self.ctx, '/XObject', name, where)
        if xobject is None:
            return
        if not isinstance(xobject, pikepdf.Stream):
            self.deny('pikepdf:schema-XObject', f"XObject {name} is not a stream")
            return
        subtype = xobject.get('/Subtype')
        if subtype == pikepdf.Name.Image:
            # The image dictionary is checked by the ImageXObject role when
            # the document walker reaches the resource dictionary; its colour
            # space depends on the /Default* colour spaces of this stream.
            self.walker.paint_image(
                xobject, self.resources.category('/ColorSpace'), where
            )
            return
        if subtype == pikepdf.Name.Form:
            self.walker.walk_form(
                xobject,
                self.state,
                self.base_depth + len(self.saved),
                self.recursion + 1,
                where,
            )
            return
        self.deny(
            self.ctx.rule('6.2.7-1', '6.2.9-3'),
            f"XObject {name} has /Subtype {pdf_repr(subtype)}",
        )

    # --- marked content -----------------------------------------------------

    def op_BDC(self, op: str, operands: list[Any]) -> None:
        tag, properties = operands
        if tag == pikepdf.Name.OC:
            if self.ctx.flavour.part == 1:
                self.deny(
                    self.ctx.rule('6.1.13-1', None),
                    "optional content (BDC /OC) is not permitted in PDF/A-1",
                )
            else:
                self.deny(
                    'pikepdf:optional-content',
                    "optional content (BDC /OC) is not supported",
                    'unsupported',
                )
            return
        if isinstance(properties, pikepdf.Name):
            self.resources.lookup(
                self.ctx, '/Properties', properties, f'{self.where} {op} {properties}'
            )

    op_DP = op_BDC

    def op_BX(self, op: str, operands: list[Any]) -> None:
        self.compat += 1

    def op_EX(self, op: str, operands: list[Any]) -> None:
        if not self.compat:
            self.syntax("EX without BX")
            return
        self.compat -= 1

    # --- inline images ------------------------------------------------------

    def inline_image(self, image: Any) -> None:
        ctx = self.ctx
        try:
            obj = image.obj
        except Exception as e:  # pylint: disable=broad-except
            self.deny('pikepdf:inline-image', f"inline image: {e}", 'unsupported')
            return
        self.check_limits(obj)
        for key in obj.keys():
            if key == '/Length':
                self.deny(
                    'pikepdf:inline-image',
                    "inline image /Length (L) is not defined in ISO 32000-1",
                )
            elif key not in INLINE_IMAGE_KEYS:
                self.deny(
                    'pikepdf:inline-image',
                    f"inline image key {key} is not supported",
                    'unsupported',
                )
        filters = obj.get('/Filter')
        if filters is not None:
            items = filters if isinstance(filters, pikepdf.Array) else [filters]
            for item in items:
                name = str(item) if isinstance(item, pikepdf.Name) else pdf_repr(item)
                if name in FORBIDDEN_FILTERS:
                    self.deny(
                        ctx.rule('6.1.10-2', '6.1.10-1'),
                        f"inline image filter {name} is not permitted",
                    )
                elif name not in INLINE_IMAGE_FILTERS:
                    self.deny(
                        'pikepdf:inline-image',
                        f"inline image filter {name} is not supported",
                        'unsupported',
                    )
        if obj.get_bool('/Interpolate') is True:
            self.deny(
                ctx.rule('6.2.4-3', '6.2.8-3'),
                "inline image /Interpolate shall be false",
            )
        intent = obj.get('/Intent')
        if intent is not None and str(intent) not in RENDERING_INTENTS:
            self.deny(
                ctx.rule('6.2.9-1', '6.2.6-1'),
                f"inline image rendering intent {pdf_str(intent)}",
            )
        bpc = obj.get('/BitsPerComponent')
        bits = obj.get_int('/BitsPerComponent')
        allowed_bpc = {1, 2, 4, 8} if ctx.flavour.part == 1 else {1, 2, 4, 8, 16}
        if obj.get_bool('/ImageMask') is True:
            if bpc is not None and bits != 1:
                self.deny('pikepdf:inline-image', f"image mask with BPC {pdf_str(bpc)}")
            return
        if bits not in allowed_bpc:
            self.deny(
                ctx.rule('6.2.4-4', '6.2.8-4'),
                f"inline image /BitsPerComponent {pdf_str(bpc)}",
            )
        colour_space = obj.get('/ColorSpace')
        if colour_space is None:
            self.deny('pikepdf:inline-image', "inline image has no colour space")
            return
        resolve_colourspace(
            colour_space,
            self.resources.category('/ColorSpace'),
            ctx,
            f'{self.where} inline image',
            inline=True,
        )


_HANDLERS: dict[str, Callable[[_StreamWalk, str, list[Any]], None]] = {}
for _op in OPERATORS:
    _method = getattr(_StreamWalk, 'op_' + _op, None)
    if _method is not None:
        _HANDLERS[_op] = _method
for _op in TEXT_POSITIONING:
    _HANDLERS[_op] = _StreamWalk.text_positioning
for _op in TEXT_SHOWING:
    _HANDLERS[_op] = _StreamWalk.text_showing
# Handlers that do not look at their operands, so they are not converted
_OPERANDS_UNUSED = frozenset(
    {'q', 'Q', 'BT', 'ET', 'd0', 'd1', 'sh', 'BX', 'EX'}
    | TEXT_POSITIONING
    | DEVICE_OPERATORS.keys()
)


def content_checker(limits: LimitChecker) -> _ContentChecker:
    """Return the C++ checker for content streams, with these limits."""
    return _ContentChecker(
        OPERATORS,
        {op: op not in _OPERANDS_UNUSED for op in _HANDLERS},
        min_integer=MIN_INTEGER,
        max_integer=MAX_INTEGER,
        max_real=float(limits.max_real),
        min_real=float(limits.min_real or 0),
        max_string=limits.max_string,
        max_name=MAX_NAME,
        max_array=MAX_ARRAY_1B if limits.containers else None,
        max_dict=MAX_DICT_1B if limits.containers else None,
        max_nesting=MAX_NESTING,
    )


class ContentWalker:
    """Check page content streams and the Form XObjects they draw.

    Args:
        ctx: Validation context.
    """

    def __init__(self, ctx: ValidationContext):
        self.ctx = ctx
        self.walked_forms: set[tuple[int, int]] = set()
        self.painted_images: set[tuple[int, int]] = set()
        self._painted: set[tuple[Any, ...]] = set()
        self._in_progress: set[tuple[int, int]] = set()
        self._scratch = pikepdf.new()
        self.limits = LimitChecker(ctx.flavour)
        self.checker = content_checker(self.limits)
        # Tests that skip the ImageXObject role also skip image colour
        self.check_images = True

    def paint_image(
        self, image: pikepdf.Stream, colour_spaces: Any, where: str
    ) -> None:
        """Check the colour of an image painted with the given resources."""
        key = (image.objgen, _defaults_key(colour_spaces))
        self.painted_images.add(image.objgen)
        if not self.check_images or key in self._painted:
            return
        self._painted.add(key)
        check_image_colour(image, colour_spaces, self.ctx, where)

    def walk_page(self, page: pikepdf.Page, where: str) -> None:
        """Check the (concatenated) content streams of a page."""
        obj = page.obj
        if '/Contents' not in obj:
            return
        resources, explicit = _page_resources(obj, self.ctx.max_depth)
        walk = _StreamWalk(
            self,
            _Resources(resources, explicit, "inherited from the page tree"),
            GraphicsState(),
            0,
            0,
            f'{where} content',
        )
        contents = obj.get('/Contents')
        if isinstance(contents, pikepdf.Array):
            if not all(isinstance(part, pikepdf.Stream) for part in contents):
                walk.deny(
                    'pikepdf:content-parse', "page /Contents has an item not a stream"
                )
                return
            # Parse the concatenation as one stream: pikepdf reports syntax
            # problems (such as a truncated token) only when parsing a stream.
            try:
                data = b'\n'.join(part.read_bytes() for part in contents)
            except pikepdf.PdfError as e:
                walk.deny('pikepdf:content-parse', f"cannot read page content: {e}")
                return
            contents = self._scratch.make_stream(data)
        if not isinstance(contents, pikepdf.Stream):
            walk.deny('pikepdf:content-parse', "page /Contents is not a stream")
            return
        walk.run(contents)

    def walk_form(
        self,
        form: pikepdf.Stream,
        state: GraphicsState,
        base_depth: int,
        recursion: int,
        where: str,
    ) -> None:
        """Check a Form XObject drawn with graphics state *state*.

        A form is walked again only when drawn with a different text
        rendering mode or font, since only those change what it records.
        """
        ctx = self.ctx
        objgen = form.objgen
        if objgen in self._in_progress:
            ctx.deny('pikepdf:form-cycle', where, "Form XObject draws itself")
            return
        if recursion > MAX_FORM_DEPTH:
            ctx.deny(
                'pikepdf:form-depth',
                where,
                f"Form XObjects nested deeper than {MAX_FORM_DEPTH}",
                'unsupported',
            )
            return
        key = (
            objgen,
            state.tr,
            id(state.font) if state.font else None,
            state.overprint,
        )
        relative = ctx.forms.get(key)
        if relative is None:
            self.walked_forms.add(objgen)
            self._in_progress.add(objgen)
            try:
                if '/Resources' in form:
                    resources = _Resources(form.get('/Resources'), True)
                else:
                    resources = _Resources(
                        pikepdf.Dictionary(),
                        ctx.flavour.part != 1,
                        "a Form XObject without /Resources",
                    )
                walk = _StreamWalk(
                    self,
                    resources,
                    state,
                    base_depth,
                    recursion,
                    f'{ctx.describe(form)} (FormXObject) content',
                )
                relative = walk.run(form)
            finally:
                self._in_progress.discard(objgen)
            ctx.forms[key] = relative
        elif base_depth + relative > MAX_Q_DEPTH:
            ctx.deny(
                ctx.rule('6.1.12-8', '6.1.13-8'),
                where,
                f"q/Q nesting exceeds {MAX_Q_DEPTH} inside the Form XObject",
            )

    def walk_unreached_form(self, form: pikepdf.Stream) -> None:
        """Check a Form XObject that no content stream has drawn so far."""
        if form.objgen in self.walked_forms:
            return
        self.walk_form(
            form, GraphicsState(), 0, 1, f'{self.ctx.describe(form)} (FormXObject)'
        )


def _defaults_key(colour_spaces: Any) -> tuple[bytes | None, ...]:
    """Identify the /Default* colour spaces of a /ColorSpace resource dict."""
    if not isinstance(colour_spaces, pikepdf.Dictionary):
        return ()
    return tuple(
        _unparse(colour_spaces.get(key)) if key in colour_spaces else None
        for key in DEFAULT_SPACES.values()
    )


def _unparse(value: Any) -> bytes:
    if isinstance(value, pikepdf.Object):
        return value.unparse()
    return b'null'


def _page_resources(page: pikepdf.Dictionary, max_depth: int) -> tuple[Any, bool]:
    """Return (resources, explicit) of a page.

    Resources inherited from the page tree are not "explicitly associated"
    with the page's content for ISO 19005-2 rule 6.2.2-2 (veraPDF reports
    them), but PDF/A-1 has no such rule.
    """
    if '/Resources' in page:
        return page.get('/Resources'), True
    node = page
    seen: set[tuple[int, int]] = set()
    for _ in range(max_depth):
        parent = node.get('/Parent')
        if not isinstance(parent, pikepdf.Dictionary) or parent.objgen in seen:
            break
        seen.add(parent.objgen)
        if '/Resources' in parent:
            return parent.get('/Resources'), False
        node = parent
    return None, False
