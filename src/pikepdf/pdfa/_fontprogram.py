# SPDX-FileCopyrightText: 2026 James R. Barlow
# SPDX-License-Identifier: MPL-2.0

"""Embedded font programs, read with fontTools behind a common interface.

fontTools parses lazily and trusts its input, so every call into it is
wrapped: any exception becomes a `FontProgramError`, which the font checks
report as an unsupported font rather than letting it escape.
"""

from __future__ import annotations

import struct
from collections import Counter
from collections.abc import Callable
from functools import cached_property, partial
from io import BytesIO
from typing import Any, Protocol, TypeVar

from fontTools.cffLib import (
    CFFFontSet,
    TopDict,
    parseCharset,
    parseCharset0,
    readCard8,
)
from fontTools.encodings.StandardEncoding import StandardEncoding
from fontTools.misc import eexec, psLib
from fontTools.misc.psCharStrings import T1CharString
from fontTools.pens.basePen import NullPen
from fontTools.ttLib import TTFont

DEFAULT_FONT_MATRIX = (0.001, 0, 0, 0.001, 0, 0)
UNITS_PER_EM_RANGE = (16, 16384)

T = TypeVar('T')


class FontProgramError(ValueError):
    """A font program could not be read, or has a structure we do not check."""


class FontProgramAmbiguity(FontProgramError):
    """A font program defines something twice, in ways readers resolve differently."""


def _guard(what: str, func: Callable[[], T]) -> T:
    """Call into fontTools, turning any failure into FontProgramError."""
    try:
        return func()
    except FontProgramError:
        raise
    except Exception as e:  # pylint: disable=broad-except
        raise FontProgramError(f"{what}: {type(e).__name__}: {e}") from e


class GlyphSource(Protocol):
    """What the font checks need to know about an embedded font program."""

    @property
    def num_glyphs(self) -> int:
        """Number of glyphs in the program."""
        ...

    def has_gid(self, gid: int) -> bool:
        """True if the program defines glyph *gid*."""
        ...

    def advance_1000(self, gid: int) -> float | None:
        """Advance width of glyph *gid* in 1/1000 text space units."""
        ...

    def gid_for_name(self, name: str) -> int | None:
        """Glyph id of the glyph called *name*, or None."""
        ...

    def gid_for_cid(self, cid: int) -> int | None:
        """Glyph id of the glyph selected by *cid*, or None."""
        ...

    def cmap_tables(self) -> list[tuple[int, int]]:
        """(platform, encoding) of every cmap subtable, in file order."""
        ...

    def lookup_cmap(self, platform: int, encoding: int, code: int) -> int | None:
        """Look up *code* in a cmap subtable; return a glyph id or None."""
        ...

    def cmap_ranges(self, platform: int, encoding: int) -> list[tuple[int, int]]:
        """Code ranges a cmap subtable covers, including codes of glyph 0."""
        ...

    def glyph_names(self) -> list[str]:
        """Names of all glyphs, in glyph id order."""
        ...


def _raw_cmap_ranges(
    data: bytes, platform: int, encoding: int
) -> list[tuple[int, int]] | None:
    """Code ranges of the first (platform, encoding) subtable of a raw cmap.

    Returns None for subtable formats other than 0, 4, 6 and 12.
    """
    (num_tables,) = struct.unpack_from('>H', data, 2)
    for index in range(num_tables):
        plat, enc, offset = struct.unpack_from('>HHL', data, 4 + 8 * index)
        if (plat, enc) == (platform, encoding):
            break
    else:
        return []
    (fmt,) = struct.unpack_from('>H', data, offset)
    if fmt == 0:
        return [(0, 255)]
    if fmt == 4:
        (seg_count_x2,) = struct.unpack_from('>H', data, offset + 6)
        count = seg_count_x2 // 2
        ends = struct.unpack_from(f'>{count}H', data, offset + 14)
        starts = struct.unpack_from(f'>{count}H', data, offset + 16 + seg_count_x2)
        return [
            (start, end)
            for start, end in zip(starts, ends, strict=True)
            if start <= end and start != 0xFFFF
        ]
    if fmt == 6:
        first, count = struct.unpack_from('>HH', data, offset + 6)
        return [(first, first + count - 1)] if count else []
    if fmt == 12:
        (num_groups,) = struct.unpack_from('>L', data, offset + 12)
        return [
            struct.unpack_from('>LL', data, offset + 16 + 12 * group)
            for group in range(num_groups)
        ]
    return None


class TrueTypeProgram:
    """A TrueType (FontFile2) or OpenType (FontFile3 /OpenType) program.

    OpenType programs with CFF outlines delegate CID and name lookups to a
    `CFFProgram` built from the ``CFF `` table.
    """

    def __init__(self, data: bytes):
        """Parse the tables the checks need; raise FontProgramError if any fail."""
        self._font: TTFont = _guard(
            "cannot read TrueType font", lambda: TTFont(BytesIO(data), lazy=True)
        )
        font = self._font
        self._num_glyphs = _guard(
            "cannot read maxp table", lambda: int(font['maxp'].numGlyphs)
        )
        units = _guard("cannot read head table", lambda: int(font['head'].unitsPerEm))
        if not UNITS_PER_EM_RANGE[0] <= units <= UNITS_PER_EM_RANGE[1]:
            raise FontProgramError(f"unitsPerEm {units} out of range")
        self._units_per_em = units
        self._order: list[str] = _guard(
            "cannot read glyph order", lambda: list(font.getGlyphOrder())
        )
        if len(self._order) != self._num_glyphs:
            raise FontProgramError("glyph order does not match maxp.numGlyphs")
        self._gid_by_name: dict[str, int] = {}
        for gid, name in enumerate(self._order):
            self._gid_by_name.setdefault(name, gid)
        self._metrics: dict[str, tuple[int, int]] = _guard(
            "cannot read hmtx table", lambda: dict(font['hmtx'].metrics)
        )
        self._cff: CFFProgram | None = None
        if 'CFF ' in font:
            cff = _guard("cannot read CFF table", lambda: font['CFF '].cff)
            self._cff = CFFProgram.from_font_set(cff)
        elif 'glyf' not in font or 'loca' not in font:
            raise FontProgramError("TrueType font has no glyf or loca table")
        self._cmaps: list[Any] = []
        if 'cmap' in font:
            self._cmaps = _guard(
                "cannot read cmap table", lambda: list(font['cmap'].tables)
            )

    @property
    def is_cff(self) -> bool:
        """True for OpenType fonts with CFF outlines."""
        return self._cff is not None

    @property
    def cff(self) -> CFFProgram | None:
        """The CFF program inside an OpenType font, if any."""
        return self._cff

    @property
    def num_glyphs(self) -> int:
        """Number of glyphs (maxp.numGlyphs)."""
        return self._num_glyphs

    def has_gid(self, gid: int) -> bool:
        """True if *gid* is below numGlyphs and its outline can be read."""
        if not 0 <= gid < self._num_glyphs:
            return False
        if self._cff is not None:
            return self._cff.has_gid(gid)
        name = self._order[gid]
        try:
            glyph = self._font['glyf'][name]
            glyph.expand(self._font['glyf'])
        except Exception:  # pylint: disable=broad-except
            return False
        return True

    def advance_1000(self, gid: int) -> float | None:
        """Advance width from hmtx scaled to 1/1000 em."""
        if not 0 <= gid < self._num_glyphs:
            return None
        metric = self._metrics.get(self._order[gid])
        if metric is None:
            return None
        return metric[0] * 1000 / self._units_per_em

    def gid_for_name(self, name: str) -> int | None:
        """Glyph id by glyph name (post table or synthesized names)."""
        if self._cff is not None:
            return self._cff.gid_for_name(name)
        return self._gid_by_name.get(name)

    def gid_for_cid(self, cid: int) -> int | None:
        """For CFF-based OpenType, the CID-keyed lookup; otherwise gid = cid."""
        if self._cff is not None:
            return self._cff.gid_for_cid(cid)
        return cid

    def cmap_tables(self) -> list[tuple[int, int]]:
        """(platform, encoding) of every cmap subtable."""
        return [(t.platformID, t.platEncID) for t in self._cmaps]

    def _cmap(self, platform: int, encoding: int) -> dict[int, str]:
        for table in self._cmaps:
            if (table.platformID, table.platEncID) == (platform, encoding):
                return _guard(
                    "cannot read cmap subtable", partial(getattr, table, 'cmap')
                )
        return {}

    def lookup_cmap(self, platform: int, encoding: int, code: int) -> int | None:
        """Look up *code* in the first matching cmap subtable."""
        name = self._cmap(platform, encoding).get(code)
        if name is None:
            return None
        return self._gid_by_name.get(name)

    def cmap_ranges(self, platform: int, encoding: int) -> list[tuple[int, int]]:
        """Code ranges the first matching cmap subtable covers.

        fontTools omits codes mapped to glyph 0, so the ranges are read from
        the raw table for the common subtable formats. They include such
        codes, which some readers take into account.
        """
        if (platform, encoding) not in self.cmap_tables():
            return []
        raw = _guard("cannot read cmap table", lambda: self._font.reader['cmap'])
        ranges = _guard(
            "cannot read cmap table",
            partial(_raw_cmap_ranges, bytes(raw), platform, encoding),
        )
        if ranges is None:
            ranges = [(code, code) for code in self._cmap(platform, encoding)]
        return ranges

    def glyph_names(self) -> list[str]:
        """Names of all glyphs in glyph id order."""
        return list(self._order)


class CFFProgram:
    """A bare CFF program (FontFile3 /Type1C or /CIDFontType0C)."""

    def __init__(self, data: bytes):
        """Parse a bare CFF font set containing exactly one font."""

        def decompile() -> CFFFontSet:
            font_set = CFFFontSet()
            font_set.decompile(BytesIO(data), otFont=None)
            return font_set

        self._init(_guard("cannot read CFF font", decompile))

    @classmethod
    def from_font_set(cls, font_set: CFFFontSet) -> CFFProgram:
        """Wrap an already parsed fontTools CFFFontSet (e.g. from an OTF)."""
        program = cls.__new__(cls)
        program._init(font_set)
        return program

    def _init(self, font_set: CFFFontSet) -> None:
        names = _guard("cannot read CFF font names", lambda: list(font_set.fontNames))
        if len(names) != 1:
            raise FontProgramError(f"CFF font set has {len(names)} fonts")
        top = _guard("cannot read CFF top dict", lambda: font_set[names[0]])
        self._top = top
        raw = _guard("cannot read CFF top dict", lambda: dict(top.rawDict))
        self.is_cid_keyed = 'ROS' in raw
        matrix = raw.get('FontMatrix')
        if matrix is not None and tuple(matrix) != DEFAULT_FONT_MATRIX:
            raise FontProgramError(f"CFF FontMatrix {list(matrix)} is not supported")
        if self.is_cid_keyed:
            fd_array = _guard("cannot read CFF FDArray", lambda: list(top.FDArray))
            for fd in fd_array:
                raw_fd = _guard("cannot read FDArray", partial(getattr, fd, 'rawDict'))
                if 'FontMatrix' in raw_fd:
                    raise FontProgramError("CFF FDArray FontMatrix is not supported")
        self._charset: list[str] = _guard(
            "cannot read CFF charset", lambda: list(top.charset)
        )
        duplicates = _guard(
            "cannot read CFF charset", partial(_duplicate_charset_names, top)
        )
        if duplicates:
            raise FontProgramAmbiguity(
                "CFF charset gives more than one glyph the name "
                + ', '.join(duplicates[:10])
            )
        self._charstrings = _guard(
            "cannot read CFF CharStrings", lambda: top.CharStrings
        )
        if len(self._charstrings) != len(self._charset):
            raise FontProgramError("CFF charset and CharStrings differ in length")
        self._widths: dict[int, float | None] = {}

    @cached_property
    def _gid_by_name(self) -> dict[str, int]:
        result: dict[str, int] = {}
        for gid, name in enumerate(self._charset):
            result.setdefault(name, gid)
        return result

    @cached_property
    def _gid_by_cid(self) -> dict[int, int]:
        result: dict[int, int] = {0: 0}
        for gid, name in enumerate(self._charset):
            if gid == 0:
                continue
            if not (name.startswith('cid') and name[3:].isdigit()):
                raise FontProgramError(f"CID-keyed CFF glyph name {name!r}")
            result.setdefault(int(name[3:]), gid)
        return result

    def cids(self) -> set[int]:
        """CIDs defined by a CID-keyed program (CID 0 included)."""
        if not self.is_cid_keyed:
            raise FontProgramError("CFF font is not CID-keyed")
        return set(self._gid_by_cid)

    @property
    def num_glyphs(self) -> int:
        """Number of glyphs (CharStrings)."""
        return len(self._charset)

    def has_gid(self, gid: int) -> bool:
        """True if *gid* is a valid glyph index."""
        return 0 <= gid < len(self._charset)

    def advance_1000(self, gid: int) -> float | None:
        """Charstring advance width (FontMatrix is 0.001, so no scaling)."""
        if not self.has_gid(gid):
            return None
        if gid not in self._widths:
            name = self._charset[gid]

            def width() -> float:
                charstring = self._charstrings[name]
                charstring.draw(NullPen())
                return float(charstring.width)

            self._widths[gid] = _guard(f"cannot read glyph {name!r}", width)
        return self._widths[gid]

    def gid_for_name(self, name: str) -> int | None:
        """Glyph id by name (not meaningful for CID-keyed fonts)."""
        if self.is_cid_keyed:
            return None
        return self._gid_by_name.get(name)

    def gid_for_cid(self, cid: int) -> int | None:
        """CID-keyed: invert the charset; otherwise gid = cid."""
        if self.is_cid_keyed:
            return self._gid_by_cid.get(cid)
        return cid if self.has_gid(cid) else None

    def cmap_tables(self) -> list[tuple[int, int]]:
        """CFF programs have no cmap."""
        return []

    def lookup_cmap(self, platform: int, encoding: int, code: int) -> int | None:
        """CFF programs have no cmap."""
        return None

    def cmap_ranges(self, platform: int, encoding: int) -> list[tuple[int, int]]:
        """CFF programs have no cmap."""
        return []

    def glyph_names(self) -> list[str]:
        """Names of all glyphs in glyph id order."""
        return list(self._charset)

    def builtin_encoding(self) -> dict[int, str] | None:
        """The font's built-in encoding, or None for StandardEncoding.

        Raises:
            FontProgramError: For ExpertEncoding or a CID-keyed font.
        """
        if self.is_cid_keyed:
            raise FontProgramError("CID-keyed CFF has no encoding")
        encoding = _guard("cannot read CFF Encoding", lambda: self._top.Encoding)
        if encoding == 'StandardEncoding':
            return None
        if isinstance(encoding, str):
            raise FontProgramError(f"CFF {encoding} is not supported")
        return {
            code: name
            for code, name in enumerate(encoding)
            if name and name != '.notdef'
        }


def _duplicate_charset_names(top: TopDict) -> list[str]:
    """Names (or CIDs) that a CFF charset gives to more than one glyph.

    fontTools makes duplicate names unique by appending ``.1`` and so on,
    so the charset is read again as stored.
    """
    offset = top.rawDict.get('charset', 0)
    if offset <= 2:
        return []  # a predefined charset
    file = top.file
    file.seek(offset)
    fmt = readCard8(file)
    is_cid = hasattr(top, 'ROS')
    if fmt == 0:
        names = parseCharset0(top.numGlyphs, file, top.strings, is_cid)
    else:
        names = parseCharset(top.numGlyphs, file, top.strings, is_cid, fmt)
    counts = Counter(names)
    return sorted(name for name, count in counts.items() if count > 1)


EEXEC_BEGIN = b'currentfile eexec'
EEXEC_END = b'currentfile closefile'
EEXEC_KEY = 55665
CHARSTRING_KEY = 4330
PS_WHITESPACE = b' \t\r\n'
HEX_DIGITS = frozenset(b'0123456789abcdefABCDEF')
MAX_PS_LOOP = 4096


class _BoundedPSInterpreter(psLib.PSInterpreter):
    """fontTools' PostScript interpreter with bounded ``for`` loops.

    Type 1 fonts use ``for`` to fill the Encoding array (256 iterations);
    a zero increment or a huge range would otherwise never finish.

    It also records the size requested for each dictionary and every
    assignment to a dictionary key, in order, so that definitions made
    after the CharStrings can be found.
    """

    def __init__(self, encoding: str = 'ascii') -> None:
        """Create an interpreter; see `psLib.PSInterpreter`."""
        # id of each dictionary created by ``dict``: (the dictionary, its size)
        self.dict_sizes: dict[int, tuple[dict, int]] = {}
        # (id of the dictionary, key, value) of each ``def`` and ``put``
        self.assignments: list[tuple[int, Any, Any]] = []
        super().__init__(encoding=encoding)

    def ps_dict(self) -> None:
        """Create a dictionary, recording the size requested."""
        size = self.stack[-1].value if self.stack else None
        super().ps_dict()
        created = self.stack[-1].value
        if isinstance(size, int):
            self.dict_sizes[id(created)] = (created, size)

    def ps_def(self) -> None:
        """Define a key in the current dictionary, recording the assignment."""
        if len(self.stack) < 2:
            super().ps_def()  # raises
            return
        target = self.dictstack[-1]
        key, value = self.stack[-2].value, self.stack[-1].value
        super().ps_def()
        self.assignments.append((id(target), key, value))

    def ps_put(self) -> None:
        """Store into a dictionary or array, recording dictionary assignments."""
        target = self.stack[-3] if len(self.stack) >= 3 else None
        if target is None or target.type != 'dicttype':
            super().ps_put()
            return
        key, value = self.stack[-2].value, self.stack[-1].value
        super().ps_put()
        self.assignments.append((id(target.value), key, value))

    def ps_for(self) -> None:
        """Run ``initial increment limit proc for`` if the loop is short."""
        if len(self.stack) < 4:
            raise psLib.PSError("stack underflow")
        initial, increment, limit = (item.value for item in self.stack[-4:-1])
        if not all(
            isinstance(v, int | float) and not isinstance(v, bool)
            for v in (initial, increment, limit)
        ):
            raise psLib.PSError("for: operands are not numbers")
        if increment == 0 or (limit - initial) / increment > MAX_PS_LOOP:
            raise psLib.PSError("for: loop is too long")
        super().ps_for()


def _decrypt_eexec(data: bytes) -> bytes:
    """Return a Type 1 program with its eexec section decrypted.

    The program is laid out as in a PDF /FontFile stream: cleartext, then
    the binary eexec-encrypted section, then an optional trailer of zeros
    and ``cleartomark``. /Length1, /Length2 and /Length3 are not needed (and
    veraPDF ignores them too). The result is the cleartext
    followed by the decrypted section up to ``currentfile closefile``, which
    the PostScript interpreter can run without switching to eexec.
    """
    begin = data.find(EEXEC_BEGIN)
    if begin < 0:
        raise FontProgramError("Type 1 program has no eexec section")
    pos = begin + len(EEXEC_BEGIN)
    # The first byte of the encrypted section is never whitespace
    while pos < len(data) and data[pos] in PS_WHITESPACE:
        pos += 1
    cipher = data[pos:]
    if len(cipher) < 4:
        raise FontProgramError("Type 1 eexec section is truncated")
    if all(byte in HEX_DIGITS for byte in cipher[:4]):
        # PostScript accepts this, but veraPDF reports such a font as not
        # embedded.
        raise FontProgramError("Type 1 eexec section is hexadecimal, not binary")
    plain, _ = eexec.decrypt(cipher, EEXEC_KEY)
    end = plain.find(EEXEC_END, 4)
    if end < 0:
        raise FontProgramError("Type 1 eexec section is truncated")
    return data[:begin] + b'\n' + plain[4:end]


def _check_type1_definitions(
    interpreter: _BoundedPSInterpreter, raw_font: dict[str, Any]
) -> None:
    """Reject a Type 1 font whose CharStrings can be read in two ways.

    PostScript grows a dictionary that receives more entries than it was
    created for, while some readers stop after that many CharStrings. And
    readers decrypt the CharStrings with the /lenIV defined either when
    they are read or at the end of the program.

    Raises:
        FontProgramAmbiguity: If the CharStrings dictionary holds more
            entries than its declared size, or /lenIV changes after the
            first CharStrings entry.
    """
    charstrings = raw_font.get('CharStrings')
    private = raw_font.get('Private')
    if charstrings is None or not isinstance(charstrings.value, dict):
        return
    cs_id = id(charstrings.value)
    _dict, size = interpreter.dict_sizes.get(cs_id, (None, None))
    if size is not None and len(charstrings.value) > size:
        raise FontProgramAmbiguity(
            f"Type 1 CharStrings has {len(charstrings.value)} entries but was "
            f"created for {size}"
        )
    if private is None or not isinstance(private.value, dict):
        return
    assignments = interpreter.assignments
    first = next((i for i, (d, _k, _v) in enumerate(assignments) if d == cs_id), None)
    if first is None:
        return
    private_id = id(private.value)
    len_ivs = [
        (i, value)
        for i, (d, key, value) in enumerate(assignments)
        if d == private_id and key == 'lenIV'
    ]
    before = [value for i, value in len_ivs if i < first]
    in_effect = before[-1] if before else 4
    later = {value for i, value in len_ivs if i > first}
    if later - {in_effect}:
        raise FontProgramAmbiguity(
            f"Type 1 /lenIV is {in_effect} when the CharStrings are defined and "
            f"then changes to {sorted(later - {in_effect})[0]}"
        )


def _run_type1(text: bytes) -> dict[str, Any]:
    """Interpret a decrypted Type 1 program; return its font dictionary."""
    interpreter = _BoundedPSInterpreter(encoding='latin-1')
    try:
        interpreter.interpret(text)
        fonts = interpreter.dictstack[0]['FontDirectory'].value
        if len(fonts) != 1:
            raise FontProgramError(f"Type 1 program defines {len(fonts)} fonts")
        (raw_font,) = fonts.values()
        if isinstance(raw_font.value, dict):
            _check_type1_definitions(interpreter, raw_font.value)
        font = psLib.unpack_item(raw_font)
    finally:
        interpreter.close()
    if not isinstance(font, dict):
        raise FontProgramError("Type 1 font is not a dictionary")
    return font


class Type1Program:
    """A Type 1 program (FontFile), read with fontTools' PostScript interpreter.

    Glyph ids are positions in `glyph_names`, which puts ``.notdef`` first
    (as glyph 0) and the other CharStrings in program order.
    """

    is_cid_keyed = False

    def __init__(self, data: bytes):
        """Parse the program; raise FontProgramError if it cannot be read."""
        text = _guard("cannot decrypt Type 1 font", lambda: _decrypt_eexec(data))
        font = _guard("cannot read Type 1 font", lambda: _run_type1(text))
        if font.get('FontType') != 1:
            raise FontProgramError(f"FontType {font.get('FontType')!r} is not 1")
        matrix = font.get('FontMatrix')
        if not isinstance(matrix, list) or tuple(matrix) != DEFAULT_FONT_MATRIX:
            raise FontProgramError(f"Type 1 FontMatrix {matrix!r} is not supported")
        self._charstrings: dict[str, T1CharString] = _guard(
            "cannot read Type 1 CharStrings", lambda: self._decrypt_charstrings(font)
        )
        if '.notdef' not in self._charstrings:
            raise FontProgramError("Type 1 font has no .notdef glyph")
        self._order = ['.notdef'] + [n for n in self._charstrings if n != '.notdef']
        self._gid_by_name = {name: gid for gid, name in enumerate(self._order)}
        self._encoding = font.get('Encoding')
        self._widths: dict[int, float] = {}

    @staticmethod
    def _decrypt_charstrings(font: dict[str, Any]) -> dict[str, T1CharString]:
        private = font['Private']
        len_iv = private.get('lenIV', 4)
        if not isinstance(len_iv, int) or len_iv < 0:
            raise FontProgramError(f"Type 1 lenIV {len_iv!r}")
        raw_subrs = private.get('Subrs', [])
        subrs: list[T1CharString] = []
        for subr in raw_subrs:
            code, _ = eexec.decrypt(subr, CHARSTRING_KEY)
            subrs.append(T1CharString(code[len_iv:], subrs=subrs))
        charstrings: dict[str, T1CharString] = {}
        for name, charstring in font['CharStrings'].items():
            if not isinstance(name, str) or not isinstance(charstring, bytes):
                raise FontProgramError("malformed Type 1 CharStrings entry")
            code, _ = eexec.decrypt(charstring, CHARSTRING_KEY)
            charstrings[name] = T1CharString(code[len_iv:], subrs=subrs)
        return charstrings

    @property
    def num_glyphs(self) -> int:
        """Number of glyphs (CharStrings entries)."""
        return len(self._order)

    def has_gid(self, gid: int) -> bool:
        """True if *gid* is a valid glyph index."""
        return 0 <= gid < len(self._order)

    def advance_1000(self, gid: int) -> float | None:
        """Charstring advance width (FontMatrix is 0.001, so no scaling)."""
        if not self.has_gid(gid):
            return None
        if gid not in self._widths:
            name = self._order[gid]

            def width() -> float:
                charstring = self._charstrings[name]
                charstring.draw(NullPen())
                return float(charstring.width)

            self._widths[gid] = _guard(f"cannot read glyph {name!r}", width)
        return self._widths[gid]

    def gid_for_name(self, name: str) -> int | None:
        """Glyph id by glyph name."""
        return self._gid_by_name.get(name)

    def gid_for_cid(self, cid: int) -> int | None:
        """Type 1 programs are not CID-keyed."""
        return None

    def cmap_tables(self) -> list[tuple[int, int]]:
        """Type 1 programs have no cmap."""
        return []

    def lookup_cmap(self, platform: int, encoding: int, code: int) -> int | None:
        """Type 1 programs have no cmap."""
        return None

    def cmap_ranges(self, platform: int, encoding: int) -> list[tuple[int, int]]:
        """Type 1 programs have no cmap."""
        return []

    def glyph_names(self) -> list[str]:
        """Names of all glyphs in glyph id order."""
        return list(self._order)

    def builtin_encoding(self) -> dict[int, str] | None:
        """The font's built-in encoding, or None for StandardEncoding.

        Raises:
            FontProgramError: If the Encoding is not StandardEncoding or an
                array of 256 names.
        """
        encoding = self._encoding
        if encoding == 'StandardEncoding' or encoding == StandardEncoding:
            return None
        if (
            not isinstance(encoding, list)
            or len(encoding) != 256
            or not all(isinstance(name, str) for name in encoding)
        ):
            raise FontProgramError(f"Type 1 Encoding {encoding!r:.40} is not supported")
        return {
            code: name
            for code, name in enumerate(encoding)
            if name and name != '.notdef'
        }
