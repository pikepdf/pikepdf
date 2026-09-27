# SPDX-FileCopyrightText: 2026 James R. Barlow
# SPDX-License-Identifier: MPL-2.0

"""Tests of the repairs applied by the speculative PDF/A conversion."""

from __future__ import annotations

import pytest

pytest.importorskip('jsonschema')

import datetime as dt
import logging
from decimal import Decimal
from io import BytesIO
from pathlib import Path

from conftest import verapdf_failed_rules
from fontTools.ttLib import TTFont
from pdfa_samples import (
    NOTO_SANS,
    RESOURCES,
    assert_verapdf_agrees,
    make_simple_truetype_pdf,
    replace_xmp,
    save_candidate,
)

import pikepdf
from pikepdf import Name
from pikepdf.models.metadata import decode_pdf_date
from pikepdf.pdfa import prepare, save, validate_written
from pikepdf.pdfa._declare import (
    add_pdfa_metadata,
    assume_local_time_zone_for_dates,
    canonicalize_xmp,
)
from pikepdf.pdfa._output_intent import (
    add_srgb_output_intent,
    has_output_intent,
    parse_output_intent,
    replace_output_intents,
)
from pikepdf.pdfa._repair import (
    add_cidsets_for_subset_cidfonts,
    add_truetype_base_encodings,
    repair_annotation_flags,
    strip_image_interpolation,
)

PHOTOSHOP = 'http://ns.adobe.com/photoshop/1.0/'
XMPMM = 'http://ns.adobe.com/xap/1.0/mm/'
PDFX = 'http://ns.adobe.com/pdfx/1.3/'
PDFXID = 'http://www.npes.org/pdfx/ns/id/'
XMP = 'http://ns.adobe.com/xap/1.0/'


@pytest.fixture(params=['fpdf2', 'sandwich'])
def francais_ocr(request) -> Path:
    """francais.pdf after real OCR with --force-ocr, as a regular PDF.

    The input is a PDF/X file with Photoshop XMP, so the output carries a
    PDF/X output intent and XMP properties that PDF/A does not permit.
    Generated once with OCRmyPDF (Tesseract, --pdf-renderer fpdf2 or
    sandwich, --output-type pdf) and checked in.
    """
    return RESOURCES / f'francais_ocr_{request.param}.pdf'


def _save_pdfa(source: Path, out: Path, flavour: str) -> Path:
    with pikepdf.open(source) as pdf:
        save(pdf, out, flavour)
    return out


def _xmp_keys(pdf: pikepdf.Pdf) -> set[str]:
    meta = pdf.open_metadata(set_pikepdf_as_editor=False, update_docinfo=False)
    return set(meta)


def test_replace_output_intents(francais_ocr):
    with pikepdf.open(francais_ocr) as pdf:
        subtypes = {str(i.S) for i in pdf.Root.OutputIntents}
        assert '/GTS_PDFX' in subtypes
        replace_output_intents(pdf)
        intents = pdf.Root.OutputIntents
        assert len(intents) == 1
        assert intents[0].S == Name.GTS_PDFA1
        assert str(intents[0].OutputConditionIdentifier) == 'sRGB'
        assert intents[0].DestOutputProfile.N == 3


@pytest.mark.parametrize('n', [Decimal('3.0'), True])
def test_has_output_intent_requires_integer_n(francais_ocr, n):
    spec = parse_output_intent('sRGB', '2b')
    with pikepdf.open(francais_ocr) as pdf:
        replace_output_intents(pdf, spec)
        assert has_output_intent(pdf, spec)
        pdf.Root.OutputIntents[0].DestOutputProfile.N = n
        assert not has_output_intent(pdf, spec)


def test_add_srgb_output_intent_replaces_existing(francais_ocr):
    with pikepdf.open(francais_ocr) as pdf:
        add_srgb_output_intent(pdf)
        add_srgb_output_intent(pdf)
        assert len(pdf.Root.OutputIntents) == 1
        assert pdf.Root.OutputIntents[0].S == Name.GTS_PDFA1


def test_strip_image_interpolation(francais_ocr):
    with pikepdf.open(francais_ocr) as pdf:
        images = [
            obj
            for obj in pdf.objects
            if isinstance(obj, pikepdf.Stream) and obj.get('/Subtype') == Name.Image
        ]
        assert images
        for image in images:
            image.Interpolate = True
        assert strip_image_interpolation(pdf) == len(images)
        assert all('/Interpolate' not in image for image in images)
        assert strip_image_interpolation(pdf) == 0


def _fpdf2_cidfont(pdf: pikepdf.Pdf) -> pikepdf.Dictionary:
    for obj in pdf.objects:
        if (
            isinstance(obj, pikepdf.Dictionary)
            and obj.get('/Subtype') == Name.CIDFontType2
            and '+' in str(obj.BaseFont)
        ):
            return obj
    pytest.skip("no subset CIDFontType2 in this rendering")


def _cidset_bits(data: bytes) -> set[int]:
    return {
        i * 8 + bit
        for i, byte in enumerate(data)
        for bit in range(8)
        if byte & (0x80 >> bit)
    }


def test_add_cidsets_matches_cidtogidmap(francais_ocr):
    with pikepdf.open(francais_ocr) as pdf:
        cidfont = _fpdf2_cidfont(pdf)
        assert '/CIDSet' not in cidfont.FontDescriptor
        assert add_cidsets_for_subset_cidfonts(pdf) == 1
        bits = _cidset_bits(cidfont.FontDescriptor.CIDSet.read_bytes())

        font = TTFont(BytesIO(cidfont.FontDescriptor.FontFile2.read_bytes()))
        num_glyphs = font['maxp'].numGlyphs
        data = cidfont.CIDToGIDMap.read_bytes()
        expected = {
            i // 2
            for i in range(0, len(data), 2)
            if 0 < int.from_bytes(data[i : i + 2], 'big') < num_glyphs
        }
        assert bits == expected | {0}
        # An existing CIDSet is left alone
        assert add_cidsets_for_subset_cidfonts(pdf) == 0


def test_add_cidsets_identity_map():
    with pikepdf.new() as pdf:
        data = NOTO_SANS
        num_glyphs = TTFont(data)['maxp'].numGlyphs
        descriptor = pikepdf.Dictionary(
            Type=Name.FontDescriptor,
            FontFile2=pdf.make_stream(data.read_bytes()),
        )
        pdf.make_indirect(
            pikepdf.Dictionary(
                Type=Name.Font,
                Subtype=Name.CIDFontType2,
                BaseFont=Name('/ABCDEF+NotoSans'),
                CIDToGIDMap=Name.Identity,
                FontDescriptor=descriptor,
            )
        )
        assert add_cidsets_for_subset_cidfonts(pdf) == 1
        bits = _cidset_bits(descriptor.CIDSet.read_bytes())
        assert bits == set(range(num_glyphs))


@pytest.mark.parametrize('flavour', ['1b', '2b'])
def test_cidset_only_for_pdfa1(francais_ocr, tmp_path, flavour):
    out = _save_pdfa(francais_ocr, tmp_path / 'out.pdf', flavour)
    with pikepdf.open(out) as pdf:
        cidfont = _fpdf2_cidfont(pdf)
        assert ('/CIDSet' in cidfont.FontDescriptor) == (flavour == '1b')


def test_strip_xmp_pdfa1(francais_ocr, caplog):
    with pikepdf.open(francais_ocr) as pdf:
        keys = _xmp_keys(pdf)
        assert f'{{{PHOTOSHOP}}}ColorMode' in keys
        assert f'{{{XMPMM}}}History' in keys
        assert f'{{{PDFX}}}GTS_PDFXVersion' in keys
        with caplog.at_level(logging.DEBUG, logger='pikepdf.pdfa'):
            dropped = canonicalize_xmp(pdf, '1b')
        assert dropped
        assert "not permitted in PDF/A" in caplog.text
        keys = _xmp_keys(pdf)
        assert not {k for k in keys if k.startswith(f'{{{PHOTOSHOP}}}')}
        assert f'{{{XMPMM}}}History' not in keys
        assert not {k for k in keys if k.startswith((f'{{{PDFX}}}', f'{{{PDFXID}}}'))}
        assert f'{{{XMP}}}CreatorTool' in keys
        raw = pdf.Root.Metadata.read_bytes()
        for uri in (PHOTOSHOP, PDFX, PDFXID, 'http://ns.adobe.com/xap/1.0/g/img/'):
            assert uri.encode() not in raw


def _add_headline(pdf: pikepdf.Pdf) -> None:
    with pdf.open_metadata(set_pikepdf_as_editor=False, update_docinfo=False) as meta:
        meta[f'{{{PHOTOSHOP}}}Headline'] = 'News'


@pytest.mark.parametrize('flavour', ['1b', '2b'])
def test_strip_xmp_photoshop(francais_ocr, flavour):
    """XMP 2005 Photoshop properties are kept for 2b; later ones are not."""
    with pikepdf.open(francais_ocr) as pdf:
        _add_headline(pdf)
        dropped = canonicalize_xmp(pdf, flavour)
        assert 'photoshop:ColorMode' in dropped
        assert 'photoshop:ICCProfile' in dropped
        assert 'xmpMM:History' in dropped
        keys = _xmp_keys(pdf)
        assert (f'{{{PHOTOSHOP}}}Headline' in keys) == (flavour == '2b')
        assert f'{{{PHOTOSHOP}}}ColorMode' not in keys
        assert f'{{{XMPMM}}}History' not in keys
        assert (f'{{{XMPMM}}}InstanceID' in keys) == (flavour == '2b')
        assert not {k for k in keys if k.startswith((f'{{{PDFX}}}', f'{{{PDFXID}}}'))}


def test_strip_xmp_nothing_to_do(francais_ocr, caplog):
    with pikepdf.open(francais_ocr) as pdf:
        canonicalize_xmp(pdf, '2b')
        caplog.clear()
        with caplog.at_level(logging.DEBUG, logger='pikepdf.pdfa'):
            assert canonicalize_xmp(pdf, '2b') == []
        assert "not permitted" not in caplog.text


def test_strip_xmp_nested_foreign_namespace_rebuilds_packet(francais_ocr, tmp_path):
    """A foreign namespace the metadata mapping cannot reach forces a new packet."""
    with pikepdf.open(francais_ocr) as pdf:
        _add_headline(pdf)
        replace_xmp(
            pdf,
            b'<rdf:li xml:lang="x-default">',
            b'<rdf:li xml:lang="x-default" xmlns:foo="http://example.com/foo/"'
            b' foo:qualifier="x">',
        )
        canonicalize_xmp(pdf, '2b')
        raw = pdf.Root.Metadata.read_bytes()
        assert b'http://example.com/foo/' not in raw
        keys = _xmp_keys(pdf)
        assert f'{{{XMP}}}CreatorTool' in keys
        assert f'{{{PHOTOSHOP}}}Headline' in keys
        assert str(pdf.open_metadata()['dc:title']) == 'Adobe Photoshop PDF'
        add_pdfa_metadata(pdf, '2', 'B')
        replace_output_intents(pdf)
        pdf.save(tmp_path / 'out.pdf')
    report = validate_written(tmp_path / 'out.pdf', '2b')
    assert report.passed, report.summary()
    assert_verapdf_agrees(tmp_path / 'out.pdf', '2b')


def test_pdfa1_candidate_has_no_xref_stream(francais_ocr, tmp_path):
    out = _save_pdfa(francais_ocr, tmp_path / 'out.pdf', '1b')
    assert b'/ObjStm' not in out.read_bytes()
    with pikepdf.open(out) as pdf:
        assert pdf.trailer.get('/Type') != Name.XRef
        assert pdf.pdf_version == '1.4'


@pytest.mark.parametrize('flavour', ['1b', '2b', '3b'])
def test_repaired_candidate_validates(francais_ocr, tmp_path, flavour):
    out = _save_pdfa(francais_ocr, tmp_path / 'out.pdf', flavour)
    report = validate_written(out, flavour)
    assert report.passed, report.summary()
    assert_verapdf_agrees(out, flavour)


def _page_annots(pdf: pikepdf.Pdf) -> list[list[pikepdf.Object]]:
    return [list(page.get('/Annots', [])) for page in pdf.pages]


def test_repair_annotation_flags_sets_print():
    with pikepdf.open(RESOURCES / 'link.pdf') as pdf:
        annots = [annot for page in _page_annots(pdf) for annot in page]
        assert len(annots) == 2
        assert all('/F' not in annot for annot in annots)
        # Print clear, with other bits set: Print is added, the others kept
        annots[1].F = 16 | 128  # NoRotate | Locked
        result = repair_annotation_flags(pdf)
        assert result.print_flags_set == 2
        assert not result.removed
        assert annots[0].F == 4
        assert annots[1].F == 16 | 128 | 4
        # Idempotent
        assert repair_annotation_flags(pdf).print_flags_set == 0


@pytest.mark.parametrize(
    'flag',
    [
        pytest.param(1, id='invisible'),
        pytest.param(2, id='hidden'),
        pytest.param(32, id='noview'),
        pytest.param(256, id='togglenoview'),
    ],
)
def test_repair_annotation_flags_removes_not_viewable(flag):
    with pikepdf.open(RESOURCES / 'link.pdf') as pdf:
        pdf.pages[0].Annots[0].F = flag | 4
        result = repair_annotation_flags(pdf)
        assert dict(result.removed) == {'Link': 1}
        assert result.removed_pages == {1}
        assert result.print_flags_set == 1  # the Link on page 2
        annots = _page_annots(pdf)
        assert annots[0] == []
        assert annots[1][0].F == 4


def _add_text_with_popup(pdf: pikepdf.Pdf, page: pikepdf.Page, flags: int):
    """Add a Text annotation and its Popup to *page*; return both."""
    text = pdf.make_indirect(
        pikepdf.Dictionary(
            Type=Name.Annot,
            Subtype=Name.Text,
            Rect=[0, 0, 0, 0],
            Contents=pikepdf.String('note'),
            F=flags,
        )
    )
    popup = pdf.make_indirect(
        pikepdf.Dictionary(
            Type=Name.Annot,
            Subtype=Name.Popup,
            Rect=[0, 0, 0, 0],
            Parent=text,
            F=4,
        )
    )
    text.Popup = popup
    page.Annots.append(text)
    page.Annots.append(popup)
    return text, popup


def test_repair_annotation_flags_removes_popup_with_parent():
    with pikepdf.open(RESOURCES / 'link.pdf') as pdf:
        _add_text_with_popup(pdf, pdf.pages[0], flags=2 | 4)
        result = repair_annotation_flags(pdf)
        assert dict(result.removed) == {'Text': 1, 'Popup': 1}
        subtypes = [annot.Subtype for annot in _page_annots(pdf)[0]]
        assert subtypes == [Name.Link]


def test_repair_annotation_flags_clears_popup_of_kept_parent():
    with pikepdf.open(RESOURCES / 'link.pdf') as pdf:
        text, popup = _add_text_with_popup(pdf, pdf.pages[1], flags=4)
        popup.F = 32 | 4  # NoView
        result = repair_annotation_flags(pdf)
        assert dict(result.removed) == {'Popup': 1}
        assert result.removed_pages == {2}
        assert '/Popup' not in text
        subtypes = [annot.Subtype for annot in _page_annots(pdf)[1]]
        assert subtypes == [Name.Link, Name.Text]


def test_repair_annotation_flags_public_standalone(tmp_path):
    """The repair is public API and works on its own, without prepare()."""
    import pikepdf.pdfa

    assert 'repair_annotation_flags' in pikepdf.pdfa.__all__
    assert 'AnnotationRepairResult' in pikepdf.pdfa.__all__
    from pikepdf.pdfa import AnnotationRepairResult
    from pikepdf.pdfa import repair_annotation_flags as public_repair

    with pikepdf.new() as pdf:
        page = pdf.add_blank_page()
        uri = pikepdf.Dictionary(S=Name.URI, URI=pikepdf.String('https://a.b/'))
        page.Annots = pdf.make_indirect(
            pikepdf.Array(
                [
                    pdf.make_indirect(
                        pikepdf.Dictionary(
                            Type=Name.Annot,
                            Subtype=Name.Link,
                            Rect=[0, 0, 10, 10],
                            A=uri,
                        )
                    ),
                    pdf.make_indirect(
                        pikepdf.Dictionary(
                            Type=Name.Annot,
                            Subtype=Name.Link,
                            Rect=[20, 20, 30, 30],
                            A=uri,
                            F=32,  # NoView
                        )
                    ),
                ]
            )
        )
        pdf.save(tmp_path / 'plain.pdf')

    with pikepdf.open(tmp_path / 'plain.pdf') as pdf:
        result = public_repair(pdf)
        assert isinstance(result, AnnotationRepairResult)
        assert result.print_flags_set == 1
        assert dict(result.removed) == {'Link': 1}
        assert result.removed_pages == {1}
        (annot,) = pdf.pages[0].Annots
        assert annot.F == 4
        assert annot.Rect == [0, 0, 10, 10]


def test_repair_annotation_flags_warns_once(caplog):
    with pikepdf.open(RESOURCES / 'link.pdf') as pdf:
        pdf.pages[0].Annots[0].F = 2
        pdf.pages[1].Annots[0].F = 32
        _add_text_with_popup(pdf, pdf.pages[1], flags=2)
        with caplog.at_level(logging.DEBUG, logger='pikepdf.pdfa'):
            repair_annotation_flags(pdf)
    warnings = [m for m in caplog.messages if m.startswith('Removed')]
    assert warnings == [
        "Removed 4 annotations (2 Link, 1 Popup, 1 Text) on pages 1, 2 that "
        "are hidden or not viewable, which PDF/A does not permit"
    ]


def test_repair_annotation_flags_omits_many_pages(caplog):
    with pikepdf.new() as pdf:
        for _ in range(6):
            page = pdf.add_blank_page()
            page.Annots = pdf.make_indirect(pikepdf.Array())
            _add_text_with_popup(pdf, page, flags=2)
        with caplog.at_level(logging.DEBUG, logger='pikepdf.pdfa'):
            repair_annotation_flags(pdf)
    assert caplog.messages == [
        "Removed 12 annotations (6 Popup, 6 Text) that are hidden or not "
        "viewable, which PDF/A does not permit"
    ]


@pytest.mark.parametrize('flavour', ['1b', '2b'])
def test_removed_annotations_candidate_validates(tmp_path, flavour, caplog):
    modified = tmp_path / 'annots.pdf'
    with pikepdf.open(RESOURCES / 'link.pdf') as pdf:
        pdf.pages[0].Annots[0].F = 2 | 4  # Hidden
        pdf.pages[1].Annots[0].F = 16  # NoRotate, Print clear
        _add_text_with_popup(pdf, pdf.pages[1], flags=32)  # NoView
        pdf.save(modified)
    with caplog.at_level(logging.DEBUG, logger='pikepdf.pdfa'):
        out = _save_pdfa(modified, tmp_path / 'out.pdf', flavour)
    assert sum('Removed 3 annotations' in m for m in caplog.messages) == 1
    with pikepdf.open(out) as pdf:
        annots = _page_annots(pdf)
        assert annots[0] == []
        assert [annot.F for annot in annots[1]] == [16 | 4]
    report = validate_written(out, flavour)
    assert report.passed, report.summary()
    assert_verapdf_agrees(out, flavour)


def _dates(pdf: pikepdf.Pdf) -> tuple[dict[str, str], dict[str, str]]:
    info = {
        k: str(pdf.docinfo[k])
        for k in ('/CreationDate', '/ModDate')
        if k in pdf.docinfo
    }
    meta = pdf.open_metadata(set_pikepdf_as_editor=False, update_docinfo=False)
    xmp = {
        k: meta[k]
        for k in ('xmp:CreateDate', 'xmp:ModifyDate', 'xmp:MetadataDate')
        if k in meta
    }
    return info, xmp


def test_assume_local_time_zone_for_dates(los_angeles_tz):
    with pikepdf.open(RESOURCES / 'jbig2.pdf') as pdf:
        info, xmp = _dates(pdf)
        assert info['/CreationDate'] == 'D:20160119123847'
        assert xmp['xmp:CreateDate'] == '2016-01-19T12:38:47'
        # Make the other dates unzoned too
        pdf.docinfo[Name.ModDate] = 'D:20220806213659'
        with pdf.open_metadata(
            set_pikepdf_as_editor=False, update_docinfo=False
        ) as meta:
            meta['xmp:ModifyDate'] = '2022-08-06T21:36:59'
            meta['xmp:MetadataDate'] = '2022-08-06T14:36:59.055384'

        assert assume_local_time_zone_for_dates(pdf) == 5
        info, xmp = _dates(pdf)
        assert info == {
            '/CreationDate': "D:20160119123847-08'00",
            '/ModDate': "D:20220806213659-07'00",
        }
        assert xmp == {
            'xmp:CreateDate': '2016-01-19T12:38:47-08:00',
            'xmp:ModifyDate': '2022-08-06T21:36:59-07:00',
            'xmp:MetadataDate': '2022-08-06T14:36:59.055384-07:00',
        }
        # Idempotent
        assert assume_local_time_zone_for_dates(pdf) == 0


def test_assume_local_time_zone_for_dates_without_xmp(los_angeles_tz):
    with pikepdf.open(RESOURCES / 'ccitt.pdf') as pdf:
        assert '/Metadata' not in pdf.Root
        assert assume_local_time_zone_for_dates(pdf) == 2
        assert '/Metadata' not in pdf.Root
        assert str(pdf.docinfo.CreationDate) == "D:20160119123847-08'00"
        assert str(pdf.docinfo.ModDate) == "D:20160119123847-08'00"


@pytest.mark.parametrize('flavour', ['1b', '2b'])
def test_unzoned_dates_candidate_validates(tmp_path, flavour):
    out = _save_pdfa(RESOURCES / 'jbig2.pdf', tmp_path / 'out.pdf', flavour)
    with pikepdf.open(out) as pdf:
        info, xmp = _dates(pdf)
    created = decode_pdf_date(info['/CreationDate'])
    assert created.tzinfo is not None
    assert created == dt.datetime.fromisoformat(xmp['xmp:CreateDate'])
    report = validate_written(out, flavour)
    assert report.passed, report.summary()
    assert_verapdf_agrees(out, flavour)


@pytest.mark.parametrize(
    ('docinfo_date', 'expected'),
    [
        ('D:202001011230', "D:20200101123000-08'00"),
        ('D:2020010112', "D:20200101120000-08'00"),
        ("D:20200101120000-05'", "D:20200101120000-05'00"),
    ],
)
def test_prepare_keeps_partial_docinfo_dates(los_angeles_tz, docinfo_date, expected):
    """Legal PDF dates with omitted fields are kept, not misread or deleted."""
    with pikepdf.open(RESOURCES / 'ccitt.pdf') as pdf:
        pdf.docinfo.CreationDate = docinfo_date
        prepare(pdf, '2b')
        info, xmp = _dates(pdf)
    assert info['/CreationDate'] == expected
    assert decode_pdf_date(expected) == dt.datetime.fromisoformat(xmp['xmp:CreateDate'])


# --- /BaseEncoding of non-symbolic TrueType fonts ----------------------------------

HELLO_DIFFERENCES = [72, Name.H, 101, Name.e, 108, Name.l, 111, Name.o]


def _without_base_encoding(
    differences: list, text: bytes = b'Hello', part: str = '2'
) -> pikepdf.Pdf:
    pdf = make_simple_truetype_pdf(part, text, subset_text="Helo'")
    pdf.pages[0].Resources.Font.F1.Encoding = pikepdf.Dictionary(
        Type=Name.Encoding, Differences=differences
    )
    return pdf


def _validate(pdf: pikepdf.Pdf, path: Path, part: str = '2'):
    save_candidate(pdf, path, part)
    return validate_written(path, f'{part}b')


def _font_form(pdf: pikepdf.Pdf, content: bytes) -> pikepdf.Stream:
    font = pdf.pages[0].Resources.Font.F1
    return pdf.make_stream(
        content,
        Type=Name.XObject,
        Subtype=Name.Form,
        BBox=[0, 0, 100, 100],
        Resources=pikepdf.Dictionary(Font=pikepdf.Dictionary(F1=font)),
    )


@pytest.mark.parametrize(
    'differences',
    [HELLO_DIFFERENCES, [72, Name.H]],
    ids=['every-code-in-differences', 'other-codes-same-in-both'],
)
def test_base_encoding_added(tmp_path, differences):
    pdf = _without_base_encoding(differences)
    before = _validate(pdf, tmp_path / 'before.pdf')
    assert 'ISO_19005_2:6.2.11.6-2' in {f.rule for f in before.findings}
    failed = verapdf_failed_rules(tmp_path / 'before.pdf', '2b')
    assert failed is None or 'ISO_19005_2:6.2.11.6-2' in failed

    result = prepare(pdf, '2b')
    assert result.base_encodings_added == 1
    assert (
        'debug',
        'Based the encoding of 1 TrueType font on WinAnsiEncoding, as PDF/A requires',
    ) in result.messages()
    encoding = pdf.pages[0].Resources.Font.F1.Encoding
    assert encoding.BaseEncoding == Name.WinAnsiEncoding
    assert list(encoding.Differences) == differences
    after = _validate(pdf, tmp_path / 'after.pdf')
    assert after.passed, after.summary()
    assert_verapdf_agrees(tmp_path / 'after.pdf', '2b')
    assert prepare(pdf, '2b').base_encodings_added == 0


def test_base_encoding_declined_for_changed_glyph():
    # 0x27 is quoteright in StandardEncoding but quotesingle in WinAnsiEncoding
    pdf = _without_base_encoding([72, Name.H], text=b"Hel'lo")
    assert add_truetype_base_encodings(pdf) == 0
    assert '/BaseEncoding' not in pdf.pages[0].Resources.Font.F1.Encoding


def test_base_encoding_quote_in_differences():
    pdf = _without_base_encoding([39, Name.quoteright], text=b"Hel'lo")
    assert add_truetype_base_encodings(pdf) == 1


@pytest.mark.parametrize(
    'where', ['form', 'annotation', 'nested-form', 'pattern', 'type3']
)
def test_base_encoding_counts_codes_outside_page_content(where):
    pdf = _without_base_encoding([72, Name.H])
    page = pdf.pages[0]
    form = _font_form(pdf, b"BT /F1 12 Tf (') Tj ET")
    if where == 'form':
        # Scanned although the page does not draw it
        page.Resources.XObject = pikepdf.Dictionary(Fm0=form)
    elif where == 'nested-form':
        outer = pdf.make_stream(
            b'/Fm1 Do',
            Type=Name.XObject,
            Subtype=Name.Form,
            BBox=[0, 0, 100, 100],
            Resources=pikepdf.Dictionary(XObject=pikepdf.Dictionary(Fm1=form)),
        )
        page.Resources.XObject = pikepdf.Dictionary(Fm0=outer)
    elif where == 'pattern':
        form.PatternType = 1
        form.PaintType = 1
        form.TilingType = 1
        form.XStep = form.YStep = 100
        page.Resources.Pattern = pikepdf.Dictionary(P0=form)
    elif where == 'type3':
        page.Resources.Font.T3 = pdf.make_indirect(
            pikepdf.Dictionary(
                Type=Name.Font,
                Subtype=Name.Type3,
                FontBBox=[0, 0, 100, 100],
                FontMatrix=[0.001, 0, 0, 0.001, 0, 0],
                CharProcs=pikepdf.Dictionary(a=form),
                Encoding=pikepdf.Dictionary(Differences=[97, Name.a]),
                FirstChar=97,
                LastChar=97,
                Widths=[100],
                Resources=form.Resources,
            )
        )
    else:
        page.Annots = pdf.make_indirect(
            [
                pikepdf.Dictionary(
                    Type=Name.Annot,
                    Subtype=Name.Square,
                    Rect=[0, 0, 100, 100],
                    F=4,
                    AP=pikepdf.Dictionary(N=form),
                )
            ]
        )
    assert add_truetype_base_encodings(pdf) == 0


@pytest.mark.parametrize(
    'content',
    [
        pytest.param(b'BT /F9 12 Tf (H) Tj ET ', id='unknown-font'),
        pytest.param(b'BT (H) Tj ET ', id='no-font'),
        pytest.param(b'/GS9 gs ', id='unknown-extgstate'),
    ],
)
def test_base_encoding_declined_for_incomplete_scan(content):
    pdf = _without_base_encoding(HELLO_DIFFERENCES)
    contents = pdf.pages[0].Contents
    contents.write(content + contents.read_bytes())
    assert add_truetype_base_encodings(pdf) == 0


def test_base_encoding_font_set_by_extgstate():
    pdf = _without_base_encoding([72, Name.H])
    page = pdf.pages[0]
    page.Resources.ExtGState = pikepdf.Dictionary(
        GS0=pikepdf.Dictionary(Font=[page.Resources.Font.F1, 12])
    )
    contents = page.Contents
    contents.write(contents.read_bytes() + b" BT /GS0 gs (') Tj ET")
    assert add_truetype_base_encodings(pdf) == 0


def test_base_encoding_follows_q_and_Q():
    pdf = _without_base_encoding([72, Name.H])
    page = pdf.pages[0]
    other = pdf.make_indirect(pikepdf.Dictionary(dict(page.Resources.Font.F1.items())))
    other.Encoding = pikepdf.Dictionary(BaseEncoding=Name.WinAnsiEncoding)
    page.Resources.Font.F2 = other
    contents = page.Contents
    # After Q the font is F1 again, so the quote is shown in F1
    contents.write(
        contents.read_bytes() + b" BT /F1 12 Tf q /F2 12 Tf (x) Tj Q (') Tj ET"
    )
    assert add_truetype_base_encodings(pdf) == 0


def test_base_encoding_shared_encoding_dictionary():
    pdf = _without_base_encoding([72, Name.H])
    page = pdf.pages[0]
    f1 = page.Resources.Font.F1
    shared = pdf.make_indirect(f1.Encoding)
    f1.Encoding = shared
    f2 = pdf.make_indirect(pikepdf.Dictionary(dict(f1.items())))
    page.Resources.Font.F2 = f2
    contents = page.Contents
    contents.write(contents.read_bytes() + b" BT /F2 12 Tf (') Tj ET")
    assert add_truetype_base_encodings(pdf) == 1
    assert f1.Encoding.BaseEncoding == Name.WinAnsiEncoding
    assert f2.Encoding.objgen == shared.objgen
    assert '/BaseEncoding' not in shared


def test_base_encoding_not_added_for_pdfa1():
    pdf = _without_base_encoding(HELLO_DIFFERENCES, part='1')
    assert prepare(pdf, '1b').base_encodings_added == 0
    assert '/BaseEncoding' not in pdf.pages[0].Resources.Font.F1.Encoding


@pytest.mark.parametrize('own_resources', [False, True])
def test_base_encoding_scan_terminates_on_form_cycles(own_resources):
    pdf = _without_base_encoding(HELLO_DIFFERENCES)
    page = pdf.pages[0]
    form = pdf.make_stream(
        b'/Fm0 Do', Type=Name.XObject, Subtype=Name.Form, BBox=[0, 0, 1, 1]
    )
    if own_resources:
        form.Resources = pikepdf.Dictionary(
            XObject=pikepdf.Dictionary(Fm0=form), Font=page.Resources.Font
        )
    page.Resources.XObject = pikepdf.Dictionary(Fm0=form)
    assert add_truetype_base_encodings(pdf) == 1
