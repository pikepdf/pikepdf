# SPDX-FileCopyrightText: 2026 James R. Barlow
# SPDX-License-Identifier: MPL-2.0

"""Font checks: dictionary rules when a font is reached, glyph rules at the end.

`load_font` runs the dictionary-tier checks once per font (cached by objgen)
and returns a `FontInfo` that decodes strings shown with the font. The
content walker records every code shown and the text rendering modes it was
shown in; `finalize_fonts` then checks, for each used code, that the glyph
exists, is not ``.notdef``, and has a width that agrees with the font
dictionary.

Only these shapes are accepted; any other font is reported as unsupported:

- Type 0 with Identity-H or an embedded CMap, over a CIDFontType2 (TrueType,
  FontFile2 or FontFile3 /OpenType) or a CIDFontType0 (CFF, FontFile3
  /CIDFontType0C or /OpenType).
- Simple TrueType (FontFile2), symbolic or non-symbolic.
- Simple Type 1 with a Type 1 program (FontFile) or a CFF program
  (FontFile3 /Type1C).

Text rendering mode 3 exempts a code from the glyph-present and width rules,
as in veraPDF; ``.notdef`` and dictionary rules apply regardless.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, NamedTuple

from fontTools import agl

import pikepdf
from pikepdf.pdfa._cmap import (
    CMapError,
    EmbeddedCMap,
    parse_embedded_cmap,
)
from pikepdf.pdfa._context import ValidationContext
from pikepdf.pdfa._encodings import (
    MAC_ROMAN,
    STANDARD,
    WIN_ANSI,
    DifferencesError,
    encoding_table,
    mac_roman_codes,
    parse_differences,
)
from pikepdf.pdfa._fontprogram import (
    CFFProgram,
    FontProgramAmbiguity,
    FontProgramError,
    GlyphSource,
    TrueTypeProgram,
    Type1Program,
)
from pikepdf.pdfa._report import FindingKind
from pikepdf.pdfa._shallow import pdf_repr

INVISIBLE = 3
WIDTH_TOLERANCE = 1
DEFAULT_CID_WIDTH = 1000
MAX_CODES_IN_MESSAGE = 10

SUBSET_PREFIX = re.compile(r'^[A-Z]{6}\+')

FONT_SUBTYPES = frozenset(
    {
        '/Type1',
        '/MMType1',
        '/TrueType',
        '/Type3',
        '/Type0',
        '/CIDFontType0',
        '/CIDFontType2',
    }
)
IDENTITY_CMAPS = frozenset({'/Identity-H', '/Identity-V'})
# ISO 32000-1:2008 Table 118, the predefined CMaps a PDF/A-2 file may use
# without embedding them.
PREDEFINED_CMAPS = frozenset(
    '/' + name
    for name in [
        'GB-EUC-H',
        'GB-EUC-V',
        'GBpc-EUC-H',
        'GBpc-EUC-V',
        'GBK-EUC-H',
        'GBK-EUC-V',
        'GBKp-EUC-H',
        'GBKp-EUC-V',
        'GBK2K-H',
        'GBK2K-V',
        'UniGB-UCS2-H',
        'UniGB-UCS2-V',
        'UniGB-UTF16-H',
        'UniGB-UTF16-V',
        'B5pc-H',
        'B5pc-V',
        'HKscs-B5-H',
        'HKscs-B5-V',
        'ETen-B5-H',
        'ETen-B5-V',
        'ETenms-B5-H',
        'ETenms-B5-V',
        'CNS-EUC-H',
        'CNS-EUC-V',
        'UniCNS-UCS2-H',
        'UniCNS-UCS2-V',
        'UniCNS-UTF16-H',
        'UniCNS-UTF16-V',
        '83pv-RKSJ-H',
        '90ms-RKSJ-H',
        '90ms-RKSJ-V',
        '90msp-RKSJ-H',
        '90msp-RKSJ-V',
        '90pv-RKSJ-H',
        'Add-RKSJ-H',
        'Add-RKSJ-V',
        'EUC-H',
        'EUC-V',
        'Ext-RKSJ-H',
        'Ext-RKSJ-V',
        'H',
        'V',
        'UniJIS-UCS2-H',
        'UniJIS-UCS2-V',
        'UniJIS-UCS2-HW-H',
        'UniJIS-UCS2-HW-V',
        'UniJIS-UTF16-H',
        'UniJIS-UTF16-V',
        'KSC-EUC-H',
        'KSC-EUC-V',
        'KSCms-UHC-H',
        'KSCms-UHC-V',
        'KSCms-UHC-HW-H',
        'KSCms-UHC-HW-V',
        'KSCpc-EUC-H',
        'UniKS-UCS2-H',
        'UniKS-UCS2-V',
        'UniKS-UTF16-H',
        'UniKS-UTF16-V',
    ]
)
STANDARD_14 = frozenset(
    {
        'Courier',
        'Courier-Bold',
        'Courier-BoldOblique',
        'Courier-Oblique',
        'Helvetica',
        'Helvetica-Bold',
        'Helvetica-BoldOblique',
        'Helvetica-Oblique',
        'Symbol',
        'Times-Bold',
        'Times-BoldItalic',
        'Times-Italic',
        'Times-Roman',
        'ZapfDingbats',
    }
)
SIMPLE_BASE_ENCODINGS = {
    '/StandardEncoding': STANDARD,
    '/WinAnsiEncoding': WIN_ANSI,
    '/MacRomanEncoding': MAC_ROMAN,
}
TRUETYPE_BASE_ENCODINGS = frozenset({'/WinAnsiEncoding', '/MacRomanEncoding'})
FLAG_SYMBOLIC = 1 << 2
FLAG_NONSYMBOLIC = 1 << 5
SYMBOL_OFFSETS = (0, 0xF000, 0xF100, 0xF200)

# Rule ids: (ISO 19005-1 clause, ISO 19005-2/-3 clause, local fallback name)
RULES: dict[str, tuple[str | None, str | None]] = {
    'type': ('6.3.2-1', '6.2.11.2-1'),
    'subtype': ('6.3.2-2', '6.2.11.2-2'),
    'basefont': ('6.3.2-3', '6.2.11.2-3'),
    'firstchar': ('6.3.2-4', '6.2.11.2-4'),
    'lastchar': ('6.3.2-5', '6.2.11.2-5'),
    'widths': ('6.3.2-6', '6.2.11.2-6'),
    'fontfile-subtype': ('6.3.2-7', '6.2.11.2-7'),
    'cidsysteminfo': ('6.3.3.1-1', '6.2.11.3.1-1'),
    'cidtogidmap': ('6.3.3.2-1', '6.2.11.3.2-1'),
    'cmap-embedded': ('6.3.3.3-1', '6.2.11.3.3-1'),
    'cmap-wmode': ('6.3.3.3-2', '6.2.11.3.3-2'),
    'cmap-usecmap': (None, '6.2.11.3.3-3'),
    'cid-limit': ('6.1.12-10', '6.1.13-10'),
    'embedded': ('6.3.4-1', '6.2.11.4.1-1'),
    'glyph': ('6.3.5-1', '6.2.11.4.1-2'),
    'charset': ('6.3.5-2', '6.2.11.4.2-1'),
    'cidset': ('6.3.5-3', '6.2.11.4.2-2'),
    'width': ('6.3.6-1', '6.2.11.5-1'),
    'tt-nonsymbolic-encoding': ('6.3.7-1', '6.2.11.6-2'),
    'tt-symbolic-encoding': ('6.3.7-2', '6.2.11.6-3'),
    'tt-symbolic-cmap': ('6.3.7-3', '6.2.11.6-4'),
    'tt-nonsymbolic-cmap': (None, '6.2.11.6-1'),
    'notdef': (None, '6.2.11.8-1'),
    'name-utf8': (None, '6.1.8-1'),
}


def rule_id(ctx: ValidationContext, key: str) -> str:
    """Return the rule id of a font rule for the flavour being checked.

    Keys not in `RULES` (and rules without an equivalent in the flavour)
    become local ``pikepdf:<key>`` ids.
    """
    part1, part23 = RULES.get(key, (None, None))
    return ctx.rule(part1, part23, key)


class GlyphRef(NamedTuple):
    """One character code shown by a text operator.

    Attributes:
        code: The character code.
        cid: For composite fonts, the CID it selects; otherwise None.
    """

    code: int
    cid: int | None = None


class _Resolved(NamedTuple):
    gid: int | None
    missing: bool = False  # True: a name or gid that the program lacks
    ambiguous: bool = False  # True: readers may select different glyphs


def _name_text(obj: Any) -> str | None:
    """Return a name's text without the slash, or None if not UTF-8."""
    try:
        return str(obj)[1:]
    except UnicodeDecodeError:
        return None


def _number(obj: Any) -> float | None:
    obj = pikepdf.unbox(obj)
    if isinstance(obj, bool):
        return None
    if isinstance(obj, int | Decimal):
        return float(obj)
    return None


def _integer(obj: Any) -> int | None:
    obj = pikepdf.unbox(obj)
    if isinstance(obj, int) and not isinstance(obj, bool):
        return int(obj)
    return None


def _is_standard_14(font: pikepdf.Dictionary) -> bool:
    """True for a simple font naming a standard 14 font and not embedded."""
    base_font = font.get('/BaseFont')
    if not isinstance(base_font, pikepdf.Name) or _name_text(base_font) not in (
        STANDARD_14
    ):
        return False
    descriptor = font.get('/FontDescriptor')
    return not isinstance(descriptor, pikepdf.Dictionary) or not any(
        key in descriptor for key in ('/FontFile', '/FontFile2', '/FontFile3')
    )


def parse_cid_widths(w: Any) -> tuple[dict[int, float], set[int]]:
    """Parse a CIDFont /W array.

    Both forms are accepted: ``c [w1 w2 ...]`` and ``cfirst clast w``.

    Returns:
        The width of each CID, and the CIDs given more than one width.
        Readers disagree on which of those widths applies.

    Raises:
        ValueError: If the array is malformed.
    """
    if not isinstance(w, pikepdf.Array):
        raise ValueError("/W is not an array")
    items = list(w)
    widths: dict[int, float] = {}
    conflicts: set[int] = set()

    def set_width(cid: int, width: float) -> None:
        if widths.setdefault(cid, width) != width:
            conflicts.add(cid)

    i = 0
    total = 0
    while i < len(items):
        first = _integer(items[i])
        if first is None or first < 0 or i + 1 >= len(items):
            raise ValueError(f"/W entry {i} is not a CID")
        second = items[i + 1]
        if isinstance(second, pikepdf.Array):
            for offset, value in enumerate(second):
                width = _number(value)
                if width is None:
                    raise ValueError(f"/W entry {i + 1} has a non-numeric width")
                set_width(first + offset, width)
            total += len(second)
            i += 2
            continue
        last = _integer(second)
        if last is None or last < first or i + 2 >= len(items):
            raise ValueError(f"/W entry {i + 1} is not a CID range")
        width = _number(items[i + 2])
        if width is None:
            raise ValueError(f"/W entry {i + 2} is not a width")
        total += last - first + 1
        if total > 65536 * 4:
            raise ValueError("/W is implausibly large")
        for cid in range(first, last + 1):
            set_width(cid, width)
        i += 3
    return widths, conflicts


def _cidset_bits(data: bytes) -> set[int]:
    return {
        byte_index * 8 + bit
        for byte_index, byte in enumerate(data)
        if byte
        for bit in range(8)
        if byte & (0x80 >> bit)
    }


@dataclass
class FontInfo:
    """A font reached by the walker, and the codes shown with it.

    Attributes:
        where: Location used in findings.
        kind: ``type0``, ``truetype``, ``type1`` or ``unsupported``.
        ok: False if the font was denied; strings shown with it are then
            not decoded or checked further.
        subset: True if BaseFont has a subset prefix (``ABCDEF+``).
        program: The embedded font program (of the descendant CIDFont for
            Type 0 fonts), once loaded.
        usage: For each code shown, the text rendering modes it was shown in.
    """

    where: str
    kind: str = 'unsupported'
    ok: bool = False
    subset: bool = False
    program: GlyphSource | None = None
    usage: dict[int, set[int]] = field(default_factory=dict)
    # Type 0 details
    cid_subtype: str = ''
    cmap: EmbeddedCMap | None = None
    cid_to_gid: bytes | None = None  # None: Identity
    cid_widths: dict[int, float] = field(default_factory=dict)
    cid_width_conflicts: set[int] = field(default_factory=set)
    default_width: float = DEFAULT_CID_WIDTH
    cidset: set[int] | None = None
    cid_of: dict[int, int] = field(default_factory=dict)
    # simple font details
    first_char: int = 0
    widths: list[float | None] = field(default_factory=list)
    code_to_name: Mapping[int, str] = field(default_factory=dict)
    symbolic: bool = False
    # Symbolic TrueType: SYMBOL_OFFSETS whose 256 codes the (3,0) cmap covers
    symbol_offsets: tuple[int, ...] = ()
    charset: set[str] | None = None
    reported: set[str] = field(default_factory=set)

    def deny_once(
        self,
        ctx: ValidationContext,
        key: str,
        message: str,
        kind: FindingKind = 'violation',
    ) -> None:
        """Report a finding for this font, at most once per rule key."""
        if key in self.reported:
            return
        self.reported.add(key)
        ctx.deny(rule_id(ctx, key), self.where, message, kind)

    # --- decoding -----------------------------------------------------------

    def decode_string(self, data: bytes, ctx: ValidationContext) -> list[GlyphRef]:
        """Split a string shown with this font into codes.

        Decoding problems are reported (once per font) and the string is
        then skipped.
        """
        if not self.ok:
            return []
        if self.kind != 'type0':
            return [GlyphRef(b) for b in data]
        if self.cmap is None:
            if len(data) % 2:
                self.deny_once(
                    ctx,
                    'text-decode',
                    "a string shown with an Identity-H font has an odd length",
                )
                return []
            return [
                GlyphRef(code, code)
                for code in (
                    int.from_bytes(data[i : i + 2], 'big')
                    for i in range(0, len(data), 2)
                )
            ]
        try:
            pairs = self.cmap.decode(data)
        except CMapError as e:
            if e.reason == 'unmapped':
                self.deny_once(
                    ctx, 'notdef', f"{e}; it selects the .notdef glyph (CID 0)"
                )
            elif e.reason == 'ambiguous':
                self.deny_once(ctx, 'font-cmap-ambiguous', str(e), 'unsupported')
            else:
                self.deny_once(ctx, 'text-decode', str(e))
            return []
        return [GlyphRef(code, cid) for code, cid in pairs]

    def record(self, refs: list[GlyphRef], mode: int) -> None:
        """Record that *refs* were shown in text rendering mode *mode*."""
        for ref in refs:
            self.usage.setdefault(ref.code, set()).add(mode)
            if ref.cid is not None:
                self.cid_of[ref.code] = ref.cid

    # --- glyph resolution ---------------------------------------------------

    def _resolve_cid(self, cid: int) -> _Resolved:
        program = self.program
        assert program is not None
        if self.cid_subtype == '/CIDFontType2':
            if self.cid_to_gid is None:
                gid = cid
            else:
                offset = 2 * cid
                if offset + 2 > len(self.cid_to_gid):
                    return _Resolved(None)
                gid = int.from_bytes(self.cid_to_gid[offset : offset + 2], 'big')
            return _Resolved(gid)
        gid_for_cid = program.gid_for_cid(cid)
        if gid_for_cid is None:
            return _Resolved(None, missing=True)
        return _Resolved(gid_for_cid)

    def _resolve_simple(self, code: int) -> _Resolved:
        program = self.program
        assert program is not None
        if self.kind == 'type1':
            name = self.code_to_name.get(code)
            if name is None or name == '.notdef':
                return _Resolved(None)
            gid = program.gid_for_name(name)
            return _Resolved(gid, missing=gid is None)
        tables = program.cmap_tables()
        if self.symbolic:
            if (3, 0) in tables:
                # A (3,0) subtable maps either single-byte codes or codes
                # offset by 0xF000, 0xF100 or 0xF200; with more than one of
                # these ranges, readers may choose different ones.
                gids = {
                    program.lookup_cmap(3, 0, offset + code) or 0
                    for offset in self.symbol_offsets
                }
                if len(gids) > 1:
                    return _Resolved(None, ambiguous=True)
                gid = gids.pop() if gids else 0
                return _Resolved(gid or None)
            return _Resolved(program.lookup_cmap(1, 0, code))
        name = self.code_to_name.get(code)
        if name is None or name == '.notdef':
            return _Resolved(None)
        if (3, 1) in tables:
            text = agl.toUnicode(name)
            if len(text) != 1:
                return _Resolved(None)
            return _Resolved(program.lookup_cmap(3, 1, ord(text)))
        mac_code = mac_roman_codes().get(name)
        if mac_code is None:
            return _Resolved(None)
        return _Resolved(program.lookup_cmap(1, 0, mac_code))

    def _dict_width(self, code: int, cid: int | None) -> float | None:
        if self.kind == 'type0':
            assert cid is not None
            return self.cid_widths.get(cid, self.default_width)
        index = code - self.first_char
        if 0 <= index < len(self.widths):
            return self.widths[index]
        return None

    # --- end of document checks ---------------------------------------------

    def finalize(self, ctx: ValidationContext) -> None:
        """Check the glyphs of every code shown with this font."""
        if not self.ok or self.program is None or not self.usage:
            return
        program = self.program
        notdef: list[int] = []
        missing: list[int] = []
        ambiguous: list[int] = []
        widths: list[str] = []
        ambiguous_widths: list[int] = []
        unset_cids: list[int] = []
        for code, modes in sorted(self.usage.items()):
            visible = any(mode != INVISIBLE for mode in modes)
            cid = self.cid_of.get(code) if self.kind == 'type0' else None
            if (
                self.cidset is not None
                and ctx.flavour.part == 1
                and cid is not None
                and cid not in self.cidset
            ):
                unset_cids.append(cid)
            try:
                if cid is not None:
                    resolved = self._resolve_cid(cid)
                else:
                    resolved = self._resolve_simple(code)
                gid = resolved.gid
                if gid is not None and not resolved.missing and gid != 0:
                    present = program.has_gid(gid)
                else:
                    present = False
            except FontProgramError as e:
                self.deny_once(ctx, 'font-program', str(e), 'unsupported')
                return
            if resolved.ambiguous:
                ambiguous.append(code)
                continue
            # veraPDF names CID 0 .notdef whatever glyph it maps to
            if cid == 0 or gid == 0 or (gid is None and not resolved.missing):
                notdef.append(code)
                continue
            if not present:
                # veraPDF exempts rendering mode 3 from the glyph-present
                # rule, but may then report the glyph as .notdef; deny
                # regardless of the mode.
                (missing if visible else notdef).append(code)
                continue
            if not visible:
                continue
            assert gid is not None
            if cid in self.cid_width_conflicts:
                ambiguous_widths.append(code)
                continue
            dict_width = self._dict_width(code, cid)
            try:
                program_width = program.advance_1000(gid)
            except FontProgramError as e:
                self.deny_once(ctx, 'font-program', str(e), 'unsupported')
                return
            if dict_width is None:
                widths.append(f"{code} (no width in the font dictionary)")
            elif (
                program_width is not None
                and abs(program_width - dict_width) > WIDTH_TOLERANCE
            ):
                widths.append(
                    f"{code} (dictionary {dict_width:g}, program {program_width:g})"
                )
        self._report(ctx, 'notdef', notdef, "codes select the .notdef glyph")
        self._report(
            ctx, 'glyph', missing, "codes select glyphs the font program lacks"
        )
        if widths:
            shown = ', '.join(widths[:MAX_CODES_IN_MESSAGE])
            more = len(widths) - MAX_CODES_IN_MESSAGE
            ctx.deny(
                rule_id(ctx, 'width'),
                self.where,
                "glyph widths disagree with the font program: "
                + shown
                + (f" and {more} more" if more > 0 else ''),
            )
        if ambiguous:
            self._report(
                ctx,
                'font-symbolic-cmap-ambiguous',
                ambiguous,
                "the (3,0) cmap maps codes in more than one range, which select "
                "different glyphs for",
                'unsupported',
            )
        if ambiguous_widths:
            self._report(
                ctx,
                'font-widths-ambiguous',
                ambiguous_widths,
                "/W gives these codes' CIDs more than one width",
                'unsupported',
            )
        if unset_cids:
            self._report(
                ctx, 'cidset', sorted(set(unset_cids)), "CIDs used but not in /CIDSet"
            )

    def _report(
        self,
        ctx: ValidationContext,
        key: str,
        codes: list[int],
        message: str,
        kind: FindingKind = 'violation',
    ) -> None:
        if not codes:
            return
        shown = ', '.join(str(c) for c in codes[:MAX_CODES_IN_MESSAGE])
        more = len(codes) - MAX_CODES_IN_MESSAGE
        suffix = f" and {more} more" if more > 0 else ''
        ctx.deny(rule_id(ctx, key), self.where, f"{message}: {shown}{suffix}", kind)


# --- loading -------------------------------------------------------------------


class _Loader:
    """Dictionary-tier checks of one font; fills in a FontInfo."""

    def __init__(self, ctx: ValidationContext, info: FontInfo):
        self.ctx = ctx
        self.info = info
        self.failed = False

    def deny(
        self,
        key: str,
        message: str,
        kind: FindingKind = 'violation',
        where: str | None = None,
    ) -> None:
        self.failed = True
        self.ctx.deny(rule_id(self.ctx, key), where or self.info.where, message, kind)

    def unsupported(self, key: str, message: str) -> None:
        self.deny(key, message, 'unsupported')

    # --- common -------------------------------------------------------------

    def common(self, font: pikepdf.Dictionary, what: str) -> str | None:
        """Check /Type, /Subtype and /BaseFont; return the subtype."""
        font_type = pikepdf.unbox(font.get('/Type'))
        if font_type != pikepdf.Name.Font:
            self.deny('type', f"{what} /Type is {pdf_repr(font_type)}, not /Font")
        subtype = pikepdf.unbox(font.get('/Subtype'))
        subtype_text = str(subtype) if isinstance(subtype, pikepdf.Name) else None
        if subtype_text not in FONT_SUBTYPES:
            self.deny(
                'subtype', f"{what} /Subtype {pdf_repr(subtype)} is not a font type"
            )
            return None
        assert subtype_text is not None
        base_font = font.get('/BaseFont')
        if subtype_text != '/Type3':
            if not isinstance(base_font, pikepdf.Name):
                self.deny('basefont', f"{what} has no /BaseFont name")
            else:
                text = _name_text(base_font)
                if text is None:
                    if self.ctx.flavour.part == 1:
                        self.unsupported(
                            'font-name', f"{what} /BaseFont is not valid UTF-8"
                        )
                    else:
                        self.deny('name-utf8', f"{what} /BaseFont is not valid UTF-8")
                elif SUBSET_PREFIX.match(text):
                    self.info.subset = True
        return subtype_text

    def descriptor(
        self, font: pikepdf.Dictionary, what: str
    ) -> tuple[pikepdf.Dictionary, int] | None:
        descriptor = font.get('/FontDescriptor')
        if not isinstance(descriptor, pikepdf.Dictionary):
            self.unsupported(
                'embedded', f"{what} has no /FontDescriptor, so it is not embedded"
            )
            return None
        font_name = descriptor.get('/FontName')
        if isinstance(font_name, pikepdf.Name) and _name_text(font_name) is None:
            if self.ctx.flavour.part == 1:
                self.unsupported('font-name', f"{what} /FontName is not valid UTF-8")
            else:
                self.deny('name-utf8', f"{what} /FontName is not valid UTF-8")
        flags = _integer(descriptor.get('/Flags'))
        if flags is None:
            self.unsupported('font-flags', f"{what} font descriptor has no /Flags")
            return None
        return descriptor, flags

    def font_file(
        self, descriptor: pikepdf.Dictionary, what: str
    ) -> tuple[str, str | None, bytes] | None:
        """Return (key, FontFile3 subtype, data) of the embedded program."""
        present = [
            key
            for key in ('/FontFile', '/FontFile2', '/FontFile3')
            if key in descriptor
        ]
        if not present:
            self.unsupported('embedded', f"{what} is not embedded")
            return None
        if len(present) > 1:
            self.unsupported('font-file', f"{what} has {', '.join(present)}")
            return None
        key = present[0]
        stream = descriptor.get(key)
        if not isinstance(stream, pikepdf.Stream):
            self.deny('embedded', f"{what} {key} is not a stream")
            return None
        subtype: str | None = None
        if key == '/FontFile3':
            value = stream.get('/Subtype')
            subtype = str(value) if isinstance(value, pikepdf.Name) else None
            allowed = {'/Type1C', '/CIDFontType0C'}
            if self.ctx.flavour.part != 1:
                allowed.add('/OpenType')
            if subtype is None:
                self.unsupported('font-file', f"{what} /FontFile3 has no /Subtype")
                return None
            if subtype not in allowed:
                self.deny('fontfile-subtype', f"{what} /FontFile3 /Subtype {subtype}")
                return None
        try:
            data = stream.read_bytes()
        except pikepdf.PdfError as e:
            self.unsupported('font-program', f"{what} {key} cannot be read: {e}")
            return None
        return key, subtype, data

    def program(self, factory: Callable[[bytes], Any], data: bytes, what: str) -> Any:
        try:
            return factory(data)
        except FontProgramAmbiguity as e:
            self.unsupported('font-program-ambiguous', f"{what}: {e}")
            return None
        except FontProgramError as e:
            self.unsupported('font-program', f"{what}: {e}")
            return None

    # --- simple fonts -------------------------------------------------------

    def simple_widths(self, font: pikepdf.Dictionary) -> None:
        if _is_standard_14(font):
            # veraPDF exempts the standard 14 fonts from /FirstChar, /LastChar
            # and /Widths; they are denied as not embedded instead.
            return
        first = _integer(font.get('/FirstChar'))
        last = _integer(font.get('/LastChar'))
        if first is None:
            self.deny('firstchar', "simple font has no integer /FirstChar")
        if last is None:
            self.deny('lastchar', "simple font has no integer /LastChar")
        widths = font.get('/Widths')
        if not isinstance(widths, pikepdf.Array):
            self.deny('widths', "simple font has no /Widths array")
            return
        if first is None or last is None:
            return
        if len(widths) != last - first + 1:
            self.deny(
                'widths',
                f"/Widths has {len(widths)} entries; /FirstChar {first} and "
                f"/LastChar {last} require {last - first + 1}",
            )
            return
        values = [_number(w) for w in widths]
        if any(v is None for v in values):
            self.deny('font-widths', "/Widths contains a non-numeric entry")
            return
        self.info.first_char = first
        self.info.widths = values

    def symbolic_flag(self, flags: int, what: str) -> bool | None:
        symbolic = bool(flags & FLAG_SYMBOLIC)
        nonsymbolic = bool(flags & FLAG_NONSYMBOLIC)
        if symbolic == nonsymbolic:
            self.unsupported(
                'font-flags',
                f"{what} /Flags {flags} sets "
                + ("both" if symbolic else "neither")
                + " of the symbolic and nonsymbolic bits",
            )
            return None
        return symbolic

    def truetype(self, font: pikepdf.Dictionary) -> None:
        info = self.info
        what = "TrueType font"
        self.simple_widths(font)
        found = self.descriptor(font, what)
        if found is None:
            return
        descriptor, flags = found
        symbolic = self.symbolic_flag(flags, what)
        file = self.font_file(descriptor, what)
        if file is None or symbolic is None:
            return
        key, subtype, data = file
        if key != '/FontFile2' and subtype != '/OpenType':
            self.unsupported('font-file', f"{what} has a {key} {subtype or ''} program")
            return
        program = self.program(TrueTypeProgram, data, what)
        if program is None:
            return
        if program.is_cff:
            self.unsupported('font-file', f"{what} has CFF outlines")
            return
        info.symbolic = symbolic
        tables = program.cmap_tables()
        encoding = pikepdf.unbox(font.get('/Encoding'))
        if symbolic:
            if encoding is not None:
                self.deny(
                    'tt-symbolic-encoding', "symbolic TrueType font has an /Encoding"
                )
            if self.ctx.flavour.part == 1:
                if len(tables) != 1:
                    self.deny(
                        'tt-symbolic-cmap',
                        f"symbolic TrueType program has {len(tables)} cmap "
                        "subtables, not exactly one",
                    )
            elif len(tables) != 1 and (3, 0) not in tables:
                self.deny(
                    'tt-symbolic-cmap',
                    f"symbolic TrueType program has {len(tables)} cmap subtables "
                    "and none is (3,0)",
                )
            if (3, 0) not in tables and (1, 0) not in tables:
                self.unsupported(
                    'font-cmap',
                    "symbolic TrueType program has no (3,0) or (1,0) cmap subtable",
                )
            try:
                ranges = program.cmap_ranges(3, 0)
            except FontProgramError as e:
                self.unsupported('font-program', f"{what}: {e}")
                return
            info.symbol_offsets = tuple(
                offset
                for offset in SYMBOL_OFFSETS
                if any(low <= offset + 0xFF and offset <= high for low, high in ranges)
            )
        else:
            self.nonsymbolic_encoding(encoding, tables)
        info.program = program

    def nonsymbolic_encoding(
        self, encoding: Any, tables: list[tuple[int, int]]
    ) -> None:
        info = self.info
        base: str | None = None
        differences: dict[int, str] = {}
        if isinstance(encoding, pikepdf.Name):
            base = str(encoding)
        elif isinstance(encoding, pikepdf.Dictionary):
            base_obj = encoding.get('/BaseEncoding')
            base = str(base_obj) if isinstance(base_obj, pikepdf.Name) else None
            if '/Differences' in encoding:
                if self.ctx.flavour.part == 1:
                    self.deny(
                        'tt-nonsymbolic-encoding',
                        "non-symbolic TrueType font encoding has /Differences",
                    )
                    return
                try:
                    differences = parse_differences(encoding.get('/Differences'))
                except DifferencesError as e:
                    self.deny('font-encoding', str(e))
                    return
                bad = sorted(
                    name for name in differences.values() if name not in agl.AGL2UV
                )
                if bad:
                    self.deny(
                        'tt-nonsymbolic-encoding',
                        "/Differences names outside the Adobe Glyph List: "
                        + ', '.join(bad[:MAX_CODES_IN_MESSAGE]),
                    )
                    return
                if (3, 1) not in tables:
                    self.unsupported(
                        'font-cmap',
                        "TrueType font with /Differences has no (3,1) cmap subtable",
                    )
                    return
        if base not in TRUETYPE_BASE_ENCODINGS:
            self.deny(
                'tt-nonsymbolic-encoding',
                f"non-symbolic TrueType font encoding is {base or pdf_repr(encoding)}, "
                "not MacRomanEncoding or WinAnsiEncoding",
            )
            return
        assert base is not None
        if self.ctx.flavour.part != 1:
            has_30 = (3, 0) in tables
            if len(tables) <= (1 if has_30 else 0):
                self.deny(
                    'tt-nonsymbolic-cmap',
                    "non-symbolic TrueType program has no non-symbolic cmap subtable",
                )
        if (3, 1) not in tables and (1, 0) not in tables:
            self.unsupported(
                'font-cmap',
                "non-symbolic TrueType program has no (3,1) or (1,0) cmap subtable",
            )
            return
        table = dict(encoding_table(SIMPLE_BASE_ENCODINGS[base]))
        table.update(differences)
        info.code_to_name = table

    def type1(self, font: pikepdf.Dictionary) -> None:
        info = self.info
        what = "Type 1 font"
        self.simple_widths(font)
        found = self.descriptor(font, what)
        if found is None:
            return
        descriptor, flags = found
        if self.symbolic_flag(flags, what) is None:
            return
        file = self.font_file(descriptor, what)
        if file is None:
            return
        key, subtype, data = file
        program: CFFProgram | Type1Program | None
        if key == '/FontFile':
            program = self.program(Type1Program, data, what)
        elif subtype == '/Type1C':
            program = self.program(CFFProgram, data, what)
        else:
            self.unsupported('font-file', f"{what} has a {key} {subtype or ''} program")
            return
        if program is None:
            return
        if program.is_cid_keyed:
            self.unsupported('font-file', f"{what} has a CID-keyed CFF program")
            return
        try:
            builtin = program.builtin_encoding()
        except FontProgramError as e:
            self.unsupported('font-encoding', f"{what}: {e}")
            return
        base_table: Mapping[int, str] = (
            builtin if builtin is not None else encoding_table(STANDARD)
        )
        encoding = pikepdf.unbox(font.get('/Encoding'))
        differences: dict[int, str] = {}
        if isinstance(encoding, pikepdf.Dictionary):
            base_obj = pikepdf.unbox(encoding.get('/BaseEncoding'))
            encoding = base_obj
            try:
                if '/Differences' in font.Encoding:
                    differences = parse_differences(font.Encoding.Differences)
            except DifferencesError as e:
                self.deny('font-encoding', str(e))
                return
        if encoding is not None:
            name = str(encoding) if isinstance(encoding, pikepdf.Name) else None
            if name not in SIMPLE_BASE_ENCODINGS:
                self.unsupported(
                    'font-encoding', f"{what} encoding {pdf_repr(encoding)}"
                )
                return
            base_table = encoding_table(SIMPLE_BASE_ENCODINGS[name])
        table = dict(base_table)
        table.update(differences)
        info.code_to_name = table
        self.charset(descriptor, program)
        info.program = program

    def charset(self, descriptor: pikepdf.Dictionary, program: GlyphSource) -> None:
        if not self.info.subset:
            return
        charset = descriptor.get('/CharSet')
        if charset is None:
            if self.ctx.flavour.part == 1:
                self.deny('charset', "Type 1 font subset has no /CharSet")
            return
        if not isinstance(charset, pikepdf.String):
            self.deny('charset', "/CharSet is not a string")
            return
        text = bytes(charset).decode('latin-1')
        names = {name for name in text.split('/') if name}
        glyphs = set(program.glyph_names()) - {'.notdef'}
        names.discard('.notdef')
        if names != glyphs:
            extra = sorted(names - glyphs)
            lacking = sorted(glyphs - names)
            self.deny(
                'charset',
                "/CharSet does not list exactly the glyphs of the program"
                + (f"; not in program: {' '.join(extra[:10])}" if extra else '')
                + (f"; not in /CharSet: {' '.join(lacking[:10])}" if lacking else ''),
            )

    # --- composite fonts ----------------------------------------------------

    def type0(self, font: pikepdf.Dictionary) -> None:
        info = self.info
        descendants = font.get('/DescendantFonts')
        if not isinstance(descendants, pikepdf.Array) or len(descendants) != 1:
            self.deny('font-descendant', "Type 0 font needs one descendant font")
            return
        cidfont = descendants[0]
        if not isinstance(cidfont, pikepdf.Dictionary):
            self.deny('font-descendant', "Type 0 descendant font is not a dictionary")
            return
        subtype = self.common(cidfont, "CIDFont")
        if subtype not in ('/CIDFontType0', '/CIDFontType2'):
            if subtype is not None:
                self.deny('font-descendant', f"descendant font subtype {subtype}")
            return
        info.cid_subtype = subtype
        system_info = self.cid_system_info(cidfont.get('/CIDSystemInfo'), "CIDFont")
        self.encoding_cmap(pikepdf.unbox(font.get('/Encoding')), system_info)
        self.cid_widths(cidfont)
        if subtype == '/CIDFontType2':
            self.cid_to_gid_map(cidfont)
        found = self.descriptor(cidfont, "CIDFont")
        if found is None:
            return
        descriptor, _flags = found
        file = self.font_file(descriptor, "CIDFont")
        if file is None:
            return
        key, file_subtype, data = file
        program: Any = None
        if subtype == '/CIDFontType2':
            if key == '/FontFile2' or file_subtype == '/OpenType':
                program = self.program(TrueTypeProgram, data, "CIDFontType2")
                if program is not None and program.is_cff:
                    self.unsupported(
                        'font-file', "CIDFontType2 program has CFF outlines"
                    )
                    return
        elif file_subtype == '/CIDFontType0C':
            program = self.program(CFFProgram, data, "CIDFontType0")
        elif file_subtype == '/OpenType':
            opentype = self.program(TrueTypeProgram, data, "CIDFontType0")
            if opentype is not None:
                program = opentype.cff
                if program is None:
                    self.unsupported(
                        'font-file', "CIDFontType0 OpenType program has no CFF"
                    )
                    return
        if program is None:
            if not self.failed:
                self.unsupported(
                    'font-file', f"{subtype} with a {key} {file_subtype or ''} program"
                )
            return
        if subtype == '/CIDFontType0' and not program.is_cid_keyed:
            self.unsupported('font-file', "CIDFontType0 with a non-CID-keyed CFF")
            return
        self.cidset(descriptor, subtype, program)
        info.program = program

    def cid_system_info(self, value: Any, what: str) -> dict[str, Any] | None:
        if not isinstance(value, pikepdf.Dictionary):
            self.deny('cidsysteminfo', f"{what} has no /CIDSystemInfo dictionary")
            return None
        registry = value.get('/Registry')
        ordering = value.get('/Ordering')
        supplement = _integer(value.get('/Supplement'))
        if (
            not isinstance(registry, pikepdf.String)
            or not isinstance(ordering, pikepdf.String)
            or supplement is None
        ):
            self.deny('cidsysteminfo', f"{what} /CIDSystemInfo is incomplete")
            return None
        return {
            'Registry': bytes(registry).decode('latin-1'),
            'Ordering': bytes(ordering).decode('latin-1'),
            'Supplement': supplement,
        }

    def encoding_cmap(self, encoding: Any, system_info: dict[str, Any] | None) -> None:
        ctx = self.ctx
        if isinstance(encoding, pikepdf.Name):
            name = str(encoding)
            if name == '/Identity-H':
                return
            if name == '/Identity-V':
                self.unsupported('font-vertical', "vertical writing (Identity-V)")
                return
            if name in PREDEFINED_CMAPS and ctx.flavour.part != 1:
                self.unsupported('font-cmap', f"predefined CMap {name}")
                return
            self.deny('cmap-embedded', f"CMap {name} is not embedded")
            return
        if not isinstance(encoding, pikepdf.Stream):
            self.deny('cmap-embedded', f"Type 0 /Encoding {pdf_repr(encoding)}")
            return
        try:
            cmap = parse_embedded_cmap(encoding)
        except CMapError as e:
            if e.reason == 'cid-limit':
                self.deny('cid-limit', str(e))
            elif e.reason == 'ambiguous':
                self.unsupported('font-cmap-ambiguous', f"embedded CMap: {e}")
            elif e.reason == 'usecmap':
                use = pikepdf.unbox(encoding.get('/UseCMap'))
                if isinstance(use, pikepdf.Name) and str(use) in PREDEFINED_CMAPS:
                    self.unsupported('font-cmap', f"{e}: {use}")
                elif use is None or ctx.flavour.part == 1:
                    self.unsupported('cmap-usecmap', str(e))
                else:
                    self.deny('cmap-usecmap', f"{e}: {pdf_repr(use)}")
            else:
                self.unsupported('font-cmap', f"embedded CMap: {e}")
            return
        dict_wmode = _integer(encoding.get('/WMode', 0))
        stream_wmode = cmap.wmode if cmap.wmode is not None else 0
        if dict_wmode != stream_wmode:
            self.deny(
                'cmap-wmode',
                f"CMap dictionary /WMode {dict_wmode} differs from the embedded "
                f"CMap's WMode {stream_wmode}",
            )
        elif stream_wmode != 0:
            self.unsupported('font-vertical', "vertical writing (WMode 1)")
        cmap_info = self.cid_system_info(encoding.get('/CIDSystemInfo'), "CMap")
        if (
            cmap_info is not None
            and cmap.cid_system_info is not None
            and cmap.cid_system_info != cmap_info
        ):
            self.unsupported(
                'font-cmap',
                "the CMap stream and its dictionary disagree on /CIDSystemInfo",
            )
        if cmap_info is not None and system_info is not None:
            if (
                cmap_info['Registry'] != system_info['Registry']
                or cmap_info['Ordering'] != system_info['Ordering']
            ):
                self.deny(
                    'cidsysteminfo',
                    "CIDFont and CMap /CIDSystemInfo differ: "
                    f"{system_info['Registry']}-{system_info['Ordering']} vs "
                    f"{cmap_info['Registry']}-{cmap_info['Ordering']}",
                )
            elif (
                ctx.flavour.part != 1
                and system_info['Supplement'] > cmap_info['Supplement']
            ):
                self.deny(
                    'cidsysteminfo',
                    f"CIDFont /Supplement {system_info['Supplement']} exceeds the "
                    f"CMap /Supplement {cmap_info['Supplement']}",
                )
        self.info.cmap = cmap

    def cid_widths(self, cidfont: pikepdf.Dictionary) -> None:
        dw = cidfont.get('/DW')
        if dw is not None:
            value = _number(dw)
            if value is None:
                self.deny('font-widths', "/DW is not a number")
                return
            self.info.default_width = value
        if '/W' in cidfont:
            try:
                self.info.cid_widths, self.info.cid_width_conflicts = parse_cid_widths(
                    cidfont.get('/W')
                )
            except ValueError as e:
                self.deny('font-widths', str(e))
        for key in ('/W2', '/DW2'):
            if key in cidfont:
                self.unsupported('font-vertical', f"CIDFont has {key}")

    def cid_to_gid_map(self, cidfont: pikepdf.Dictionary) -> None:
        value = cidfont.get('/CIDToGIDMap')
        if value is None:
            self.deny('cidtogidmap', "CIDFontType2 has no /CIDToGIDMap")
            return
        if isinstance(value, pikepdf.Name):
            if value != pikepdf.Name.Identity:
                self.deny('cidtogidmap', f"/CIDToGIDMap is {value}")
            return
        if not isinstance(value, pikepdf.Stream):
            self.deny('cidtogidmap', "/CIDToGIDMap is not a stream or /Identity")
            return
        try:
            data = value.read_bytes()
        except pikepdf.PdfError as e:
            self.unsupported('font-program', f"/CIDToGIDMap cannot be read: {e}")
            return
        if len(data) % 2:
            self.deny('cidtogidmap', "/CIDToGIDMap has an odd length")
            return
        self.info.cid_to_gid = data

    def cidset(
        self, descriptor: pikepdf.Dictionary, subtype: str, program: Any
    ) -> None:
        info = self.info
        value = descriptor.get('/CIDSet')
        part1 = self.ctx.flavour.part == 1
        if value is None:
            if info.subset and part1:
                self.deny('cidset', "CIDFont subset has no /CIDSet")
            return
        if not isinstance(value, pikepdf.Stream):
            self.deny('cidset', "/CIDSet is not a stream")
            return
        try:
            bits = _cidset_bits(value.read_bytes())
        except pikepdf.PdfError as e:
            self.unsupported('font-program', f"/CIDSet cannot be read: {e}")
            return
        if part1:
            info.cidset = bits
            return
        if not info.subset:
            return
        if subtype == '/CIDFontType2':
            self.unsupported(
                'cidset', "/CIDSet on a CIDFontType2 subset is not checked"
            )
            return
        try:
            program_cids = program.cids()
        except FontProgramError as e:
            self.unsupported('font-program', str(e))
            return
        # veraPDF ignores CID 0 (.notdef) when comparing
        if bits - {0} != program_cids - {0}:
            extra = sorted(bits - program_cids - {0})
            lacking = sorted(program_cids - bits - {0})
            self.deny(
                'cidset',
                "/CIDSet does not identify exactly the CIDs of the program"
                + (f"; not in program: {extra[:10]}" if extra else '')
                + (f"; not in /CIDSet: {lacking[:10]}" if lacking else ''),
            )


def _load(font: Any, ctx: ValidationContext, where: str) -> FontInfo:
    info = FontInfo(where=where)
    loader = _Loader(ctx, info)
    if not isinstance(font, pikepdf.Dictionary):
        loader.deny('font-dictionary', "font resource is not a dictionary")
        return info
    subtype = loader.common(font, "font")
    if subtype is None:
        return info
    if subtype == '/Type0':
        info.kind = 'type0'
        loader.type0(font)
    elif subtype == '/TrueType':
        info.kind = 'truetype'
        loader.truetype(font)
    elif subtype == '/Type1':
        info.kind = 'type1'
        loader.type1(font)
    elif subtype == '/Type3':
        loader.unsupported('font-type3', "Type 3 fonts are not supported")
    elif subtype == '/MMType1':
        loader.unsupported('font-mmtype1', "multiple master fonts are not supported")
    else:
        loader.deny('font-dictionary', f"a {subtype} cannot be used as a font")
    info.ok = not loader.failed and info.program is not None
    return info


def load_font(font: Any, ctx: ValidationContext, where: str) -> FontInfo:
    """Check a font dictionary and return what is needed to check its use.

    Indirect fonts are checked once and cached in ``ctx.fonts``; direct
    font dictionaries are checked each time they are reached.

    Args:
        font: The font dictionary.
        ctx: Validation context; findings are added to its report.
        where: Location used in findings.
    """
    font = pikepdf.unbox(font)
    if isinstance(font, pikepdf.Object) and font.is_indirect:
        key = font.objgen
        info = ctx.fonts.get(key)
        if info is None:
            info = _load(font, ctx, f'{ctx.describe(font)} (Font)')
            ctx.fonts[key] = info
        return info
    info = _load(font, ctx, where)
    ctx.direct_fonts.append(info)
    return info


def finalize_fonts(ctx: ValidationContext) -> None:
    """Run the glyph-level checks of every font, over the codes it showed."""
    for info in [*ctx.fonts.values(), *ctx.direct_fonts]:
        info.finalize(ctx)
