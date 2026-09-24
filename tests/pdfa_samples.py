# SPDX-FileCopyrightText: 2026 James R. Barlow
# SPDX-License-Identifier: MPL-2.0

"""Sample PDFs for the PDF/A validator tests, built in memory with pikepdf."""

from __future__ import annotations

import zlib
from collections.abc import Callable
from io import BytesIO
from pathlib import Path

from conftest import verapdf_failed_rules as _verapdf_failed_rules
from fontTools.cffLib import CFFFontSet
from fontTools.ttLib import TTFont

import pikepdf
from pikepdf import Dictionary, Name
from pikepdf.pdfa._declare import add_pdfa_metadata
from pikepdf.pdfa._output_intent import add_srgb_output_intent


def make_image_only_pdf(part: str = '2') -> pikepdf.Pdf:
    """Return a one-page, image-only PDF/A candidate (DeviceGray Flate image).

    The file is saved and reopened, so that it has what qpdf adds when
    writing, such as the trailer /ID.
    """
    buffer = BytesIO()
    with _build_image_only_pdf(part) as pdf:
        pdf.save(buffer, **_save_kwargs(part != '1'))
    buffer.seek(0)
    return pikepdf.open(buffer)


def _save_kwargs(object_streams: bool) -> dict:
    return dict(
        object_stream_mode=(
            pikepdf.ObjectStreamMode.generate
            if object_streams
            else pikepdf.ObjectStreamMode.disable
        )
    )


def _build_image_only_pdf(part: str) -> pikepdf.Pdf:
    pdf = pikepdf.new()
    image = pdf.make_stream(
        zlib.compress(bytes(range(64))),
        Type=Name.XObject,
        Subtype=Name.Image,
        Width=8,
        Height=8,
        ColorSpace=Name.DeviceGray,
        BitsPerComponent=8,
        Filter=Name.FlateDecode,
    )
    content = pdf.make_stream(b'q 612 0 0 792 0 0 cm /Im0 Do Q')
    page = Dictionary(
        Type=Name.Page,
        MediaBox=[0, 0, 612, 792],
        Resources=Dictionary(XObject=Dictionary(Im0=image)),
        Contents=content,
    )
    pdf.pages.append(pikepdf.Page(page))
    add_srgb_output_intent(pdf)
    add_pdfa_metadata(pdf, part, 'B')
    return pdf


def save_image_only_pdf(
    path: Path,
    part: str = '2',
    mutate: Callable[[pikepdf.Pdf], None] | None = None,
    *,
    object_streams: bool | None = None,
    **save_kwargs,
) -> Path:
    """Build the image-only sample, optionally mutate it, and save it.

    By default PDF/A-1 candidates are saved without object streams (so there
    is no cross-reference stream either) and others with them, matching
    OCRmyPDF's ``get_pdf_save_settings``.
    """
    if object_streams is None:
        object_streams = part != '1'
    with make_image_only_pdf(part) as pdf:
        if mutate is not None:
            mutate(pdf)
        pdf.save(path, **_save_kwargs(object_streams), **save_kwargs)
    return path


def replace_xmp(pdf: pikepdf.Pdf, old: bytes, new: bytes) -> None:
    """Replace bytes in the raw XMP packet, asserting the old bytes exist."""
    raw = pdf.Root.Metadata.read_bytes()
    assert old in raw, raw
    pdf.Root.Metadata.write(raw.replace(old, new, 1))


def save_candidate(pdf: pikepdf.Pdf, path: Path, part: str) -> Path:
    """Save a PDF/A candidate the way the pipeline does for *part*."""
    if part == '1':
        pdf.save(path, force_version='1.4', **_save_kwargs(False))
    else:
        pdf.save(path, **_save_kwargs(True))
    return path


def make_candidate(source: Path | pikepdf.Pdf, part: str = '2') -> pikepdf.Pdf:
    """Turn a PDF into a PDF/A candidate in memory.

    Replaces the OutputIntents with the sRGB PDF/A intent, adds PDF/A XMP
    metadata, drops /OpenAction (which fpdf2 writes and the pipeline never
    copies) and, for PDF/A-1, removes page transparency groups and adds the
    /CIDSet that PDF/A-1 requires on subset CIDFonts.
    """
    pdf = source if isinstance(source, pikepdf.Pdf) else pikepdf.open(source)
    if '/OpenAction' in pdf.Root:
        del pdf.Root['/OpenAction']
    if '/OutputIntents' in pdf.Root:
        del pdf.Root['/OutputIntents']
    add_srgb_output_intent(pdf)
    add_pdfa_metadata(pdf, part, 'B')
    if part == '1':
        for page in pdf.pages:
            if '/Group' in page.obj:
                del page.obj['/Group']
        add_cidsets(pdf)
    return pdf


def _cidset_bytes(cids: set[int]) -> bytes:
    data = bytearray(max(cids) // 8 + 1 if cids else 1)
    for cid in cids:
        data[cid // 8] |= 0x80 >> (cid % 8)
    return bytes(data)


def _program_cids(cidfont: pikepdf.Dictionary) -> set[int] | None:
    descriptor = cidfont.FontDescriptor
    if '/FontFile2' in descriptor:
        font = TTFont(BytesIO(descriptor.FontFile2.read_bytes()), lazy=True)
        num_glyphs = font['maxp'].numGlyphs
        cid_to_gid = cidfont.get('/CIDToGIDMap')
        if not isinstance(cid_to_gid, pikepdf.Stream):
            return set(range(num_glyphs))
        data = cid_to_gid.read_bytes()
        return {
            i // 2
            for i in range(0, len(data) - 1, 2)
            if 0 < int.from_bytes(data[i : i + 2], 'big') < num_glyphs
        } | {0}
    if '/FontFile3' in descriptor:
        cff = CFFFontSet()
        cff.decompile(BytesIO(descriptor.FontFile3.read_bytes()), otFont=None)
        charset = cff[cff.fontNames[0]].charset
        return {0} | {int(name[3:]) for name in charset[1:]}
    return None


def add_cidsets(pdf: pikepdf.Pdf) -> None:
    """Add a /CIDSet to every subset CIDFont lacking one (as PDF/A-1 needs)."""
    for obj in pdf.objects:
        if not isinstance(obj, pikepdf.Dictionary) or obj.get('/Subtype') not in (
            Name.CIDFontType0,
            Name.CIDFontType2,
        ):
            continue
        descriptor = obj.get('/FontDescriptor')
        if descriptor is None or '/CIDSet' in descriptor:
            continue
        if '+' not in str(obj.BaseFont)[:8]:
            continue
        cids = _program_cids(obj)
        if cids is not None:
            descriptor.CIDSet = pdf.make_stream(_cidset_bytes(cids))


def verapdf_failed_rules(path: Path, flavour: str) -> set[str] | None:
    """Return the ids of the veraPDF rules *path* fails, or None without veraPDF.

    Ids use the catalogue's form, e.g. ``ISO_19005_2:6.2.2-2``.
    """
    return _verapdf_failed_rules(path, flavour)


def assert_verapdf_agrees(path: Path, flavour: str) -> None:
    """If veraPDF is installed, assert it also finds *path* compliant."""
    failed = verapdf_failed_rules(path, flavour)
    if failed is not None:
        assert failed == set(), f"veraPDF {flavour} fails {sorted(failed)}"


RESOURCES = Path(__file__).parent / 'resources' / 'pdfa'

NOTO_SANS = RESOURCES / 'NotoSans-Regular.ttf'


def make_simple_truetype_pdf(
    part: str = '2',
    text: bytes = b'Hello',
    *,
    subset_text: str = 'Helo',
) -> pikepdf.Pdf:
    """Return a candidate showing *text* in a non-symbolic simple TrueType font.

    The font is a subset of NotoSans with a (3,1) cmap, WinAnsiEncoding,
    and /Widths taken from the program's hmtx.
    """
    from fontTools import subset

    options = subset.Options()
    options.notdef_outline = True
    options.name_IDs = []
    options.layout_features = []
    font = TTFont(NOTO_SANS)
    subsetter = subset.Subsetter(options)
    subsetter.populate(text=subset_text)
    subsetter.subset(font)
    buffer = BytesIO()
    font.save(buffer)
    data = buffer.getvalue()
    font = TTFont(BytesIO(data))
    cmap = font.getBestCmap()
    units = font['head'].unitsPerEm
    first, last = 32, 126
    widths = []
    for code in range(first, last + 1):
        glyph = cmap.get(code)
        width = font['hmtx'][glyph][0] * 1000 / units if glyph else 0
        widths.append(round(width))

    pdf = pikepdf.new()
    descriptor = Dictionary(
        Type=Name.FontDescriptor,
        FontName=Name('/ABCDEF+NotoSans'),
        Flags=32,
        FontBBox=[-621, -394, 2800, 1347],
        ItalicAngle=0,
        Ascent=1069,
        Descent=-293,
        CapHeight=714,
        StemV=87,
        FontFile2=pdf.make_stream(data, Length1=len(data)),
    )
    font_dict = pdf.make_indirect(
        Dictionary(
            Type=Name.Font,
            Subtype=Name.TrueType,
            BaseFont=Name('/ABCDEF+NotoSans'),
            FirstChar=first,
            LastChar=last,
            Widths=pdf.make_indirect(pikepdf.Array(widths)),
            Encoding=Name.WinAnsiEncoding,
            FontDescriptor=pdf.make_indirect(descriptor),
        )
    )
    content = pdf.make_stream(b'BT /F1 24 Tf 72 700 Td (' + text + b') Tj ET')
    page = Dictionary(
        Type=Name.Page,
        MediaBox=[0, 0, 612, 792],
        Resources=Dictionary(Font=Dictionary(F1=font_dict)),
        Contents=content,
    )
    pdf.pages.append(pikepdf.Page(page))
    return make_candidate(pdf, part)


TYPE1_FONT_FILES = (
    Path('/usr/share/fonts/type1/urw-base35/NimbusSans-Regular.t1'),
    Path('/usr/share/fonts/type1/gsfonts/n019003l.pfb'),
    Path('/usr/share/fonts/X11/Type1/NimbusSans-Regular.pfb'),
)


def find_type1_font() -> Path | None:
    """Return a Type 1 font file (PFA or PFB) installed on this system, or None.

    Looks in the usual Linux font directories and in Ghostscript's font
    search path, which holds the URW base 35 fonts as PFA files.
    """
    import shutil
    import subprocess

    candidates = list(TYPE1_FONT_FILES)
    gs = shutil.which('gs')
    if gs is not None:
        try:
            proc = subprocess.run(
                [gs, '-h'], capture_output=True, text=True, check=False, timeout=30
            )
            search = proc.stdout.split('Search path:', 1)[-1]
        except (OSError, subprocess.SubprocessError):
            search = ''
        for token in search.replace(':', ' ').split():
            if 'Font' in token or 'font' in token:
                directory = Path(token)
                candidates.append(directory / 'NimbusSans-Regular')
                candidates.append(directory / 'n019003l.pfb')
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def make_type1_pdf(
    font_path: Path,
    part: str = '2',
    text: bytes = b'Hello',
    *,
    subset: bool = True,
) -> pikepdf.Pdf:
    """Return a candidate showing *text* in an embedded Type 1 font (/FontFile).

    The program is stored in the PDF layout: cleartext (/Length1), binary
    eexec section (/Length2) and trailer (/Length3). The font uses
    WinAnsiEncoding with /Widths from the program. If *subset*, the BaseFont
    gets a subset prefix and the descriptor a /CharSet listing every glyph of
    the (complete) program.
    """
    from fontTools import t1Lib
    from fontTools.pens.basePen import NullPen

    from pikepdf.pdfa._encodings import WIN_ANSI, encoding_table

    data, _kind = t1Lib.read(str(font_path))
    chunks = [chunk for _encrypted, chunk in t1Lib.findEncryptedChunks(data)]
    assert len(chunks) == 3, [len(c) for c in chunks]
    font = t1Lib.T1Font(str(font_path))
    charstrings = font['CharStrings']
    first, last = 32, 126
    names = encoding_table(WIN_ANSI)
    widths = []
    for code in range(first, last + 1):
        name = names.get(code)
        if name in charstrings:
            glyph = charstrings[name]
            glyph.draw(NullPen())
            widths.append(round(glyph.width))
        else:
            widths.append(0)
    font_name = font['FontName']
    if subset:
        font_name = 'ABCDEF+' + font_name
    bbox = [round(v) for v in font['FontBBox']]

    pdf = pikepdf.new()
    font_file = pdf.make_stream(
        b''.join(chunks),
        Length1=len(chunks[0]),
        Length2=len(chunks[1]),
        Length3=len(chunks[2]),
    )
    descriptor = Dictionary(
        Type=Name.FontDescriptor,
        FontName=Name('/' + font_name),
        Flags=32,
        FontBBox=bbox,
        ItalicAngle=0,
        Ascent=bbox[3],
        Descent=bbox[1],
        CapHeight=700,
        StemV=80,
        FontFile=font_file,
    )
    if subset:
        descriptor.CharSet = pikepdf.String(
            ''.join(
                '/' + name for name in sorted(charstrings.keys()) if name != '.notdef'
            )
        )
    font_dict = pdf.make_indirect(
        Dictionary(
            Type=Name.Font,
            Subtype=Name.Type1,
            BaseFont=Name('/' + font_name),
            FirstChar=first,
            LastChar=last,
            Widths=pdf.make_indirect(pikepdf.Array(widths)),
            Encoding=Name.WinAnsiEncoding,
            FontDescriptor=pdf.make_indirect(descriptor),
        )
    )
    content = pdf.make_stream(b'BT /F1 24 Tf 72 700 Td (' + text + b') Tj ET')
    page = Dictionary(
        Type=Name.Page,
        MediaBox=[0, 0, 612, 792],
        Resources=Dictionary(Font=Dictionary(F1=font_dict)),
        Contents=content,
    )
    pdf.pages.append(pikepdf.Page(page))
    return make_candidate(pdf, part)


def make_clean_candidate(
    source: Path | pikepdf.Pdf,
    part: str = '2',
    *,
    strip_keys: tuple[str, ...] = (),
) -> pikepdf.Pdf:
    """Like `make_candidate`, but start from fresh XMP metadata.

    The input's XMP often carries properties PDF/A does not permit, which
    the pipeline strips before validating. *strip_keys* are further keys to
    delete from the trailer, the catalog and every page (producer-private
    keys such as ``/PDFpenVersion``).
    """
    pdf = source if isinstance(source, pikepdf.Pdf) else pikepdf.open(source)
    if '/Metadata' in pdf.Root:
        del pdf.Root['/Metadata']
    for key in strip_keys:
        for obj in (pdf.trailer, pdf.Root, *(page.obj for page in pdf.pages)):
            if key in obj:
                del obj[key]
    return make_candidate(pdf, part)


def assert_verapdf_fails(path: Path, flavour: str, rule: str) -> None:
    """If veraPDF is installed, assert it reports *rule* for *path*."""
    failed = verapdf_failed_rules(path, flavour)
    if failed is not None:
        assert rule in failed, f"veraPDF {flavour} fails {sorted(failed)}, not {rule}"
