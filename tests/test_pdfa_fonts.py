# SPDX-FileCopyrightText: 2026 James R. Barlow
# SPDX-License-Identifier: MPL-2.0

from __future__ import annotations

import pytest

pytest.importorskip('jsonschema')

import re
import shutil
import subprocess
from io import BytesIO
from pathlib import Path

from conftest import verapdf_command
from fontTools.ttLib import TTFont
from pdfa_samples import (
    add_cidsets,
    assert_verapdf_agrees,
    find_type1_font,
    make_candidate,
    make_image_only_pdf,
    make_simple_truetype_pdf,
    make_type1_pdf,
    save_candidate,
    verapdf_failed_rules,
)

import pikepdf
from pikepdf import Array, Dictionary, Name
from pikepdf.pdfa import Flavour, validate
from pikepdf.pdfa._cmap import CMapError, parse_embedded_cmap
from pikepdf.pdfa._context import ValidationContext
from pikepdf.pdfa._encodings import (
    MAC_ROMAN,
    STANDARD,
    WIN_ANSI,
    DifferencesError,
    apply_differences,
    encoding_table,
    mac_roman_codes,
    parse_differences,
)
from pikepdf.pdfa._fontprogram import FontProgramError, Type1Program
from pikepdf.pdfa._fonts import RULES
from pikepdf.pdfa._report import ValidationReport
from pikepdf.pdfa._schemas import SchemaSet
from pikepdf.pdfa._walker import DocumentWalker

# --- encodings ---------------------------------------------------------------


def test_encoding_tables():
    assert encoding_table(WIN_ANSI)[0x41] == 'A'
    assert encoding_table(WIN_ANSI)[0x80] == 'Euro'
    assert encoding_table(WIN_ANSI)[160] == 'space'
    assert encoding_table(WIN_ANSI)[173] == 'hyphen'
    assert encoding_table(MAC_ROMAN)[0x8A] == 'adieresis'
    assert encoding_table(MAC_ROMAN)[202] == 'space'
    assert encoding_table(STANDARD)[0xAE] == 'fi'
    assert 0x80 not in encoding_table(STANDARD)
    assert mac_roman_codes()['adieresis'] == 0x8A
    assert mac_roman_codes()['space'] == 32
    with pytest.raises(KeyError):
        encoding_table('MacExpertEncoding')


def test_differences():
    diffs = Array([32, Name.space, Name.a, 100, Name('/uni0041')])
    assert parse_differences(diffs) == {32: 'space', 33: 'a', 100: 'uni0041'}
    merged = apply_differences(encoding_table(WIN_ANSI), diffs)
    assert merged[33] == 'a'
    assert merged[0x42] == 'B'


@pytest.mark.parametrize(
    'diffs',
    [
        Array([Name.a]),
        Array([255, Name.a, Name.b]),
        Array([-1, Name.a]),
        Array([32, pikepdf.String('a')]),
        Array([32, 1.5]),
        pikepdf.Dictionary(),
    ],
)
def test_differences_malformed(diffs):
    with pytest.raises(DifferencesError):
        parse_differences(diffs)


# --- embedded CMaps ----------------------------------------------------------

CMAP_HEADER = b"""/CIDInit /ProcSet findresource begin
12 dict begin
begincmap
/CIDSystemInfo << /Registry (Adobe) /Ordering (Identity) /Supplement 0 >> def
/CMapName /Test-H def
/CMapType 1 def
"""
CMAP_FOOTER = b"""endcmap
CMapName currentdict /CMap defineresource pop
end
end
"""


def cmap_stream(pdf: pikepdf.Pdf, body: bytes) -> pikepdf.Stream:
    return pdf.make_stream(
        CMAP_HEADER + body + CMAP_FOOTER, Type=Name.CMap, CMapName=Name('/Test-H')
    )


@pytest.fixture
def pdf():
    with pikepdf.new() as pdf:
        yield pdf


def test_cmap_cidchar_two_byte(pdf):
    cmap = parse_embedded_cmap(
        cmap_stream(
            pdf,
            b"""1 begincodespacerange <0000> <FFFF> endcodespacerange
2 begincidchar <0001> 20220 <0020> 1 endcidchar
""",
        )
    )
    assert cmap.wmode is None
    assert cmap.cid_system_info == {
        'Registry': 'Adobe',
        'Ordering': 'Identity',
        'Supplement': 0,
    }
    assert cmap.decode(b'\x00\x01\x00\x20') == [(1, 20220), (0x20, 1)]
    with pytest.raises(CMapError) as e:
        cmap.decode(b'\x00\x02')
    assert e.value.reason == 'unmapped'
    with pytest.raises(CMapError) as e:
        cmap.decode(b'\x00')
    assert e.value.reason == 'codespace'


def test_cmap_mixed_codespace_and_ranges(pdf):
    cmap = parse_embedded_cmap(
        cmap_stream(
            pdf,
            b"""2 begincodespacerange <00> <80> <8140> <9FFC> endcodespacerange
2 begincidrange <20> <7e> 1 <8140> <817e> 633 endcidrange
1 beginnotdefrange <00> <1f> 7 endnotdefrange
/WMode 1 def
""",
        )
    )
    assert cmap.wmode == 1
    assert cmap.decode(b'A\x81\x41\x05') == [
        (0x41, 0x41 - 0x20 + 1),
        (0x8141, 634),
        (0x05, 7),
    ]
    assert cmap.max_cid == 633 + 0x7E - 0x40


def test_cmap_identity_range(pdf):
    cmap = parse_embedded_cmap(
        cmap_stream(
            pdf,
            b"""1 begincodespacerange <0000> <FFFF> endcodespacerange
1 begincidrange <0000> <FFFF> 0 endcidrange
""",
        )
    )
    assert cmap.decode(b'\x01\x02\xff\xff') == [(0x102, 0x102), (0xFFFF, 0xFFFF)]
    assert cmap.max_cid == 0xFFFF


def test_cmap_nested_cidsysteminfo_dict(pdf):
    cmap = parse_embedded_cmap(
        pdf.make_stream(
            b"""/CIDInit /ProcSet findresource begin 12 dict begin begincmap
/CIDSystemInfo 3 dict dup begin
  /Registry (Adobe) def /Ordering (Japan1) def /Supplement 6 def
end def
1 begincodespacerange <00> <FF> endcodespacerange
1 begincidchar <41> 34 endcidchar
endcmap CMapName currentdict /CMap defineresource pop end end
"""
        )
    )
    assert cmap.cid_system_info == {
        'Registry': 'Adobe',
        'Ordering': 'Japan1',
        'Supplement': 6,
    }
    assert cmap.decode(b'A') == [(0x41, 34)]


@pytest.mark.parametrize(
    'body, reason',
    [
        (b'/Other-H usecmap\n', 'usecmap'),
        (
            b'1 begincodespacerange <0000> <FFFF> endcodespacerange\n'
            b'1 begincidchar <0001> 65536 endcidchar\n',
            'cid-limit',
        ),
        (
            b'1 begincodespacerange <0000> <FFFF> endcodespacerange\n'
            b'1 begincidrange <0000> <00FF> 65500 endcidrange\n',
            'cid-limit',
        ),
        (b'1 begincodespacerange <0000> <FF> endcodespacerange\n', 'syntax'),
        (b'1 begincodespacerange <0000> endcodespacerange\n', 'syntax'),
        (b'1 begincidchar <0001> (x) endcidchar\n', 'syntax'),
        (b'1 beginbfchar <0001> <0041> endbfchar\n', 'syntax'),
        (b'systemdict /foo get exec\n', 'syntax'),
        (b'1 begincodespacerange <0000> <FFFF', 'syntax'),
        (
            b'1 begincodespacerange <0000> <FFFF> endcodespacerange\n'
            b'1 begincidrange <02FF> <0100> 1 endcidrange\n',
            'syntax',
        ),
    ],
)
def test_cmap_errors(pdf, body, reason):
    with pytest.raises(CMapError) as e:
        parse_embedded_cmap(cmap_stream(pdf, body))
    assert e.value.reason == reason


def test_cmap_usecmap_in_dict_is_error(pdf):
    stream = cmap_stream(pdf, b'1 begincodespacerange <00> <FF> endcodespacerange\n')
    stream.UseCMap = Name('/Identity-H')
    with pytest.raises(CMapError) as e:
        parse_embedded_cmap(stream)
    assert e.value.reason == 'usecmap'


# --- fixtures ----------------------------------------------------------------

RESOURCES = Path(__file__).parent / 'resources' / 'pdfa'


def rule_ids(report: ValidationReport) -> set[str]:
    return {f.rule for f in report.findings}


def check(pdf: pikepdf.Pdf, path: Path, part: str = '2') -> ValidationReport:
    save_candidate(pdf, path, part)
    return validate(path, f'{part}b')


def assert_approved(pdf: pikepdf.Pdf, path: Path, part: str = '2') -> None:
    report = check(pdf, path, part)
    assert report.passed, report.summary()
    assert_verapdf_agrees(path, f'{part}b')


def assert_denied(
    pdf: pikepdf.Pdf,
    path: Path,
    rule: str,
    part: str = '2',
    *,
    kind: str | None = None,
    verapdf_fails: bool = False,
) -> ValidationReport:
    report = check(pdf, path, part)
    assert rule in rule_ids(report), report.summary()
    if kind is not None:
        assert {f.kind for f in report.findings if f.rule == rule} == {kind}
    if verapdf_fails:
        failed = verapdf_failed_rules(path, f'{part}b')
        if failed is not None:
            assert rule in failed, failed
    return report


@pytest.fixture(scope='module')
def renders():
    """fpdf2 renders of Latin text, visible (Tr 0) and invisible (Tr 3).

    Rendered once with OCRmyPDF's fpdf2 renderer from 'Hello wörld fi'.
    """
    return {
        0: RESOURCES / 'fpdf2_latin_tr0.pdf',
        3: RESOURCES / 'fpdf2_latin_tr3.pdf',
    }


def fpdf2_font(pdf: pikepdf.Pdf) -> pikepdf.Dictionary:
    return pdf.pages[0].Resources.Font.F1


def cidfont(pdf: pikepdf.Pdf) -> pikepdf.Dictionary:
    return fpdf2_font(pdf).DescendantFonts[0]


def num_glyphs(cid_font: pikepdf.Dictionary) -> int:
    data = cid_font.FontDescriptor.FontFile2.read_bytes()
    return TTFont(BytesIO(data), lazy=True)['maxp'].numGlyphs


def set_cid_to_gid(pdf: pikepdf.Pdf, cid: int, gid: int | None) -> None:
    cid_font = cidfont(pdf)
    data = bytearray(cid_font.CIDToGIDMap.read_bytes())
    if gid is None:
        data = data[: 2 * cid]
    else:
        data[2 * cid : 2 * cid + 2] = gid.to_bytes(2, 'big')
    cid_font.CIDToGIDMap.write(bytes(data))


# --- OCRmyPDF output approves --------------------------------------------------


@pytest.mark.parametrize('part', ['1', '2', '3'])
@pytest.mark.parametrize('mode', [0, 3])
def test_fpdf2_latin_approved(renders, tmp_path, part, mode):
    assert_approved(make_candidate(renders[mode], part), tmp_path / 'c.pdf', part)


@pytest.mark.parametrize('part', ['1', '2'])
def test_occulta_fallback_approved(tmp_path, part):
    # Rendered from '\ue000 \u13a0x', for which no installed font has glyphs
    source = RESOURCES / 'fpdf2_occulta.pdf'
    with pikepdf.open(source) as pdf:
        assert 'Occulta' in str(fpdf2_font(pdf).BaseFont)
    assert_approved(make_candidate(source, part), tmp_path / 'c.pdf', part)


@pytest.mark.parametrize('part', ['1', '2'])
def test_fpdf2_cjk_approved(tmp_path, part):
    # Rendered from '日本語 テキスト' with a Noto Sans CJK font
    source = RESOURCES / 'fpdf2_cjk.pdf'
    with pikepdf.open(source) as pdf:
        font = fpdf2_font(pdf)
        assert isinstance(font.Encoding, pikepdf.Stream)
        assert font.DescendantFonts[0].Subtype == Name.CIDFontType0
    assert_approved(make_candidate(source, part), tmp_path / 'c.pdf', part)


def test_fpdf2_cjk_cidset(tmp_path):
    # Rendered from '日本語' with a Noto Sans CJK font
    source = RESOURCES / 'fpdf2_cjk_short.pdf'
    pdf = make_candidate(source, '2')
    add_cidsets(pdf)
    # CIDSet equal to the CFF charset CIDs (CID 0 included or not) approves
    assert_approved(pdf, tmp_path / 'with.pdf')
    descriptor = cidfont(pdf).FontDescriptor
    data = bytearray(descriptor.CIDSet.read_bytes())
    data[0] ^= 0x80
    descriptor.CIDSet.write(bytes(data))
    assert_approved(pdf, tmp_path / 'toggled0.pdf')
    data[0] |= 0x40  # CID 1 is in the program; set CID 2, which is not
    data[0] |= 0x20
    descriptor.CIDSet.write(bytes(data))
    assert_denied(
        pdf, tmp_path / 'extra.pdf', 'ISO_19005_2:6.2.11.4.2-2', verapdf_fails=True
    )


@pytest.mark.parametrize('part', ['1', '2'])
def test_sandwich_font_approved(tmp_path, part):
    assert_approved(
        make_candidate(RESOURCES / 'graph_ocred.pdf', part), tmp_path / 'c.pdf', part
    )


@pytest.mark.parametrize('part', ['1', '2'])
def test_simple_truetype_approved(tmp_path, part):
    assert_approved(make_simple_truetype_pdf(part), tmp_path / 'c.pdf', part)


@pytest.fixture
def ghostscript_type1c(tmp_path):
    """Return a factory for a PDF with Ghostscript-embedded Type1C fonts."""
    if shutil.which('gs') is None:
        pytest.skip("Ghostscript not installed")

    def make(text: str) -> Path:
        out = tmp_path / 'gs.pdf'
        subprocess.run(
            [
                'gs',
                '-q',
                '-dNOPAUSE',
                '-dBATCH',
                '-dSAFER',
                '-sDEVICE=pdfwrite',
                '-dPDFSETTINGS=/prepress',
                '-dEmbedAllFonts=true',
                '-o',
                str(out),
                '-c',
                f'/Helvetica findfont 24 scalefont setfont 72 700 moveto ({text}) '
                'show showpage',
            ],
            check=True,
        )
        return out

    return make


def test_ghostscript_type1c_approved(tmp_path, ghostscript_type1c):
    source = ghostscript_type1c('Hello world')
    with pikepdf.open(source) as pdf:
        font = next(iter(pdf.pages[0].Resources.Font.values()))
        assert font.FontDescriptor.FontFile3.Subtype == Name.Type1C
        assert '/CharSet' in font.FontDescriptor
    assert_approved(make_candidate(source, '2'), tmp_path / 'c.pdf')


def test_ghostscript_type1c_notdef(tmp_path, ghostscript_type1c):
    # Ghostscript encodes a character Helvetica's encoding lacks as .notdef
    source = ghostscript_type1c('W\\366rld')
    assert_denied(
        make_candidate(source, '2'),
        tmp_path / 'c.pdf',
        'ISO_19005_2:6.2.11.8-1',
        verapdf_fails=True,
    )


def test_ghostscript_type1c_charset_mismatch(tmp_path, ghostscript_type1c):
    pdf = make_candidate(ghostscript_type1c('Hello'), '2')
    font = next(iter(pdf.pages[0].Resources.Font.values()))
    font.FontDescriptor.CharSet = pikepdf.String('/H/e/l')
    assert_denied(pdf, tmp_path / 'c.pdf', 'ISO_19005_2:6.2.11.4.2-1')
    pdf1 = make_candidate(ghostscript_type1c('Hello'), '1')
    font = next(iter(pdf1.pages[0].Resources.Font.values()))
    del font.FontDescriptor['/CharSet']
    assert_denied(pdf1, tmp_path / 'c1.pdf', 'ISO_19005_1:6.3.5-2', '1')


def test_fontfile3_opentype_denied_in_1b(tmp_path, ghostscript_type1c):
    pdf = make_candidate(ghostscript_type1c('Hello'), '1')
    font = next(iter(pdf.pages[0].Resources.Font.values()))
    font.FontDescriptor.FontFile3.Subtype = Name.OpenType
    assert_denied(pdf, tmp_path / 'c.pdf', 'ISO_19005_1:6.3.2-7', '1')


@pytest.fixture(scope='module')
def type1_font() -> Path:
    path = find_type1_font()
    if path is None:
        pytest.skip("no Type 1 font file (PFA/PFB) installed")
    return path


def type1_descriptor(pdf: pikepdf.Pdf) -> pikepdf.Dictionary:
    return fpdf2_font(pdf).FontDescriptor


TYPE1_GLYPH = {'1': 'ISO_19005_1:6.3.5-1', '2': 'ISO_19005_2:6.2.11.4.1-2'}
TYPE1_WIDTH = {'1': 'ISO_19005_1:6.3.6-1', '2': 'ISO_19005_2:6.2.11.5-1'}
TYPE1_CHARSET = {'1': 'ISO_19005_1:6.3.5-2', '2': 'ISO_19005_2:6.2.11.4.2-1'}


@pytest.mark.parametrize('part', ['1', '2'])
def test_type1_fontfile_approved(tmp_path, type1_font, part):
    pdf = make_type1_pdf(type1_font, part)
    assert '/FontFile' in type1_descriptor(pdf)
    assert_approved(pdf, tmp_path / 'c.pdf', part)


def test_type1_fontfile_not_subset_approved(tmp_path, type1_font):
    pdf = make_type1_pdf(type1_font, '2', subset=False)
    assert '/CharSet' not in type1_descriptor(pdf)
    assert_approved(pdf, tmp_path / 'c.pdf', '2')


def test_type1_fontfile_builtin_encoding_approved(tmp_path, type1_font):
    pdf = make_type1_pdf(type1_font, '2')
    del fpdf2_font(pdf)['/Encoding']
    assert_approved(pdf, tmp_path / 'c.pdf', '2')


def test_type1_fontfile_hex_eexec_unsupported(tmp_path, type1_font):
    # veraPDF reports a hexadecimal eexec section as not embedded
    pdf = make_type1_pdf(type1_font, '2')
    stream = type1_descriptor(pdf).FontFile
    data = stream.read_bytes()
    clear, rest = int(stream.Length1), int(stream.Length2)
    cipher = data[clear : clear + rest].hex().encode()
    lines = b'\n'.join(cipher[i : i + 64] for i in range(0, len(cipher), 64))
    stream.write(data[:clear] + lines + b'\n' + data[clear + rest :])
    stream.Length2 = len(lines) + 1
    assert_denied(pdf, tmp_path / 'c.pdf', 'pikepdf:font-program', kind='unsupported')
    failed = verapdf_failed_rules(tmp_path / 'c.pdf', '2b')
    assert failed is None or 'ISO_19005_2:6.2.11.4.1-1' in failed, failed


@pytest.mark.parametrize('part', ['1', '2'])
def test_type1_fontfile_differences_missing_glyph(tmp_path, type1_font, part):
    pdf = make_type1_pdf(type1_font, part)
    fpdf2_font(pdf).Encoding = Dictionary(
        Type=Name.Encoding,
        BaseEncoding=Name.WinAnsiEncoding,
        Differences=Array([72, Name('/nosuchglyph')]),
    )
    assert_denied(pdf, tmp_path / 'c.pdf', TYPE1_GLYPH[part], part, verapdf_fails=True)


@pytest.mark.parametrize('part', ['1', '2'])
def test_type1_fontfile_width_mismatch(tmp_path, type1_font, part):
    pdf = make_type1_pdf(type1_font, part)
    widths = fpdf2_font(pdf).Widths
    widths[ord('H') - 32] = int(widths[ord('H') - 32]) + 2
    assert_denied(pdf, tmp_path / 'c.pdf', TYPE1_WIDTH[part], part, verapdf_fails=True)


@pytest.mark.parametrize('part', ['1', '2'])
def test_type1_fontfile_charset_extra_name(tmp_path, type1_font, part):
    pdf = make_type1_pdf(type1_font, part)
    descriptor = type1_descriptor(pdf)
    descriptor.CharSet = pikepdf.String(bytes(descriptor.CharSet) + b'/nosuchglyph')
    assert_denied(pdf, tmp_path / 'c.pdf', TYPE1_CHARSET[part], part)


def test_type1_fontfile_charset_required_in_1b(tmp_path, type1_font):
    pdf = make_type1_pdf(type1_font, '1')
    del type1_descriptor(pdf)['/CharSet']
    assert_denied(pdf, tmp_path / 'c.pdf', TYPE1_CHARSET['1'], '1')


@pytest.mark.parametrize('keep', [0.5, 0.99])
def test_type1_fontfile_truncated_unsupported(tmp_path, type1_font, keep):
    pdf = make_type1_pdf(type1_font, '2')
    stream = type1_descriptor(pdf).FontFile
    data = stream.read_bytes()
    stream.write(data[: int(len(data) * keep)])
    assert_denied(pdf, tmp_path / 'c.pdf', 'pikepdf:font-program', kind='unsupported')


def test_type1_fontfile_font_matrix_unsupported(tmp_path, type1_font):
    pdf = make_type1_pdf(type1_font, '2')
    stream = type1_descriptor(pdf).FontFile
    data = stream.read_bytes()
    clear = int(stream.Length1)
    head = data[:clear]
    old = re.search(rb'/FontMatrix\s*\[[^\]]*\]', head)
    assert old is not None
    new = b'/FontMatrix [0.002 0 0 0.002 0 0]'
    head = head.replace(old.group(0), new)
    stream.write(head + data[clear:])
    stream.Length1 = len(head)
    assert_denied(pdf, tmp_path / 'c.pdf', 'pikepdf:font-program', kind='unsupported')


def test_type1_program_adapter(type1_font):
    pdf = make_type1_pdf(type1_font, '2')
    program = Type1Program(type1_descriptor(pdf).FontFile.read_bytes())
    names = program.glyph_names()
    assert names[0] == '.notdef'
    assert len(names) == program.num_glyphs == len(set(names))
    gid = program.gid_for_name('H')
    assert gid is not None and program.has_gid(gid)
    assert program.gid_for_name('nosuchglyph') is None
    assert not program.has_gid(program.num_glyphs)
    assert program.advance_1000(gid) == int(fpdf2_font(pdf).Widths[ord('H') - 32])
    builtin = program.builtin_encoding()
    assert builtin is None or builtin[ord('H')] == 'H'
    assert program.cmap_tables() == []


@pytest.mark.parametrize(
    'data',
    [b'', b'%!PS-AdobeFont-1.0: X\n/FontType 1 def\n', b'\x80\x01garbage'],
)
def test_type1_program_rejects_garbage(data):
    with pytest.raises(FontProgramError):
        Type1Program(data)


@pytest.mark.parametrize('loop', [b'0 0 1 {pop} for', b'0 1 1000000000 {pop} for'])
def test_type1_program_rejects_long_loops(loop):
    from fontTools.misc import eexec

    cipher, _ = eexec.encrypt(b'\xff\xfe\xfd\xfc mark currentfile closefile\n', 55665)
    assert cipher[0] not in b' \t\r\n'
    data = b'%!PS-AdobeFont-1.0: X\n' + loop + b'\ncurrentfile eexec\n' + cipher
    with pytest.raises(FontProgramError, match='loop'):
        Type1Program(data)


NON_UTF8_NAME = pikepdf.Object.parse(b'<< /N /\xb0\xa1 >>').N


def font_findings(report: ValidationReport):
    return [
        f
        for f in report.findings
        if '(Font)' in f.where
        or ' font ' in f.where
        or f.rule in _FONT_RULE_IDS
        or f.rule.startswith(('pikepdf:font', 'pikepdf:text', 'pikepdf:notdef'))
    ]


_FONT_RULE_IDS = {
    f'ISO_19005_{part}:{clause}'
    for part1, part23 in RULES.values()
    for part, clause in (('1', part1), ('2', part23), ('3', part23))
    if clause
}


@pytest.mark.parametrize(
    'name, fonts',
    [('link.pdf', 2), ('truetype_font_nomapping.pdf', 1), ('overlay.pdf', 4)],
)
def test_resource_fonts_pass_font_tier(tmp_path, name, fonts):
    """Fonts of scanner and office files pass; other constructs are step 4."""
    pdf = make_candidate(RESOURCES / name, '2')
    # Remove producer-private keys, which stop the walker before the fonts
    for key in ('/PDFpenVersion',):
        if key in pdf.trailer:
            del pdf.trailer[key]
    for page in pdf.pages:
        for key in ('/Thumb', '/PDFpenImprints'):
            if key in page.obj:
                del page.obj[key]
    path = save_candidate(pdf, tmp_path / name, '2')
    report = validate(path, '2b')
    assert font_findings(report) == [], report.summary()
    with pikepdf.open(path) as pdf:
        ctx = ValidationContext(Flavour('2b'), pdf, ValidationReport(Flavour('2b')))
        DocumentWalker(ctx, SchemaSet.for_flavour('2b')).walk()
        infos = [*ctx.fonts.values(), *ctx.direct_fonts]
        assert all(info.ok for info in infos)
        assert len([info for info in infos if info.usage]) == fonts


def test_symbolic_truetype_with_encoding_denied(tmp_path):
    pdf = make_candidate(RESOURCES / 'link.pdf', '2')
    pdf.pages[0].Resources.Font.TT0.Encoding = Name.WinAnsiEncoding
    report = check(pdf, tmp_path / 'c.pdf')
    assert 'ISO_19005_2:6.2.11.6-3' in rule_ids(report)


def test_symbolic_truetype_two_cmaps_denied_in_1b_only(tmp_path):
    name = 'truetype_font_nomapping.pdf'
    report = check(make_candidate(RESOURCES / name, '1'), tmp_path / '1.pdf', '1')
    assert 'ISO_19005_1:6.3.7-3' in rule_ids(report)
    report = check(make_candidate(RESOURCES / name, '2'), tmp_path / '2.pdf')
    assert font_findings(report) == []


# --- mutations of the fpdf2 CIDFontType2 -----------------------------------------


@pytest.mark.parametrize('mode', [0, 3])
def test_missing_fontfile_denied(renders, tmp_path, mode):
    pdf = make_candidate(renders[mode])
    del cidfont(pdf).FontDescriptor['/FontFile2']
    assert_denied(
        pdf, tmp_path / 'c.pdf', 'ISO_19005_2:6.2.11.4.1-1', kind='unsupported'
    )


def _bump_width(pdf: pikepdf.Pdf, delta: int) -> None:
    widths = cidfont(pdf).W
    widths[1][1] = widths[1][1] + delta


def test_width_mismatch_denied_when_visible(renders, tmp_path):
    pdf = make_candidate(renders[0])
    _bump_width(pdf, 2)
    assert_denied(pdf, tmp_path / 'c.pdf', 'ISO_19005_2:6.2.11.5-1', verapdf_fails=True)


def test_width_within_tolerance_approved(renders, tmp_path):
    pdf = make_candidate(renders[0])
    _bump_width(pdf, 1)
    assert_approved(pdf, tmp_path / 'c.pdf')


def test_width_mismatch_approved_when_invisible(renders, tmp_path):
    pdf = make_candidate(renders[3])
    _bump_width(pdf, 2)
    assert_approved(pdf, tmp_path / 'c.pdf')


def test_cid_to_gid_beyond_glyphs_denied(renders, tmp_path):
    pdf = make_candidate(renders[0])
    set_cid_to_gid(pdf, 1, num_glyphs(cidfont(pdf)))
    assert_denied(
        pdf, tmp_path / 'c.pdf', 'ISO_19005_2:6.2.11.4.1-2', verapdf_fails=True
    )


def test_cid_to_gid_beyond_glyphs_denied_when_invisible(renders, tmp_path):
    # veraPDF exempts Tr 3 from the glyph-present rule but then names the
    # glyph .notdef
    pdf = make_candidate(renders[3])
    set_cid_to_gid(pdf, 1, num_glyphs(cidfont(pdf)))
    assert_denied(pdf, tmp_path / 'c.pdf', 'ISO_19005_2:6.2.11.8-1', verapdf_fails=True)


@pytest.mark.parametrize('mode', [0, 3])
def test_cid_to_gid_zero_denied(renders, tmp_path, mode):
    # Stricter than veraPDF, which only names CID 0 .notdef
    pdf = make_candidate(renders[mode])
    set_cid_to_gid(pdf, 1, 0)
    assert_denied(pdf, tmp_path / 'c.pdf', 'ISO_19005_2:6.2.11.8-1')


@pytest.mark.parametrize('mode', [0, 3])
def test_cid_to_gid_truncated_denied(renders, tmp_path, mode):
    pdf = make_candidate(renders[mode])
    set_cid_to_gid(pdf, 1, None)
    assert_denied(pdf, tmp_path / 'c.pdf', 'ISO_19005_2:6.2.11.8-1', verapdf_fails=True)


@pytest.mark.parametrize('mode', [0, 3])
def test_cid_zero_is_notdef(renders, tmp_path, mode):
    pdf = make_candidate(renders[mode])
    pdf.pages[0].Contents.write(
        f'BT {mode} Tr /F1 12 Tf 72 72 Td <0000> Tj ET'.encode()
    )
    assert_denied(pdf, tmp_path / 'c.pdf', 'ISO_19005_2:6.2.11.8-1', verapdf_fails=True)


def test_odd_length_string_denied(renders, tmp_path):
    pdf = make_candidate(renders[0])
    pdf.pages[0].Contents.write(b'BT /F1 12 Tf 72 72 Td <000100> Tj ET')
    assert_denied(pdf, tmp_path / 'c.pdf', 'pikepdf:text-decode')


def test_missing_cid_to_gid_map_denied(renders, tmp_path):
    pdf = make_candidate(renders[0])
    del cidfont(pdf)['/CIDToGIDMap']
    assert_denied(pdf, tmp_path / 'c.pdf', 'ISO_19005_2:6.2.11.3.2-1')


def test_malformed_w_denied(renders, tmp_path):
    pdf = make_candidate(renders[0])
    cidfont(pdf).W = Array([0, Name.Foo])
    assert_denied(pdf, tmp_path / 'c.pdf', 'pikepdf:font-widths')


@pytest.mark.parametrize(
    'mutate, rule',
    [
        (lambda f: f.__delitem__('/Type'), 'ISO_19005_2:6.2.11.2-1'),
        (lambda f: f.__setitem__('/Subtype', Name.Type9), 'ISO_19005_2:6.2.11.2-2'),
        (lambda f: f.__delitem__('/BaseFont'), 'ISO_19005_2:6.2.11.2-3'),
        (
            lambda f: f.__setitem__('/BaseFont', NON_UTF8_NAME),
            'ISO_19005_2:6.1.8-1',
        ),
    ],
)
def test_font_dictionary_denied(renders, tmp_path, mutate, rule):
    pdf = make_candidate(renders[0])
    mutate(fpdf2_font(pdf))
    assert_denied(pdf, tmp_path / 'c.pdf', rule)


def test_cidset_required_on_subset_in_1b(renders, tmp_path):
    pdf = make_candidate(renders[0], '1')
    del cidfont(pdf).FontDescriptor['/CIDSet']
    assert_denied(
        pdf, tmp_path / 'c.pdf', 'ISO_19005_1:6.3.5-3', '1', verapdf_fails=True
    )


def test_cidset_must_list_used_cids_in_1b(renders, tmp_path):
    pdf = make_candidate(renders[0], '1')
    cidfont(pdf).FontDescriptor.CIDSet.write(b'\x80')
    assert_denied(
        pdf, tmp_path / 'c.pdf', 'ISO_19005_1:6.3.5-3', '1', verapdf_fails=True
    )


def test_cidset_on_truetype_cidfont_unsupported_in_2b(renders, tmp_path):
    pdf = make_candidate(renders[0], '2')
    add_cidsets(pdf)
    assert_denied(
        pdf, tmp_path / 'c.pdf', 'ISO_19005_2:6.2.11.4.2-2', kind='unsupported'
    )


@pytest.mark.parametrize(
    'encoding, rule, kind',
    [
        ('/Identity-V', 'pikepdf:font-vertical', 'unsupported'),
        ('/UniJIS-UCS2-H', 'pikepdf:font-cmap', 'unsupported'),
        ('/Foo-H', 'ISO_19005_2:6.2.11.3.3-1', 'violation'),
    ],
)
def test_type0_named_cmaps(renders, tmp_path, encoding, rule, kind):
    pdf = make_candidate(renders[0])
    fpdf2_font(pdf).Encoding = Name(encoding)
    assert_denied(pdf, tmp_path / 'c.pdf', rule, kind=kind)


def test_type0_predefined_cmap_denied_in_1b(renders, tmp_path):
    pdf = make_candidate(renders[0], '1')
    fpdf2_font(pdf).Encoding = Name('/UniJIS-UCS2-H')
    assert_denied(pdf, tmp_path / 'c.pdf', 'ISO_19005_1:6.3.3.3-1', '1')


def test_type3_unsupported(tmp_path):
    with make_image_only_pdf() as pdf:
        proc = pdf.make_stream(b'750 0 0 0 750 750 d1 0 0 750 750 re f')
        pdf.pages[0].Resources.Font = Dictionary(
            T3=Dictionary(
                Type=Name.Font,
                Subtype=Name.Type3,
                FontBBox=[0, 0, 750, 750],
                FontMatrix=[0.001, 0, 0, 0.001, 0, 0],
                CharProcs=Dictionary(a=proc),
                Encoding=Dictionary(Type=Name.Encoding, Differences=[97, Name.a]),
                FirstChar=97,
                LastChar=97,
                Widths=[750],
                Resources=Dictionary(),
            )
        )
        pdf.pages[0].Contents = pdf.make_stream(b'BT /T3 12 Tf 72 72 Td (a) Tj ET')
        report = check(pdf, tmp_path / 'c.pdf')
    assert 'pikepdf:font-type3' in rule_ids(report)


# --- embedded CMaps over the fpdf2 font -----------------------------------------

IDENTITY_CMAP = b"""/CIDInit /ProcSet findresource begin
12 dict begin
begincmap
/CIDSystemInfo << /Registry (Adobe) /Ordering (UCS) /Supplement 0 >> def
/CMapName /Test-Identity-H def
/CMapType 1 def
%(wmode)s
1 begincodespacerange <0000> <FFFF> endcodespacerange
1 begincidrange <0000> <FFFF> 0 endcidrange
%(extra)s
endcmap
CMapName currentdict /CMap defineresource pop
end
end
"""


def embed_cmap(
    pdf: pikepdf.Pdf, *, wmode: bytes = b'', extra: bytes = b'', **keys
) -> pikepdf.Stream:
    data = IDENTITY_CMAP.replace(b'%(wmode)s', wmode).replace(b'%(extra)s', extra)
    stream = pdf.make_stream(
        data,
        Type=Name.CMap,
        CMapName=Name('/Test-Identity-H'),
        CIDSystemInfo=Dictionary(Registry='Adobe', Ordering='UCS', Supplement=0),
    )
    for key, value in keys.items():
        stream[f'/{key}'] = value
    fpdf2_font(pdf).Encoding = stream
    return stream


def test_embedded_cmap_approved(renders, tmp_path):
    pdf = make_candidate(renders[0])
    embed_cmap(pdf)
    assert_approved(pdf, tmp_path / 'c.pdf')


def test_embedded_cmap_wmode_mismatch(renders, tmp_path):
    pdf = make_candidate(renders[0])
    embed_cmap(pdf, WMode=1)
    assert_denied(
        pdf, tmp_path / 'c.pdf', 'ISO_19005_2:6.2.11.3.3-2', verapdf_fails=True
    )


def test_embedded_cmap_supplement_mismatch(renders, tmp_path):
    pdf = make_candidate(renders[0])
    embed_cmap(pdf)
    cidfont(pdf).CIDSystemInfo.Supplement = 1
    assert_denied(
        pdf, tmp_path / 'c.pdf', 'ISO_19005_2:6.2.11.3.1-1', verapdf_fails=True
    )
    # PDF/A-1 compares only Registry and Ordering
    pdf1 = make_candidate(renders[0], '1')
    embed_cmap(pdf1)
    cidfont(pdf1).CIDSystemInfo.Supplement = 1
    report = check(pdf1, tmp_path / 'c1.pdf', '1')
    assert report.passed, report.summary()


def test_embedded_cmap_ordering_mismatch(renders, tmp_path):
    pdf = make_candidate(renders[0])
    embed_cmap(pdf)
    cidfont(pdf).CIDSystemInfo.Ordering = pikepdf.String('Japan1')
    assert_denied(
        pdf, tmp_path / 'c.pdf', 'ISO_19005_2:6.2.11.3.1-1', verapdf_fails=True
    )


def test_embedded_cmap_usecmap(renders, tmp_path):
    pdf = make_candidate(renders[0])
    other = pdf.make_stream(b'', Type=Name.CMap)
    embed_cmap(pdf, UseCMap=other)
    assert_denied(pdf, tmp_path / 'c.pdf', 'ISO_19005_2:6.2.11.3.3-3')
    embed_cmap(pdf, extra=b'/Identity-H usecmap')
    assert_denied(
        pdf, tmp_path / 'c2.pdf', 'ISO_19005_2:6.2.11.3.3-3', kind='unsupported'
    )


def test_embedded_cmap_cid_limit(renders, tmp_path):
    pdf = make_candidate(renders[0])
    embed_cmap(pdf, extra=b'1 begincidchar <FFFF> 70000 endcidchar')
    assert_denied(pdf, tmp_path / 'c.pdf', 'ISO_19005_2:6.1.13-10')


def test_embedded_cmap_unmapped_code_is_notdef(renders, tmp_path):
    pdf = make_candidate(renders[0])
    stream = embed_cmap(pdf)
    stream.write(
        stream.read_bytes().replace(
            b'1 begincidrange <0000> <FFFF> 0 endcidrange',
            b'1 begincidrange <0000> <0005> 0 endcidrange',
        )
    )
    assert_denied(pdf, tmp_path / 'c.pdf', 'ISO_19005_2:6.2.11.8-1')


# --- simple TrueType -------------------------------------------------------------


def test_simple_truetype_widths_length(tmp_path):
    pdf = make_simple_truetype_pdf()
    pdf.pages[0].Resources.Font.F1.LastChar = 127
    assert_denied(pdf, tmp_path / 'c.pdf', 'ISO_19005_2:6.2.11.2-6', verapdf_fails=True)


def test_simple_truetype_width_mismatch(tmp_path):
    pdf = make_simple_truetype_pdf()
    widths = pdf.pages[0].Resources.Font.F1.Widths
    widths[ord('H') - 32] = widths[ord('H') - 32] + 5
    assert_denied(pdf, tmp_path / 'c.pdf', 'ISO_19005_2:6.2.11.5-1', verapdf_fails=True)


def test_simple_truetype_missing_encoding(tmp_path):
    pdf = make_simple_truetype_pdf()
    del pdf.pages[0].Resources.Font.F1['/Encoding']
    assert_denied(pdf, tmp_path / 'c.pdf', 'ISO_19005_2:6.2.11.6-2', verapdf_fails=True)


def test_simple_truetype_agl_differences(tmp_path):
    def with_differences(part: str, name: str) -> pikepdf.Pdf:
        pdf = make_simple_truetype_pdf(part)
        pdf.pages[0].Resources.Font.F1.Encoding = Dictionary(
            Type=Name.Encoding,
            BaseEncoding=Name.WinAnsiEncoding,
            Differences=[ord('H'), Name('/' + name)],
        )
        return pdf

    assert_approved(with_differences('2', 'H'), tmp_path / 'agl2.pdf')
    assert_denied(
        with_differences('1', 'H'), tmp_path / 'agl1.pdf', 'ISO_19005_1:6.3.7-1', '1'
    )
    assert_denied(
        with_differences('2', 'Hfoo'), tmp_path / 'foo.pdf', 'ISO_19005_2:6.2.11.6-2'
    )


def test_simple_truetype_glyph_missing(tmp_path):
    pdf = make_simple_truetype_pdf(text=b'Hex')
    assert_denied(pdf, tmp_path / 'c.pdf', 'ISO_19005_2:6.2.11.8-1')


@pytest.mark.parametrize('flags', [4 | 32, 0])
def test_simple_truetype_symbolic_flags(tmp_path, flags):
    pdf = make_simple_truetype_pdf()
    pdf.pages[0].Resources.Font.F1.FontDescriptor.Flags = flags
    assert_denied(pdf, tmp_path / 'c.pdf', 'pikepdf:font-flags', kind='unsupported')


# --- rendering mode and font state flow into forms ----------------------------------


@pytest.mark.parametrize('mode, passes', [(0, False), (3, True)])
def test_form_inherits_font_and_mode(renders, tmp_path, mode, passes):
    pdf = make_candidate(renders[0])
    _bump_width(pdf, 2)
    page = pdf.pages[0]
    form = pdf.make_stream(
        b'BT 72 72 Td <00010002> Tj ET',
        Type=Name.XObject,
        Subtype=Name.Form,
        BBox=[0, 0, 612, 792],
        Resources=page.Resources,
    )
    page.Resources.XObject = Dictionary(Fm0=form)
    page.Contents.write(f'/F1 12 Tf {mode} Tr /Fm0 Do'.encode())
    report = check(pdf, tmp_path / 'c.pdf')
    assert report.passed is passes, report.summary()
    if passes:
        assert_verapdf_agrees(tmp_path / 'c.pdf', '2b')
    else:
        assert 'ISO_19005_2:6.2.11.5-1' in rule_ids(report)


# --- experiments against veraPDF ------------------------------------------------------


def require_verapdf() -> None:
    if verapdf_command() is None:
        pytest.skip("veraPDF not installed")


def test_experiment_empty_glyph_is_present(renders, tmp_path):
    """A glyph without an outline (space) is present for veraPDF."""
    require_verapdf()
    path = save_candidate(make_candidate(renders[0]), tmp_path / 'c.pdf', '2')
    with pikepdf.open(path) as pdf:
        assert b'\x00 ' in pdf.pages[0].Contents.read_bytes()  # CID 32, space
    assert verapdf_failed_rules(path, '2b') == set()
    assert validate(path, '2b').passed


@pytest.mark.parametrize('mode, verapdf_fails', [(0, True), (3, False)])
def test_experiment_type3_widths(tmp_path, mode, verapdf_fails):
    """Type 3 /Widths are checked by veraPDF against d0/d1 (except in Tr 3).

    The validator does not support Type 3 fonts at all yet.
    """
    require_verapdf()
    with make_image_only_pdf() as pdf:
        proc = pdf.make_stream(b'750 0 0 0 750 750 d1 0 0 750 750 re f')
        pdf.pages[0].Resources.Font = Dictionary(
            T3=Dictionary(
                Type=Name.Font,
                Subtype=Name.Type3,
                FontBBox=[0, 0, 750, 750],
                FontMatrix=[0.001, 0, 0, 0.001, 0, 0],
                CharProcs=Dictionary(a=proc),
                Encoding=Dictionary(Type=Name.Encoding, Differences=[97, Name.a]),
                FirstChar=97,
                LastChar=97,
                Widths=[500],
                Resources=Dictionary(),
            )
        )
        pdf.pages[0].Contents = pdf.make_stream(
            f'BT {mode} Tr /T3 12 Tf 72 72 Td (a) Tj ET'.encode()
        )
        path = save_candidate(pdf, tmp_path / 'c.pdf', '2')
    failed = verapdf_failed_rules(path, '2b')
    assert ('ISO_19005_2:6.2.11.5-1' in failed) is verapdf_fails, failed
    assert 'pikepdf:font-type3' in rule_ids(validate(path, '2b'))


# --- OCRmyPDF pipeline output ---------------------------------------------------------


@pytest.mark.parametrize('renderer', ['fpdf2', 'sandwich'])
def test_pipeline_latin_output_validates(tmp_path, renderer):
    """Text layers from both renderers validate once the candidate is repaired.

    The input's XMP carries PDF/X properties that PDF/A does not allow; the
    pipeline's repair step removes them, simulated here by dropping the packet.
    The files are OCRmyPDF's output for francais.pdf (``--force-ocr -l eng
    --output-type pdf --pdf-renderer <renderer>``).
    """
    out = RESOURCES / f'francais_ocr_{renderer}.pdf'
    for part in ('1', '2'):
        with pikepdf.open(out) as pdf:
            del pdf.Root['/Metadata']
            assert_approved(make_candidate(pdf, part), tmp_path / f'{part}.pdf', part)
