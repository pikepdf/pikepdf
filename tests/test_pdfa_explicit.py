# SPDX-FileCopyrightText: 2026 James R. Barlow
# SPDX-License-Identifier: MPL-2.0

"""The PDF/A validator and repairs give the same results in both conversion modes.

Each document is checked once in implicit and once in explicit conversion
mode, and the findings must be identical, as must the effect of every repair.

The whole PDF/A suite can also be run in explicit mode: with
``PIKEPDF_TEST_EXPLICIT=1`` in the environment, the autouse fixture in
``conftest.py`` wraps every test in a ``test_pdfa*`` module in
`pikepdf.explicit_conversion`::

    PIKEPDF_TEST_EXPLICIT=1 uv run pytest tests/test_pdfa*.py -n auto
"""

from __future__ import annotations

import pytest

pytest.importorskip('jsonschema')

import functools
from collections.abc import Callable
from decimal import Decimal
from io import BytesIO
from pathlib import Path

from pdfa_samples import (
    RESOURCES,
    find_type1_font,
    make_clean_candidate,
    make_image_only_pdf,
    make_simple_truetype_pdf,
    make_type1_pdf,
)

import pikepdf
from pikepdf import Array, Dictionary, Name, String
from pikepdf._explicit_conv import implicit_conversion
from pikepdf.pdfa import _engine, check
from pikepdf.pdfa._output_intent import parse_output_intent, replace_output_intents
from pikepdf.pdfa._repair import (
    add_cidsets_for_subset_cidfonts,
    repair_annotation_flags,
    strip_image_interpolation,
)

FLAVOURS = ('1b', '2b')

RESOURCE_PDFS = sorted(RESOURCES.glob('*.pdf'))


def _to_bytes(pdf: pikepdf.Pdf) -> bytes:
    buffer = BytesIO()
    pdf.save(buffer, static_id=True)
    return buffer.getvalue()


def _image_only(mutate: Callable[[pikepdf.Pdf], None] | None = None):
    def build(part: str) -> bytes:
        with make_image_only_pdf(part) as pdf:
            if mutate is not None:
                mutate(pdf)
            return _to_bytes(pdf)

    return build


def _image(pdf: pikepdf.Pdf) -> pikepdf.Stream:
    return pdf.pages[0].Resources.XObject.Im0


def _set_image(key: str, value) -> Callable[[pikepdf.Pdf], None]:
    def mutate(pdf: pikepdf.Pdf) -> None:
        _image(pdf)[Name('/' + key)] = value

    return mutate


def _add_annots(*flags) -> Callable[[pikepdf.Pdf], None]:
    def mutate(pdf: pikepdf.Pdf) -> None:
        annots = []
        for flag in flags:
            annot = Dictionary(
                Type=Name.Annot,
                Subtype=Name.Link,
                Rect=[0, 0, 10, 10],
                Border=[0, 0, 0],
            )
            if flag is not None:
                annot.F = flag
            annots.append(pdf.make_indirect(annot))
        pdf.pages[0].obj.Annots = Array(annots)

    return mutate


def _add_pattern(pdf: pikepdf.Pdf) -> None:
    pattern = pdf.make_stream(
        b'0 0 10 10 re f',
        Type=Name.Pattern,
        PatternType=1,
        PaintType=1,
        TilingType=1,
        BBox=[0, 0, 10, 10],
        XStep=10,
        YStep=10,
        Resources=Dictionary(),
    )
    pdf.pages[0].Resources.Pattern = Dictionary(P0=pattern)


def _set_doc_info(pdf: pikepdf.Pdf) -> None:
    pdf.docinfo.Title = String('Title')
    pdf.docinfo.Trapped = True


def _set_page_scalars(pdf: pikepdf.Pdf) -> None:
    page = pdf.pages[0].obj
    page.Rotate = Decimal('90.0')
    page.UserUnit = 2
    page.MediaBox = Array([0, Decimal('0.5'), True, String('792')])


def _indirect_scalars(pdf: pikepdf.Pdf) -> None:
    page = pdf.pages[0].obj
    with pikepdf.explicit_conversion():
        page.Rotate = pdf.make_indirect(pikepdf.Integer(0))
        page.UserUnit = pdf.make_indirect(pikepdf.Real('1.0'))
        _image(pdf).Interpolate = pdf.make_indirect(pikepdf.Boolean(True))


def _indirect_big_integer(pdf: pikepdf.Pdf) -> None:
    with pikepdf.explicit_conversion():
        pdf.pages[0].obj.Big = pdf.make_indirect(pikepdf.Integer(2**31))


def _scalar_output_profile(pdf: pikepdf.Pdf) -> None:
    pdf.Root.OutputIntents[0].DestOutputProfile = 3


def _set_content(content: bytes) -> Callable[[pikepdf.Pdf], None]:
    def mutate(pdf: pikepdf.Pdf) -> None:
        pdf.pages[0].obj.Contents = pdf.make_stream(content)

    return mutate


def _add_odd_annot(pdf: pikepdf.Pdf) -> None:
    annot = Dictionary(
        Type=Name.Annot,
        Subtype=Dictionary(A=1),
        Rect=[0, 0, 10, 10],
        F=4,
        CA=Array([Decimal('0.5')]),
    )
    pdf.pages[0].obj.Annots = Array([pdf.make_indirect(annot)])


def _truetype(part: str) -> bytes:
    with make_simple_truetype_pdf(part) as pdf:
        return _to_bytes(pdf)


def _truetype_real_widths(part: str) -> bytes:
    with make_simple_truetype_pdf(part) as pdf:
        font = pdf.pages[0].Resources.Font.F1
        font.Widths = Array([Decimal(int(w)) for w in font.Widths])
        font.FirstChar = Decimal(32)
        font.FontDescriptor.Flags = True
        return _to_bytes(pdf)


def _type1(part: str) -> bytes:
    font = find_type1_font()
    if font is None:
        pytest.skip("no Type 1 font installed")
    with make_type1_pdf(font, part) as pdf:
        return _to_bytes(pdf)


def _candidate(path: Path):
    def build(part: str) -> bytes:
        with make_clean_candidate(path, part) as pdf:
            return _to_bytes(pdf)

    return build


def _raw(path: Path):
    def build(part: str) -> bytes:
        return path.read_bytes()

    return build


SAMPLES: dict[str, Callable[[str], bytes]] = {
    'image-only': _image_only(),
    'interpolate-true': _image_only(_set_image('Interpolate', True)),
    'interpolate-false': _image_only(_set_image('Interpolate', False)),
    'interpolate-int': _image_only(_set_image('Interpolate', 1)),
    'bpc-real': _image_only(_set_image('BitsPerComponent', Decimal('8.0'))),
    'bpc-bool': _image_only(_set_image('BitsPerComponent', True)),
    'width-string': _image_only(_set_image('Width', String('8'))),
    'width-real': _image_only(_set_image('Width', Decimal('8'))),
    'imagemask-int': _image_only(_set_image('ImageMask', 1)),
    'decode-mixed': _image_only(_set_image('Decode', Array([0, Decimal('1.0')]))),
    'smask-in-data': _image_only(_set_image('SMaskInData', 1)),
    'annots': _image_only(_add_annots(None, 4, 0, 2, 32, 4 | 256)),
    'annots-odd-flags': _image_only(
        _add_annots(Decimal('4.0'), True, String('4'), Name.Print)
    ),
    'pattern': _image_only(_add_pattern),
    'docinfo': _image_only(_set_doc_info),
    'page-scalars': _image_only(_set_page_scalars),
    'indirect-scalars': _image_only(_indirect_scalars),
    'indirect-big-integer': _image_only(_indirect_big_integer),
    'scalar-output-profile': _image_only(_scalar_output_profile),
    'container-operands': _image_only(
        _set_content(
            b'q [1 2.5] 0 0 rg << /A 1 /B [true] >> 1 1 RG 612 0 0 792 0 0 cm '
            b'/Im0 Do Q BI /W 1 /H 1 /BPC [8] /CS /G /F [<< /A 1 >>] '
            b'/Intent [1] ID\nx\nEI'
        )
    ),
    'colour-space-dict': _image_only(_set_image('ColorSpace', Dictionary(N=3))),
    'colour-space-hival-array': _image_only(
        _set_image(
            'ColorSpace',
            Array([Name.Indexed, Name.DeviceGray, Array([1, Decimal('2.5')]), b'x']),
        )
    ),
    'filter-dict': _image_only(_set_image('Filter', Array([Dictionary(N=3)]))),
    'annot-odd-subtype': _image_only(_add_odd_annot),
    'truetype': _truetype,
    'truetype-real-widths': _truetype_real_widths,
    'type1': _type1,
}
SAMPLES.update({f'raw-{p.stem}': _raw(p) for p in RESOURCE_PDFS})
SAMPLES.update({f'candidate-{p.stem}': _candidate(p) for p in RESOURCE_PDFS})


@functools.cache
def _sample_bytes(name: str, part: str) -> bytes:
    with implicit_conversion():
        return SAMPLES[name](part)


def _findings(report) -> list[tuple[str, str, str, str]]:
    return [(f.rule, f.where, f.message, f.kind) for f in report.findings]


def _in_both_modes(data: bytes, fn: Callable[[pikepdf.Pdf], object]):
    """Return fn(pdf) for *data* opened in implicit and in explicit mode."""
    with implicit_conversion():
        with pikepdf.open(BytesIO(data), conversion_mode='implicit') as pdf:
            implicit = fn(pdf)
    with pikepdf.explicit_conversion():
        with pikepdf.open(BytesIO(data), conversion_mode='explicit') as pdf:
            explicit = fn(pdf)
    return implicit, explicit


@pytest.mark.parametrize('flavour', FLAVOURS)
@pytest.mark.parametrize('name', sorted(SAMPLES))
def test_validator_same_in_both_modes(name, flavour):
    data = _sample_bytes(name, flavour[0])

    def validate(pdf):
        return (
            _findings(_engine.run(pdf, flavour)),
            _findings(check(pdf, flavour)),
        )

    implicit, explicit = _in_both_modes(data, validate)
    assert explicit == implicit


def _repair_all(flavour: str) -> Callable[[pikepdf.Pdf], object]:
    def repair(pdf: pikepdf.Pdf):
        spec = parse_output_intent('sRGB', flavour)
        results = (
            strip_image_interpolation(pdf),
            repair_annotation_flags(pdf),
            add_cidsets_for_subset_cidfonts(pdf),
        )
        replace_output_intents(pdf, spec)
        return results, _to_bytes(pdf)

    return repair


@pytest.mark.parametrize('flavour', FLAVOURS)
@pytest.mark.parametrize('name', sorted(SAMPLES))
def test_repairs_same_in_both_modes(name, flavour):
    data = _sample_bytes(name, flavour[0])
    implicit, explicit = _in_both_modes(data, _repair_all(flavour))
    assert explicit[0] == implicit[0]
    assert explicit[1] == implicit[1]


def test_annotation_flags_kept_in_explicit_mode():
    data = _sample_bytes('annots', '2')

    def flags(pdf):
        repair_annotation_flags(pdf)
        return [pikepdf.unbox(a.get(Name.F)) for a in pdf.pages[0].obj.Annots]

    implicit, explicit = _in_both_modes(data, flags)
    assert implicit == [4, 4, 4]
    assert explicit == implicit


def _rules(data: bytes, flavour: str, *, written: bool = False) -> dict[str, list[str]]:
    with pikepdf.open(BytesIO(data)) as pdf:
        report = _engine.run(pdf, flavour) if written else check(pdf, flavour)
    rules: dict[str, list[str]] = {}
    for finding in report.findings:
        rules.setdefault(finding.rule, []).append(finding.where)
    return rules


def test_indirect_scalars_are_checked_as_values():
    rules = _rules(_sample_bytes('indirect-scalars', '2'), '2b')
    assert 'ISO_19005_2:6.2.8-3' in rules  # /Interpolate true, though indirect


@pytest.mark.parametrize('written', [False, True])
def test_indirect_integer_out_of_range_is_a_limit_finding(written):
    rules = _rules(_sample_bytes('indirect-big-integer', '2'), '2b', written=written)
    assert 'pikepdf:internal' not in rules
    assert rules['ISO_19005_2:6.1.13-1'] == ['obj 4 0']


@pytest.mark.parametrize('written', [False, True])
def test_scalar_output_profile_is_denied(written):
    rules = _rules(_sample_bytes('scalar-output-profile', '2'), '2b', written=written)
    assert 'pikepdf:internal' not in rules
    assert 'pikepdf:schema-OutputIntent' in rules
