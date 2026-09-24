# SPDX-FileCopyrightText: 2026 James R. Barlow
# SPDX-License-Identifier: MPL-2.0

"""Fonts whose data can be read two ways are reported as unsupported.

When a font defines the same thing twice and the definitions disagree,
readers may pick either one, so the validator does not guess: it reports
the font as unsupported and the pipeline falls back to Ghostscript.
Duplicate definitions that agree are accepted.
"""

from __future__ import annotations

import pytest

pytest.importorskip('jsonschema')

from io import BytesIO
from pathlib import Path

from fontTools.cffLib import CFFFontSet
from fontTools.fontBuilder import FontBuilder
from fontTools.misc import eexec
from fontTools.misc.psCharStrings import T1CharString
from fontTools.pens.t2CharStringPen import T2CharStringPen
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib.tables._c_m_a_p import CmapSubtable
from pdfa_samples import (
    assert_verapdf_agrees,
    assert_verapdf_fails,
    make_candidate,
    save_candidate,
)

import pikepdf
from pikepdf import Array, Dictionary, Name
from pikepdf.pdfa import validate
from pikepdf.pdfa._cmap import CMapError, parse_embedded_cmap
from pikepdf.pdfa._fonts import parse_cid_widths
from pikepdf.pdfa._report import ValidationReport

GLYPHS = [('.notdef', 500), ('space', 250), ('A', 600), ('B', 700), ('C', 800)]
DESCRIPTOR = dict(
    Type=Name.FontDescriptor,
    FontBBox=[0, -200, 1000, 800],
    ItalicAngle=0,
    Ascent=800,
    Descent=-200,
    CapHeight=700,
    StemV=80,
)
WIDTH_RULE = 'ISO_19005_2:6.2.11.5-1'


# --- font builders ------------------------------------------------------------


def make_ttf(glyphs: list[tuple[str, int]], cmaps: dict) -> bytes:
    """Return a TrueType font; *cmaps* maps (platform, encoding) to {code: name}."""
    builder = FontBuilder(1000, isTTF=True)
    builder.setupGlyphOrder([name for name, _ in glyphs])
    builder.setupCharacterMap({})
    outlines = {}
    for name, advance in glyphs:
        pen = TTGlyphPen(None)
        right = max(advance, 120) - 50
        pen.moveTo((50, 0))
        pen.lineTo((50, 700))
        pen.lineTo((right, 700))
        pen.lineTo((right, 0))
        pen.closePath()
        outlines[name] = pen.glyph()
    builder.setupGlyf(outlines)
    builder.setupHorizontalMetrics({name: (adv, 50) for name, adv in glyphs})
    builder.setupHorizontalHeader(ascent=800, descent=-200)
    builder.setupNameTable({'familyName': 'Test', 'styleName': 'Regular'})
    builder.setupOS2()
    builder.setupPost()
    tables = []
    for (platform, encoding), mapping in cmaps.items():
        subtable = CmapSubtable.newSubtable(0 if (platform, encoding) == (1, 0) else 4)
        subtable.platformID, subtable.platEncID, subtable.language = (
            platform,
            encoding,
            0,
        )
        subtable.cmap = dict(mapping)
        tables.append(subtable)
    builder.font['cmap'].tables = tables
    buf = BytesIO()
    builder.font.save(buf)
    return buf.getvalue()


def make_cff(glyphs: list[tuple[str, int]]) -> bytes:
    """Return a bare (FontFile3 /Type1C) CFF font."""
    builder = FontBuilder(1000, isTTF=False)
    builder.setupGlyphOrder([name for name, _ in glyphs])
    builder.setupCharacterMap({})
    charstrings = {}
    for name, advance in glyphs:
        pen = T2CharStringPen(advance, None)
        if name not in ('.notdef', 'space'):
            pen.moveTo((50, 0))
            pen.lineTo((50, 700))
            pen.lineTo((advance - 50, 700))
            pen.lineTo((advance - 50, 0))
            pen.closePath()
        charstrings[name] = pen.getCharString()
    builder.setupCFF('TestCFF', {'FullName': 'TestCFF'}, charstrings, {})
    font_set = builder.font['CFF '].cff
    buf = BytesIO()
    font_set.compile(buf, builder.font)
    return buf.getvalue()


def _type1_charstring(width: int, empty: bool, len_iv: int) -> bytes:
    program: list = [0, width, 'hsbw']
    if not empty:
        program += [100, 0, 'rmoveto', 0, 700, 'rlineto']
        program += [max(width - 200, 20), 0, 'rlineto', 0, -700, 'rlineto']
        program += ['closepath']
    program.append('endchar')
    charstring = T1CharString(program=program)
    charstring.compile()
    encrypted, _ = eexec.encrypt(b'\0' * len_iv + charstring.bytecode, 4330)
    return encrypted


def make_type1(
    glyphs: list[tuple[str, int]],
    *,
    charstrings_count: int | None = None,
    len_iv: int = 4,
    early_len_iv: int | None = 4,
    late_len_iv: int | None = None,
) -> tuple[bytes, bytes, bytes]:
    """Return the cleartext, eexec and trailer parts of a Type 1 font.

    The CharStrings are encrypted with *len_iv*; the Private dictionary
    defines /lenIV as *early_len_iv* before the CharStrings and as
    *late_len_iv* after them (None: not defined there).
    """
    clear = (
        b'%!PS-AdobeFont-1.0: TestT1\n12 dict begin\n'
        b'/FontInfo 2 dict dup begin /FamilyName (Test) readonly def end '
        b'readonly def\n/FontName /TestT1 def\n/PaintType 0 def\n/FontType 1 def\n'
        b'/FontMatrix [0.001 0 0 0.001 0 0] readonly def\n'
        b'/FontBBox {0 -200 1000 800} readonly def\n'
        b'/Encoding StandardEncoding def\ncurrentdict end\ncurrentfile eexec\n'
    )
    count = len(glyphs) if charstrings_count is None else charstrings_count
    private = (
        b'dup /Private 8 dict dup begin\n'
        b'/RD {string currentfile exch readstring pop} executeonly def\n'
        b'/ND {noaccess def} executeonly def\n/NP {noaccess put} executeonly def\n'
        b'/BlueValues [] def\n/MinFeature {16 16} def\n/password 5839 def\n'
    )
    if early_len_iv is not None:
        private += b'/lenIV %d def\n' % early_len_iv
    private += b'/Subrs 0 array\nND\n2 index /CharStrings %d dict dup begin\n' % count
    for name, width in glyphs:
        data = _type1_charstring(width, name in ('.notdef', 'space'), len_iv)
        private += b'/%s %d RD %s ND\n' % (name.encode(), len(data), data)
    private += b'end\n'
    if late_len_iv is not None:
        private += b'/lenIV %d def\n' % late_len_iv
    private += (
        b'end\nreadonly put\nnoaccess put\n'
        b'dup /FontName get exch definefont pop\nmark currentfile closefile\n'
    )
    encrypted, _ = eexec.encrypt(b'\0\0\0\0' + private, 55665)
    trailer = (b'0' * 64 + b'\n') * 8 + b'cleartomark\n'
    return clear, encrypted, trailer


# --- PDF builders -------------------------------------------------------------


def _page(pdf: pikepdf.Pdf, font: Dictionary, content: bytes) -> None:
    page = Dictionary(
        Type=Name.Page,
        MediaBox=[0, 0, 612, 792],
        Resources=Dictionary(Font=Dictionary(F1=pdf.make_indirect(font))),
        Contents=pdf.make_stream(content),
    )
    pdf.pages.append(pikepdf.Page(page))


def type0_pdf(
    content: bytes, *, w: list | None = None, cmap: bytes | None = None
) -> pikepdf.Pdf:
    """A Type 0 font over a CIDFontType2 of GLYPHS (CID = glyph id)."""
    pdf = pikepdf.new()
    data = make_ttf(GLYPHS, {(3, 1): {0x20: 'space', 0x41: 'A', 0x42: 'B'}})
    descriptor = Dictionary(
        **DESCRIPTOR,
        FontName=Name('/Test'),
        Flags=4,
        FontFile2=pdf.make_stream(data, Length1=len(data)),
    )
    cidfont = Dictionary(
        Type=Name.Font,
        Subtype=Name.CIDFontType2,
        BaseFont=Name('/Test'),
        CIDSystemInfo=Dictionary(
            Registry=pikepdf.String('Adobe'),
            Ordering=pikepdf.String('Identity'),
            Supplement=0,
        ),
        CIDToGIDMap=Name.Identity,
        FontDescriptor=pdf.make_indirect(descriptor),
        W=Array(w if w is not None else [1, [250, 600, 700, 800]]),
    )
    encoding: pikepdf.Object = Name('/Identity-H')
    if cmap is not None:
        encoding = pdf.make_stream(
            CMAP_HEADER + cmap + CMAP_FOOTER,
            Type=Name.CMap,
            CMapName=Name('/Test-H'),
            CIDSystemInfo=Dictionary(
                Registry=pikepdf.String('Adobe'),
                Ordering=pikepdf.String('Identity'),
                Supplement=0,
            ),
        )
    font = Dictionary(
        Type=Name.Font,
        Subtype=Name.Type0,
        BaseFont=Name('/Test'),
        Encoding=encoding,
        DescendantFonts=Array([pdf.make_indirect(cidfont)]),
    )
    _page(pdf, font, content)
    return pdf


def symbolic_truetype_pdf(cmap_30: dict[int, str]) -> pikepdf.Pdf:
    """A symbolic TrueType font with one (3,0) cmap subtable, showing (A)."""
    pdf = pikepdf.new()
    data = make_ttf(GLYPHS, {(3, 0): cmap_30})
    descriptor = Dictionary(
        **DESCRIPTOR,
        FontName=Name('/ABCDEF+Test'),
        Flags=4,
        FontFile2=pdf.make_stream(data, Length1=len(data)),
    )
    widths = [0] * 256
    widths[0x41] = 700
    font = Dictionary(
        Type=Name.Font,
        Subtype=Name.TrueType,
        BaseFont=Name('/ABCDEF+Test'),
        FirstChar=0,
        LastChar=255,
        Widths=Array(widths),
        FontDescriptor=pdf.make_indirect(descriptor),
    )
    _page(pdf, font, b'BT /F1 24 Tf 72 700 Td (A) Tj ET')
    return pdf


def type1_pdf(parts: tuple[bytes, bytes, bytes]) -> pikepdf.Pdf:
    """A simple Type 1 font (FontFile) showing (AB), widths A 600 and B 700."""
    clear, encrypted, trailer = parts
    pdf = pikepdf.new()
    font_file = pdf.make_stream(
        clear + encrypted + trailer,
        Length1=len(clear),
        Length2=len(encrypted),
        Length3=len(trailer),
    )
    descriptor = Dictionary(
        **DESCRIPTOR, FontName=Name('/TestT1'), Flags=32, FontFile=font_file
    )
    font = Dictionary(
        Type=Name.Font,
        Subtype=Name.Type1,
        BaseFont=Name('/TestT1'),
        FirstChar=65,
        LastChar=66,
        Widths=Array([600, 700]),
        Encoding=Name.WinAnsiEncoding,
        FontDescriptor=pdf.make_indirect(descriptor),
    )
    _page(pdf, font, b'BT /F1 24 Tf 72 700 Td (AB) Tj ET')
    return pdf


def type1c_pdf(data: bytes) -> pikepdf.Pdf:
    """A simple Type 1 font (FontFile3 /Type1C) showing (A), width 600."""
    pdf = pikepdf.new()
    descriptor = Dictionary(
        **DESCRIPTOR,
        FontName=Name('/TestCFF'),
        Flags=32,
        FontFile3=pdf.make_stream(data, Subtype=Name.Type1C),
    )
    font = Dictionary(
        Type=Name.Font,
        Subtype=Name.Type1,
        BaseFont=Name('/TestCFF'),
        FirstChar=65,
        LastChar=65,
        Widths=Array([600]),
        Encoding=Name.WinAnsiEncoding,
        FontDescriptor=pdf.make_indirect(descriptor),
    )
    _page(pdf, font, b'BT /F1 24 Tf 72 700 Td (A) Tj ET')
    return pdf


def check(pdf: pikepdf.Pdf, path: Path) -> ValidationReport:
    save_candidate(make_candidate(pdf, '2'), path, '2')
    return validate(path, '2b')


def assert_ambiguous(
    pdf: pikepdf.Pdf, path: Path, key: str, verapdf_rule: str | None = WIDTH_RULE
) -> None:
    report = check(pdf, path)
    rule = f'pikepdf:{key}'
    kinds = {f.kind for f in report.findings if f.rule == rule}
    assert kinds == {'unsupported'}, report.summary()
    if verapdf_rule is not None:
        assert_verapdf_fails(path, '2b', verapdf_rule)


def assert_accepted(pdf: pikepdf.Pdf, path: Path, *, verapdf: bool = True) -> None:
    report = check(pdf, path)
    assert report.passed, report.summary()
    if verapdf:
        assert_verapdf_agrees(path, '2b')


# --- CIDFont /W -----------------------------------------------------------------

SHOW_CID_2 = b'BT /F1 24 Tf 72 700 Td <0002> Tj ET'


@pytest.mark.parametrize(
    'w, verapdf_rule',
    [
        ([2, [600], 2, [700]], WIDTH_RULE),
        ([2, 2, 600, 2, [700]], WIDTH_RULE),
        ([2, [700], 1, 3, 600], WIDTH_RULE),
        # veraPDF happens to pick the width that matches the program
        ([1, 3, 600, 2, 2, 700], None),
    ],
)
def test_cid_widths_conflict(tmp_path, w, verapdf_rule):
    assert parse_cid_widths(Array(w))[1] == {2}
    pdf = type0_pdf(SHOW_CID_2, w=w)
    assert_ambiguous(pdf, tmp_path / 'w.pdf', 'font-widths-ambiguous', verapdf_rule)


@pytest.mark.parametrize(
    'w',
    [
        [2, [600], 2, [600]],
        [1, [250, 600], 2, 2, 600],
        [1, 3, 600, 2, [600]],
        # CID 3 has two widths but is not shown
        [2, [600, 800], 3, [900]],
    ],
)
def test_cid_widths_duplicates_that_agree(tmp_path, w):
    assert_accepted(type0_pdf(SHOW_CID_2, w=w), tmp_path / 'w.pdf')


def test_cid_widths_conflict_invisible(tmp_path):
    content = b'BT 3 Tr /F1 24 Tf 72 700 Td <0002> Tj ET'
    assert_accepted(type0_pdf(content, w=[2, [600], 2, [700]]), tmp_path / 'w.pdf')


# --- embedded CMaps -------------------------------------------------------------

CMAP_HEADER = b"""/CIDInit /ProcSet findresource begin
12 dict begin
begincmap
/CIDSystemInfo << /Registry (Adobe) /Ordering (Identity) /Supplement 0 >> def
/CMapName /Test-H def
/CMapType 1 def
"""
CMAP_FOOTER = b"""
endcmap
CMapName currentdict /CMap defineresource pop
end
end
"""
CS1 = b'1 begincodespacerange <00> <FF> endcodespacerange\n'


def parse(body: bytes):
    with pikepdf.new() as pdf:
        return parse_embedded_cmap(pdf.make_stream(CMAP_HEADER + body + CMAP_FOOTER))


@pytest.mark.parametrize(
    'body',
    [
        b'1 begincidchar <41> 2 endcidchar 1 begincidrange <41> <41> 9 endcidrange',
        b'1 begincidrange <41> <41> 9 endcidrange 1 begincidchar <41> 2 endcidchar',
        b'2 begincidrange <41> <41> 2 <00> <FF> 1000 endcidrange',
        b'2 begincidrange <40> <42> 1 <41> <50> 9 endcidrange',
        b'2 begincidchar <41> 2 <41> 9 endcidchar',
        b'2 beginnotdefrange <40> <42> 1 <41> <41> 2 endnotdefrange',
    ],
)
def test_cmap_conflicting_mappings(body):
    cmap = parse(CS1 + body)
    with pytest.raises(CMapError) as e:
        cmap.decode(b'A')
    assert e.value.reason == 'ambiguous'


@pytest.mark.parametrize(
    'body',
    [
        b'1 begincidchar <41> 2 endcidchar 1 begincidrange <40> <42> 1 endcidrange',
        b'2 begincidrange <40> <42> 1 <41> <50> 2 endcidrange',
        b'2 begincidchar <41> 2 <41> 2 endcidchar',
        # A notdef mapping only applies to codes without a CID mapping
        b'1 begincidchar <41> 2 endcidchar 1 beginnotdefrange <00> <FF> 1 '
        b'endnotdefrange',
    ],
)
def test_cmap_mappings_that_agree(body):
    assert parse(CS1 + body).decode(b'A') == [(0x41, 2)]


def test_cmap_conflict_only_matters_where_used():
    cmap = parse(CS1 + b'2 begincidrange <40> <42> 1 <42> <50> 9 endcidrange')
    assert cmap.decode(b'A') == [(0x41, 2)]
    with pytest.raises(CMapError) as e:
        cmap.decode(b'B')
    assert e.value.reason == 'ambiguous'


@pytest.mark.parametrize(
    'codespace',
    [
        b'2 begincodespacerange <0000> <FFFF> <00> <7F> endcodespacerange',
        b'2 begincodespacerange <00> <7F> <0000> <FFFF> endcodespacerange',
        b'2 begincodespacerange <00> <80> <8040> <9FFC> endcodespacerange',
        b'2 begincodespacerange <00> <80> <40> <FF> endcodespacerange',
        b'2 begincodespacerange <0000> <8080> <000000> <FFFFFF> endcodespacerange',
    ],
)
def test_cmap_overlapping_codespace(codespace):
    with pytest.raises(CMapError) as e:
        parse(codespace + b'\n1 begincidchar <41> 2 endcidchar')
    assert e.value.reason == 'ambiguous'


@pytest.mark.parametrize(
    'codespace',
    [
        b'2 begincodespacerange <00> <80> <8140> <9FFC> endcodespacerange',
        b'2 begincodespacerange <00> <7F> <80> <FF> endcodespacerange',
        b'2 begincodespacerange <0000> <80FF> <810000> <FFFFFF> endcodespacerange',
        # The second bytes differ, so no 2-byte code is a prefix of a 3-byte one
        b'2 begincodespacerange <0000> <FF7F> <008000> <FFFFFF> endcodespacerange',
    ],
)
def test_cmap_disjoint_codespace(codespace):
    parse(codespace + b'\n1 begincidchar <41> 2 endcidchar')


SHOW_A = b'BT /F1 24 Tf 72 700 Td <41> Tj ET'


@pytest.mark.parametrize(
    'cmap, content',
    [
        (
            CS1 + b'1 begincidchar <41> 2 endcidchar\n'
            b'1 begincidrange <41> <41> 9 endcidrange',
            SHOW_A,
        ),
        (CS1 + b'2 begincidrange <41> <41> 2 <00> <FF> 1000 endcidrange', SHOW_A),
    ],
)
def test_cmap_conflict_denied(tmp_path, cmap, content):
    assert_ambiguous(
        type0_pdf(content, cmap=cmap), tmp_path / 'c.pdf', 'font-cmap-ambiguous'
    )


def test_cmap_codespace_overlap_denied(tmp_path):
    cmap = (
        b'2 begincodespacerange <0000> <FFFF> <00> <7F> endcodespacerange\n'
        b'3 begincidchar <41> 2 <42> 3 <4142> 9 endcidchar'
    )
    pdf = type0_pdf(b'BT /F1 24 Tf 72 700 Td <4142> Tj ET', cmap=cmap)
    assert_ambiguous(pdf, tmp_path / 'c.pdf', 'font-cmap-ambiguous')


def test_cmap_agreeing_mappings_accepted(tmp_path):
    cmap = (
        CS1 + b'1 begincidchar <41> 2 endcidchar\n'
        b'2 begincidrange <40> <42> 1 <41> <41> 2 endcidrange'
    )
    assert_accepted(type0_pdf(SHOW_A, cmap=cmap), tmp_path / 'c.pdf')


# --- symbolic TrueType (3,0) cmap ---------------------------------------------------


@pytest.mark.parametrize(
    'cmap_30',
    [
        {0x20: 'space', 0xF041: 'B'},
        {0xF020: 'space', 0xF141: 'B'},
        {0x41: '.notdef', 0xF041: 'B'},
        {0x41: 'A', 0xF041: 'B'},
    ],
)
def test_symbolic_30_mixed_ranges_denied(tmp_path, cmap_30):
    rule = 'ISO_19005_2:6.2.11.4.1-2' if 0x41 not in cmap_30 else None
    assert_ambiguous(
        symbolic_truetype_pdf(cmap_30),
        tmp_path / 's.pdf',
        'font-symbolic-cmap-ambiguous',
        rule,
    )


@pytest.mark.parametrize(
    'cmap_30',
    [
        {0xF020: 'space', 0xF041: 'B'},
        {0x20: 'space', 0x41: 'B'},
        {0xF220: 'space', 0xF241: 'B'},
    ],
)
def test_symbolic_30_single_range_accepted(tmp_path, cmap_30):
    assert_accepted(symbolic_truetype_pdf(cmap_30), tmp_path / 's.pdf')


def test_symbolic_30_mixed_ranges_that_agree_accepted(tmp_path):
    pdf = symbolic_truetype_pdf({0x20: 'space', 0x41: 'B', 0xF041: 'B'})
    assert_accepted(pdf, tmp_path / 's.pdf', verapdf=False)


# --- Type 1 programs ------------------------------------------------------------

T1_GLYPHS = [('.notdef', 500), ('space', 250), ('A', 600), ('B', 700)]


def test_type1_accepted(tmp_path):
    assert_accepted(type1_pdf(make_type1(T1_GLYPHS)), tmp_path / 't.pdf')


def test_type1_charstrings_count_too_small(tmp_path):
    parts = make_type1(T1_GLYPHS, charstrings_count=2)
    assert_ambiguous(type1_pdf(parts), tmp_path / 't.pdf', 'font-program-ambiguous')


def test_type1_charstrings_count_larger_accepted(tmp_path):
    parts = make_type1(T1_GLYPHS, charstrings_count=20)
    assert_accepted(type1_pdf(parts), tmp_path / 't.pdf')


@pytest.mark.parametrize('early', [4, None])
def test_type1_late_len_iv_differs(tmp_path, early):
    parts = make_type1(T1_GLYPHS, len_iv=0, early_len_iv=early, late_len_iv=0)
    assert_ambiguous(type1_pdf(parts), tmp_path / 't.pdf', 'font-program-ambiguous')


@pytest.mark.parametrize('early', [4, None])
def test_type1_late_len_iv_same(tmp_path, early):
    parts = make_type1(T1_GLYPHS, len_iv=4, early_len_iv=early, late_len_iv=4)
    assert_accepted(type1_pdf(parts), tmp_path / 't.pdf')


def test_type1_len_iv_redefined_before_charstrings(tmp_path):
    clear, encrypted, trailer = make_type1(T1_GLYPHS, len_iv=0, early_len_iv=0)
    plain, _ = eexec.decrypt(encrypted, 55665)
    plain = plain.replace(b'/lenIV 0 def', b'/lenIV 4 def /lenIV 0 def', 1)
    encrypted, _ = eexec.encrypt(plain, 55665)
    assert_accepted(type1_pdf((clear, encrypted, trailer)), tmp_path / 't.pdf')


# --- CFF charset ----------------------------------------------------------------


def test_cff_accepted(tmp_path):
    assert_accepted(type1c_pdf(make_cff(GLYPHS[:4])), tmp_path / 'c.pdf')


def test_cff_duplicate_charset_name(tmp_path):
    data = bytearray(make_cff(GLYPHS[:4]))
    font_set = CFFFontSet()
    font_set.decompile(BytesIO(bytes(data)), None)
    offset = font_set[font_set.fontNames[0]].rawDict['charset']
    assert data[offset] == 0  # format 0: one SID per glyph after .notdef
    # Rename glyph 3 from B (SID 35) to A (SID 34)
    data[offset + 5 : offset + 7] = (34).to_bytes(2, 'big')
    assert_ambiguous(
        type1c_pdf(bytes(data)), tmp_path / 'c.pdf', 'font-program-ambiguous'
    )
