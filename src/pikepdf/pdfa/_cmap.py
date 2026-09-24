# SPDX-FileCopyrightText: 2026 James R. Barlow
# SPDX-License-Identifier: MPL-2.0

"""Embedded CMap streams (the /Encoding of a Type 0 font).

A CMap is a small PostScript program. ``pikepdf.parse_content_stream``
tokenizes it cleanly, grouping the operands that precede each operator, so
this module interprets the tokens with a minimal operand and dictionary
stack. Only the operators found in CMap files are accepted; anything else
is an error.
"""

from __future__ import annotations

import warnings
from bisect import bisect_right
from dataclasses import dataclass, field
from typing import Any, Literal, NamedTuple

import pikepdf

MAX_CID = 65535
MAX_CODE_BYTES = 4

CMapErrorReason = Literal[
    'syntax', 'usecmap', 'cid-limit', 'codespace', 'unmapped', 'ambiguous'
]


class CMapError(ValueError):
    """A CMap could not be parsed or a string could not be decoded.

    Attributes:
        reason: ``syntax`` (not a CMap this module understands), ``usecmap``
            (it refers to another CMap), ``cid-limit`` (it maps a code to a
            CID above 65535), ``codespace`` (a string has bytes outside every
            codespace range), ``unmapped`` (a code has no CID), or
            ``ambiguous`` (codespace ranges overlap, so a string can be split
            into codes in more than one way, or a code is mapped to two
            different CIDs, so readers may disagree on which applies).
    """

    def __init__(self, message: str, reason: CMapErrorReason):
        super().__init__(message)
        self.reason: CMapErrorReason = reason


class _Dict(dict):
    """A dictionary created by the PostScript ``dict`` operator."""


class _Opaque:
    """A PostScript value this module does not need to interpret."""


_OPAQUE = _Opaque()

# Executable names that only push a value or are no-ops in CMap files.
_PUSH_OPAQUE = frozenset({'CMapName', 'CIDSystemInfo', 'userdict', 'systemdict'})


@dataclass
class _Range:
    low: int
    high: int
    cid: int
    single: bool = False  # notdefrange: every code maps to the same CID


@dataclass
class EmbeddedCMap:
    """An embedded CMap mapping character codes to CIDs.

    Attributes:
        name: The /CMapName defined in the stream, if any.
        wmode: The /WMode defined in the stream, or None if not defined.
        cid_system_info: The /CIDSystemInfo defined in the stream, as a
            dict with ``Registry``, ``Ordering`` and ``Supplement``, or None.
        codespace: Codespace ranges as (low, high) byte strings.
        max_cid: The largest CID any mapping produces.
    """

    name: str | None = None
    wmode: int | None = None
    cid_system_info: dict[str, Any] | None = None
    codespace: list[tuple[bytes, bytes]] = field(default_factory=list)
    max_cid: int = 0
    _chars: dict[tuple[int, int], int] = field(default_factory=dict)
    _ranges: dict[int, list[_Range]] = field(default_factory=dict)
    _notdef_chars: dict[tuple[int, int], int] = field(default_factory=dict)
    _notdef_ranges: dict[int, list[_Range]] = field(default_factory=dict)
    # Codes with conflicting mappings, as (low, high) by code length
    _conflicts: dict[int, list[tuple[int, int]]] = field(default_factory=dict)
    _notdef_conflicts: dict[int, list[tuple[int, int]]] = field(default_factory=dict)

    def _in_codespace(self, chunk: bytes) -> bool:
        for low, high in self.codespace:
            if len(low) == len(chunk) and all(
                lo <= b <= hi for lo, b, hi in zip(low, chunk, high, strict=True)
            ):
                return True
        return False

    @staticmethod
    def _find(ranges: list[_Range] | None, code: int) -> int | None:
        if not ranges:
            return None
        index = bisect_right([r.low for r in ranges], code) - 1
        # Ranges may overlap, so check backwards from the candidate.
        for r in reversed(ranges[: index + 1]):
            if r.low <= code <= r.high:
                return r.cid if r.single else r.cid + (code - r.low)
        return None

    @staticmethod
    def _conflicting(
        conflicts: dict[int, list[tuple[int, int]]], length: int, code: int
    ) -> bool:
        return any(lo <= code <= hi for lo, hi in conflicts.get(length, ()))

    def lookup(self, length: int, code: int) -> int | None:
        """Return the CID of an *length*-byte code, or None if unmapped.

        Raises:
            CMapError: If the code is mapped to different CIDs.
        """
        conflicts = self._conflicts
        cid = self._chars.get((length, code))
        if cid is None:
            cid = self._find(self._ranges.get(length), code)
        if cid is None:
            conflicts = self._notdef_conflicts
            cid = self._notdef_chars.get((length, code))
            if cid is None:
                cid = self._find(self._notdef_ranges.get(length), code)
        if cid is not None and self._conflicting(conflicts, length, code):
            raise CMapError(
                f"code <{code:0{2 * length}x}> is mapped to more than one CID",
                'ambiguous',
            )
        return cid

    def decode(self, data: bytes) -> list[tuple[int, int]]:
        """Decode a string into (code, CID) pairs.

        Raises:
            CMapError: If the bytes do not match any codespace range, or a
                code has no CID or more than one.
        """
        result: list[tuple[int, int]] = []
        pos = 0
        size = len(data)
        while pos < size:
            for length in range(1, MAX_CODE_BYTES + 1):
                chunk = data[pos : pos + length]
                if len(chunk) == length and self._in_codespace(chunk):
                    break
            else:
                raise CMapError(
                    f"bytes {data[pos : pos + MAX_CODE_BYTES].hex()} at offset "
                    f"{pos} match no codespace range",
                    'codespace',
                )
            code = int.from_bytes(chunk, 'big')
            cid = self.lookup(length, code)
            if cid is None:
                raise CMapError(
                    f"code <{chunk.hex()}> is not mapped to a CID", 'unmapped'
                )
            result.append((code, cid))
            pos += length
        return result

    def _add_range(self, table: dict[int, list[_Range]], length: int, r: _Range):
        table.setdefault(length, []).append(r)


def _code(obj: Any) -> bytes:
    if not isinstance(obj, pikepdf.String):
        raise CMapError(f"expected a code string, not {obj!r}", 'syntax')
    raw = bytes(obj)
    if not 1 <= len(raw) <= MAX_CODE_BYTES:
        raise CMapError(f"code <{raw.hex()}> has {len(raw)} bytes", 'syntax')
    return raw


def _cid(obj: Any) -> int:
    if not isinstance(obj, int) or isinstance(obj, bool):
        raise CMapError(f"expected a CID, not {obj!r}", 'syntax')
    cid = int(obj)
    if cid < 0:
        raise CMapError(f"negative CID {cid}", 'syntax')
    if cid > MAX_CID:
        raise CMapError(f"CID {cid} exceeds {MAX_CID}", 'cid-limit')
    return cid


def _groups(operands: list[Any], size: int, op: str) -> list[list[Any]]:
    if len(operands) % size:
        raise CMapError(f"{op} has {len(operands)} operands", 'syntax')
    return [operands[i : i + size] for i in range(0, len(operands), size)]


def _range_pair(low: bytes, high: bytes, op: str) -> tuple[int, int]:
    if len(low) != len(high):
        raise CMapError(
            f"{op}: <{low.hex()}> and <{high.hex()}> differ in length", 'syntax'
        )
    lo, hi = int.from_bytes(low, 'big'), int.from_bytes(high, 'big')
    if lo > hi:
        raise CMapError(f"{op}: empty range <{low.hex()}>..<{high.hex()}>", 'syntax')
    return lo, hi


def _pdf_value(obj: Any) -> Any:
    """Convert a CIDSystemInfo value to Python."""
    if isinstance(obj, pikepdf.String):
        return bytes(obj).decode('latin-1')
    if isinstance(obj, int):
        return int(obj)
    return obj


def _system_info(value: Any) -> dict[str, Any] | None:
    if isinstance(value, pikepdf.Dictionary):
        items = {str(k)[1:]: v for k, v in value.items()}
    elif isinstance(value, _Dict):
        items = dict(value)
    else:
        return None
    return {k: _pdf_value(v) for k, v in items.items()}


class _Interpreter:
    def __init__(self) -> None:
        self.cmap = EmbeddedCMap()
        self.stack: list[Any] = []
        self.dicts: list[Any] = [_Dict()]
        # The CMap entries this module reads, wherever they were defined
        self.top = _Dict()
        self.pending: str | None = None  # the open begin... section

    def pop(self, op: str) -> Any:
        if not self.stack:
            raise CMapError(f"{op}: operand stack underflow", 'syntax')
        return self.stack.pop()

    def run(self, operands: list[Any], op: str) -> None:
        if self.pending is not None:
            if op != 'end' + self.pending:
                raise CMapError(f"{op} inside begin{self.pending}", 'syntax')
            self.section(self.pending, operands)
            self.pending = None
            return
        self.stack.extend(operands)
        handler = getattr(self, 'op_' + op, None)
        if handler is not None:
            handler(op)
        elif op in _SECTIONS:
            count = self.pop(op)
            if not isinstance(count, int) or not 0 <= count <= 100:
                raise CMapError(f"{op}: bad count {count!r}", 'syntax')
            self.pending = op.removeprefix('begin')
        elif op in _PUSH_OPAQUE:
            self.stack.append(_OPAQUE)
        else:
            raise CMapError(f"unexpected operator {op!r} in CMap", 'syntax')

    # --- PostScript ---------------------------------------------------------

    def op_findresource(self, op: str) -> None:
        self.pop(op)
        self.pop(op)
        self.stack.append(_OPAQUE)

    def op_dict(self, op: str) -> None:
        self.pop(op)
        self.stack.append(_Dict())

    def op_dup(self, op: str) -> None:
        value = self.pop(op)
        self.stack.extend([value, value])

    def op_begin(self, op: str) -> None:
        value = self.pop(op)
        self.dicts.append(value)

    def op_end(self, op: str) -> None:
        if len(self.dicts) <= 1:
            raise CMapError("end without begin", 'syntax')
        self.dicts.pop()

    def op_def(self, op: str) -> None:
        value = self.pop(op)
        key = self.pop(op)
        if not isinstance(key, pikepdf.Name):
            raise CMapError(f"def with key {key!r}", 'syntax')
        name = str(key)[1:]
        current = self.dicts[-1]
        if isinstance(current, _Dict):
            current[name] = value
        if name in _CMAP_KEYS:
            self.top[name] = value

    def op_currentdict(self, op: str) -> None:
        self.stack.append(self.dicts[-1])

    def op_defineresource(self, op: str) -> None:
        self.pop(op)
        value = self.pop(op)
        self.pop(op)
        self.stack.append(value)

    def op_pop(self, op: str) -> None:
        self.pop(op)

    def op_begincmap(self, op: str) -> None:
        pass

    def op_endcmap(self, op: str) -> None:
        pass

    def op_usecmap(self, op: str) -> None:
        raise CMapError("the CMap refers to another CMap (usecmap)", 'usecmap')

    # --- CMap sections ------------------------------------------------------

    def section(self, name: str, operands: list[Any]) -> None:
        cmap = self.cmap
        op = 'end' + name
        if name == 'codespacerange':
            for low, high in _groups(operands, 2, op):
                lo_code, hi_code = _code(low), _code(high)
                if len(lo_code) != len(hi_code) or any(
                    a > b for a, b in zip(lo_code, hi_code, strict=True)
                ):
                    raise CMapError(
                        f"bad codespace range <{lo_code.hex()}> <{hi_code.hex()}>",
                        'syntax',
                    )
                cmap.codespace.append((lo_code, hi_code))
        elif name in ('cidchar', 'notdefchar'):
            table = cmap._chars if name == 'cidchar' else cmap._notdef_chars
            conflicts = cmap._conflicts if name == 'cidchar' else cmap._notdef_conflicts
            for src, dst in _groups(operands, 2, op):
                code = _code(src)
                cid = _cid(dst)
                key = (len(code), int.from_bytes(code, 'big'))
                if table.setdefault(key, cid) != cid:
                    conflicts.setdefault(key[0], []).append((key[1], key[1]))
                cmap.max_cid = max(cmap.max_cid, cid)
        elif name in ('cidrange', 'notdefrange'):
            single = name == 'notdefrange'
            ranges = cmap._ranges if name == 'cidrange' else cmap._notdef_ranges
            for low, high, dst in _groups(operands, 3, op):
                lo_bytes, hi_bytes = _code(low), _code(high)
                lo, hi = _range_pair(lo_bytes, hi_bytes, op)
                cid = _cid(dst)
                last = cid if single else cid + (hi - lo)
                if last > MAX_CID:
                    raise CMapError(f"CID {last} exceeds {MAX_CID}", 'cid-limit')
                cmap._add_range(ranges, len(lo_bytes), _Range(lo, hi, cid, single))
                cmap.max_cid = max(cmap.max_cid, last)

    def finish(self) -> EmbeddedCMap:
        if self.pending is not None:
            raise CMapError(f"unterminated begin{self.pending}", 'syntax')
        cmap = self.cmap
        for table in (cmap._ranges, cmap._notdef_ranges):
            for ranges in table.values():
                ranges.sort(key=lambda r: r.low)
        _check_codespace(cmap.codespace)
        _find_conflicts(cmap._chars, cmap._ranges, cmap._conflicts)
        _find_conflicts(cmap._notdef_chars, cmap._notdef_ranges, cmap._notdef_conflicts)
        top = self.top
        wmode = top.get('WMode')
        if wmode is not None:
            if not isinstance(wmode, int) or wmode not in (0, 1):
                raise CMapError(f"bad /WMode {wmode!r}", 'syntax')
            cmap.wmode = int(wmode)
        cmap.cid_system_info = _system_info(top.get('CIDSystemInfo'))
        name = top.get('CMapName')
        if isinstance(name, pikepdf.Name):
            cmap.name = str(name)[1:]
        if not cmap.codespace:
            raise CMapError("the CMap has no codespace ranges", 'syntax')
        return cmap


_CMAP_KEYS = frozenset({'WMode', 'CIDSystemInfo', 'CMapName'})


def _check_codespace(codespace: list[tuple[bytes, bytes]]) -> None:
    """Reject codespace ranges that overlap.

    If the bytes of a shorter range can begin a longer one, a string can be
    split into codes in two ways, and readers differ in which they choose.
    Overlapping ranges of the same length are rejected as well.

    Raises:
        CMapError: If two ranges overlap.
    """
    for i, (low1, high1) in enumerate(codespace):
        for low2, high2 in codespace[i + 1 :]:
            if all(
                max(a, b) <= min(c, d)
                for a, b, c, d in zip(low1, low2, high1, high2, strict=False)
            ):
                raise CMapError(
                    f"codespace ranges <{low1.hex()}> <{high1.hex()}> and "
                    f"<{low2.hex()}> <{high2.hex()}> overlap",
                    'ambiguous',
                )


class _Mapping(NamedTuple):
    low: int
    high: int
    cid: int  # CID of *low*
    single: bool  # every code maps to *cid*

    def at(self, code: int) -> int:
        return self.cid if self.single else self.cid + code - self.low


def _find_conflicts(
    chars: dict[tuple[int, int], int],
    ranges: dict[int, list[_Range]],
    conflicts: dict[int, list[tuple[int, int]]],
) -> None:
    """Add to *conflicts* the codes that two mappings map to different CIDs."""
    by_length: dict[int, list[_Mapping]] = {}
    for (length, code), cid in chars.items():
        by_length.setdefault(length, []).append(_Mapping(code, code, cid, True))
    for length, table in ranges.items():
        for r in table:
            by_length.setdefault(length, []).append(
                _Mapping(r.low, r.high, r.cid, r.single or r.low == r.high)
            )
    for length, mappings in by_length.items():
        mappings.sort()
        active: list[_Mapping] = []
        for m in mappings:
            active = [a for a in active if a.high >= m.low]
            for a in active:
                low, high = m.low, min(a.high, m.high)
                if low == high:
                    agree = a.at(low) == m.at(low)
                else:
                    agree = (a.single, a.at(low)) == (m.single, m.at(low))
                if not agree:
                    conflicts.setdefault(length, []).append((low, high))
            active.append(m)


_SECTIONS = frozenset(
    {
        'begincodespacerange',
        'begincidchar',
        'begincidrange',
        'beginnotdefchar',
        'beginnotdefrange',
    }
)


def parse_embedded_cmap(stream: pikepdf.Stream) -> EmbeddedCMap:
    """Parse an embedded CMap stream.

    Raises:
        CMapError: If the stream refers to another CMap (by /UseCMap or
            ``usecmap``), maps a code to a CID above 65535, or contains
            anything this parser does not understand, including tokens
            pikepdf warns about.
    """
    if '/UseCMap' in stream.stream_dict:
        raise CMapError("the CMap refers to another CMap (/UseCMap)", 'usecmap')
    interpreter = _Interpreter()
    try:
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter('always')
            instructions = pikepdf.parse_content_stream(stream, '')
    except (pikepdf.PdfError, ValueError, TypeError) as e:
        raise CMapError(f"cannot parse the CMap: {e}", 'syntax') from e
    if caught:
        raise CMapError(f"cannot parse the CMap: {caught[0].message}", 'syntax')
    for instruction in instructions:
        if not isinstance(instruction, pikepdf.ContentStreamInstruction):
            raise CMapError("inline image in a CMap", 'syntax')
        interpreter.run(list(instruction.operands), str(instruction.operator))
    return interpreter.finish()
