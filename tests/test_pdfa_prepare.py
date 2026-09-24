# SPDX-FileCopyrightText: 2026 James R. Barlow
# SPDX-License-Identifier: MPL-2.0

"""Tests of pikepdf.pdfa.prepare, which applies the PDF/A repairs in memory."""

from __future__ import annotations

import pytest

pytest.importorskip('jsonschema')

import re
from collections import Counter
from io import BytesIO

from pdfa_samples import RESOURCES, make_image_only_pdf

import pikepdf
from pikepdf import Array, Dictionary, Name
from pikepdf.models._cal_icc import build_calrgb_icc
from pikepdf.pdfa import _engine, resolve_save_kwargs, validate_written
from pikepdf.pdfa._output_intent import (
    OutputIntentSpec,
    load_srgb,
    parse_output_intent,
)
from pikepdf.pdfa._prepare import PrepareResult, prepare

PHOTOSHOP = 'http://ns.adobe.com/photoshop/1.0/'
FLAVOURS = ['1b', '2b', '3b']


@pytest.fixture(scope='module')
def cmyk_profile() -> bytes:
    """A CMYK printer profile (ICC version 2), from cmyk.pdf's /DefaultCMYK."""
    with pikepdf.open(RESOURCES / 'cmyk.pdf') as pdf:
        return pdf.pages[0].Resources.ColorSpace.DefaultCMYK[1].read_bytes()


@pytest.fixture(scope='module')
def v4_profile() -> bytes:
    return build_calrgb_icc(
        (0.9505, 1.0, 1.089),
        (2.2, 2.2, 2.2),
        (0.4124, 0.2126, 0.0193, 0.3576, 0.7152, 0.1192, 0.1805, 0.0722, 0.9505),
    )


def _part(flavour: str) -> str:
    return flavour[0]


def make_dirty(flavour: str) -> pikepdf.Pdf:
    """The image-only sample with problems that prepare repairs."""
    pdf = make_image_only_pdf(_part(flavour))
    del pdf.Root.OutputIntents
    pdf.pages[0].Resources.XObject.Im0.Interpolate = True
    hidden = pdf.make_indirect(
        Dictionary(
            Type=Name.Annot,
            Subtype=Name.Text,
            Rect=[0, 0, 10, 10],
            F=2,
        )
    )
    link = pdf.make_indirect(
        Dictionary(
            Type=Name.Annot,
            Subtype=Name.Link,
            Rect=[20, 20, 40, 40],
            Border=[0, 0, 0],
        )
    )
    pdf.pages[0].Annots = Array([hidden, link])
    with pdf.open_metadata(set_pikepdf_as_editor=False, update_docinfo=False) as meta:
        meta[f'{{{PHOTOSHOP}}}ColorMode'] = '3'
    return pdf


def save_bytes(pdf: pikepdf.Pdf, flavour: str) -> bytes:
    buffer = BytesIO()
    pdf.save(buffer, **resolve_save_kwargs(flavour, static_id=True))
    return buffer.getvalue()


def _without_metadata_date(data: bytes) -> bytes:
    return re.sub(rb'(MetadataDate(?:>|="))[^<"]*', rb'\1', data)


@pytest.mark.parametrize('flavour', FLAVOURS)
def test_prepare_repairs_and_passes(flavour, tmp_path):
    with make_dirty(flavour) as pdf:
        result = prepare(pdf, flavour)
        assert isinstance(result, PrepareResult)
        assert result.output_intent_replaced
        assert result.output_intent == 'RGB'
        assert result.interpolation_removed == 1
        assert result.annotations_removed == Counter({'Text': 1})
        assert result.print_flags_set == 1
        assert result.cidsets_added == 0
        assert 'photoshop:ColorMode' in result.xmp_dropped
        assert not result.xmp_unreadable
        assert result.changed
        text = '\n'.join(result.describe())
        assert 'output intent' in text
        assert 'interpolation' in text
        assert '1 annotation (1 Text) on page 1' in text
        assert 'Print flag' in text
        assert 'photoshop:ColorMode' in text
        path = tmp_path / 'out.pdf'
        path.write_bytes(save_bytes(pdf, flavour))
    report = validate_written(path, flavour)
    assert report.verdict == 'pass', report.summary()


@pytest.mark.parametrize('flavour', FLAVOURS)
def test_prepare_is_idempotent(flavour):
    """A second prepare changes nothing but xmp:MetadataDate.

    declare_pdfa_metadata always records pikepdf as the metadata editor with
    the current time, so the saved bytes are compared with the value of
    xmp:MetadataDate blanked out.
    """
    with make_dirty(flavour) as pdf:
        prepare(pdf, flavour)
        first = save_bytes(pdf, flavour)
        again = prepare(pdf, flavour)
        assert not again.changed, again
        assert not again.output_intent_replaced
        assert again.describe() == []
        second = save_bytes(pdf, flavour)
    assert b'MetadataDate' in first
    assert _without_metadata_date(first) == _without_metadata_date(second)


def test_describe_nothing_changed():
    assert PrepareResult().describe() == []
    assert not PrepareResult().changed
    assert PrepareResult().messages() == []


def test_messages_levels():
    result = PrepareResult(
        output_intent_replaced=True,
        output_intent='RGB',
        interpolation_removed=2,
        annotations_removed=Counter({'Text': 1}),
        annotations_removed_pages=frozenset({1}),
        print_flags_set=3,
        cidsets_added=1,
        xmp_dropped=('photoshop:ColorMode',),
        xmp_unreadable=True,
        xmp_problem='XMP is not well-formed XML: oops',
        dates_zoned=1,
        pdfa_declared=True,
    )
    messages = result.messages()
    levels = [level for level, _ in messages]
    assert set(levels) <= {'warning', 'info', 'debug'}
    by_topic = {
        'output intent': 'debug',
        'interpolation': 'debug',
        'annotation (1 Text)': 'warning',
        'Print flag': 'info',
        'CIDSet': 'debug',
        'could not be read': 'info',
        'not permitted in PDF/A': 'info',
        'time zone': 'debug',
        'Declared PDF/A': 'debug',
    }
    assert len(messages) == len(by_topic)
    for topic, level in by_topic.items():
        matches = [lvl for lvl, sentence in messages if topic in sentence]
        assert matches == [level], topic
    assert result.describe() == [sentence for _, sentence in messages]


def test_unreadable_xmp_problem():
    with make_image_only_pdf('2') as pdf:
        pdf.Root.Metadata.write(b'<x:xmpmeta><broken')
        result = prepare(pdf, '2b')
    assert result.xmp_unreadable
    assert result.xmp_problem is not None
    assert 'not well-formed' in result.xmp_problem
    [(level, sentence)] = [m for m in result.messages() if 'could not be read' in m[1]]
    assert level == 'info'
    assert result.xmp_problem in sentence


def test_readable_xmp_has_no_problem():
    with make_image_only_pdf('2') as pdf:
        result = prepare(pdf, '2b')
    assert not result.xmp_unreadable
    assert result.xmp_problem is None


def test_prepare_cmyk_output_intent(cmyk_profile):
    with make_dirty('2b') as pdf:
        result = prepare(pdf, '2b', output_intent=cmyk_profile)
        assert result.output_intent == 'CMYK'
        assert result.output_intent_replaced
        intents = pdf.Root.OutputIntents
        assert len(intents) == 1
        assert intents[0].S == Name.GTS_PDFA1
        assert intents[0].DestOutputProfile.N == 4
        assert intents[0].DestOutputProfile.read_bytes() == cmyk_profile
        assert str(intents[0].OutputConditionIdentifier) == (
            'U.S. Web Coated (SWOP) v2'
        )
        report = _engine.run(pdf, '2b')
    assert report.output_intent == 'CMYK'


def test_prepare_output_condition_identifier():
    with make_dirty('2b') as pdf:
        prepare(pdf, '2b', output_condition_identifier='My printer')
        intent = pdf.Root.OutputIntents[0]
        assert str(intent.OutputConditionIdentifier) == 'My printer'


def test_srgb_case_insensitive():
    spec = parse_output_intent('srgb', '1b')
    assert isinstance(spec, OutputIntentSpec)
    assert spec.icc == load_srgb()
    assert spec.n == 3
    assert spec.colour_space == 'RGB'
    assert spec.identifier == 'sRGB'
    assert parse_output_intent('SRGB', '2b') == spec


def test_parse_none():
    assert parse_output_intent(None, '2b') is None


def test_parse_cmyk(cmyk_profile):
    spec = parse_output_intent(cmyk_profile, '1b')
    assert spec is not None
    assert (spec.n, spec.colour_space) == (4, 'CMYK')


def test_v4_profile_part1_rejected(v4_profile):
    with pytest.raises(ValueError, match='version'):
        parse_output_intent(v4_profile, '1b')
    spec = parse_output_intent(v4_profile, '2b')
    assert spec is not None
    assert (spec.n, spec.colour_space) == (3, 'RGB')


@pytest.mark.parametrize(
    'value',
    [b'', b'garbage' * 50, 'Adobe RGB', b'\x00' * 200],
)
def test_parse_invalid(value):
    with pytest.raises(ValueError):
        parse_output_intent(value, '2b')


def test_parse_wrong_device_class(v4_profile):
    data = bytearray(v4_profile)
    data[12:16] = b'scnr'
    with pytest.raises(ValueError, match='device class'):
        parse_output_intent(bytes(data), '2b')


def test_parse_wrong_colour_space(v4_profile):
    data = bytearray(v4_profile)
    data[16:20] = b'Lab '
    with pytest.raises(ValueError, match='colour space'):
        parse_output_intent(bytes(data), '2b')


@pytest.mark.parametrize('value', [b'garbage' * 50, 'Adobe RGB'])
def test_invalid_intent_mutates_nothing(value, v4_profile):
    with make_dirty('1b') as pdf:
        before = save_bytes(pdf, '1b')
        with pytest.raises(ValueError):
            prepare(pdf, '1b', output_intent=value)
        with pytest.raises(ValueError):
            prepare(pdf, '1b', output_intent=v4_profile)
        assert save_bytes(pdf, '1b') == before


def test_none_keeps_existing_intent(cmyk_profile):
    with make_image_only_pdf('2') as pdf:
        prepare(pdf, '2b', output_intent=cmyk_profile)
        intent = pdf.Root.OutputIntents[0]
        objgen = intent.objgen
        result = prepare(pdf, '2b', output_intent=None)
        assert not result.output_intent_replaced
        assert result.output_intent is None
        assert pdf.Root.OutputIntents[0].objgen == objgen
        assert pdf.Root.OutputIntents[0].DestOutputProfile.N == 4


def test_prepare_explicit_conversion(tmp_path):
    with pikepdf.explicit_conversion(), make_dirty('2b') as pdf:
        result = prepare(pdf, '2b')
        assert result.interpolation_removed == 1
        assert result.annotations_removed == Counter({'Text': 1})
        assert result.print_flags_set == 1
        path = tmp_path / 'out.pdf'
        path.write_bytes(save_bytes(pdf, '2b'))
    assert validate_written(path, '2b').verdict == 'pass'


def test_prepare_declares_pdfa_on_plain_pdf():
    with pikepdf.new() as pdf:
        pdf.add_blank_page()
        result = prepare(pdf, '2b')
        assert result.pdfa_declared
        assert result.changed
        meta = pdf.open_metadata()
        assert meta['pdfaid:part'] == '2'
        assert not prepare(pdf, '2b').pdfa_declared


def test_prepare_fixes_page_count(tmp_path):
    with make_image_only_pdf('2') as pdf:
        pdf.Root.Pages.Count = 5
        prepare(pdf, '2b')
        path = tmp_path / 'out.pdf'
        path.write_bytes(save_bytes(pdf, '2b'))
    with pikepdf.open(path) as pdf:
        assert pdf.Root.Pages.Count == 1


def test_prepare_bad_flavour():
    with make_image_only_pdf('2') as pdf, pytest.raises(ValueError):
        prepare(pdf, '4z')
