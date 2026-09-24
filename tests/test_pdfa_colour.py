# SPDX-FileCopyrightText: 2026 James R. Barlow
# SPDX-License-Identifier: MPL-2.0

"""Colour spaces, images, graphics state parameters and implementation limits."""

from __future__ import annotations

import pytest

pytest.importorskip('jsonschema')

import zlib
from decimal import Decimal

from pdfa_samples import (
    RESOURCES,
    assert_verapdf_agrees,
    assert_verapdf_fails,
    make_candidate,
    make_clean_candidate,
    save_candidate,
    save_image_only_pdf,
    verapdf_failed_rules,
)

import pikepdf
from pikepdf import Array, Dictionary, Name, String
from pikepdf.pdfa import validate_written
from pikepdf.pdfa._report import ValidationReport

DRAW_IMAGE = b'q 612 0 0 792 0 0 cm /Im0 Do Q'


def rule_ids(report: ValidationReport) -> set[str]:
    return {f.rule for f in report.findings}


def check(pdf: pikepdf.Pdf, path, part: str = '2') -> ValidationReport:
    save_candidate(pdf, path, part)
    return validate_written(path, f'{part}b')


def run(tmp_path, mutate, part: str = '2', content: bytes | None = None):
    """Validate the image-only sample after *mutate*; return (report, path)."""

    def apply(pdf: pikepdf.Pdf) -> None:
        if content is not None:
            pdf.pages[0].Contents = pdf.make_stream(content)
        mutate(pdf)

    path = save_image_only_pdf(tmp_path / 'c.pdf', part, apply)
    return validate_written(path, f'{part}b'), path


def srgb_profile(pdf: pikepdf.Pdf) -> pikepdf.Stream:
    """An ICCBased profile stream holding the sRGB OutputIntent profile."""
    data = pdf.Root.OutputIntents[0].DestOutputProfile.read_bytes()
    return pdf.make_stream(data, N=3, Alternate=Name.DeviceRGB)


@pytest.fixture(scope='module')
def cmyk_profile() -> bytes:
    """A CMYK printer profile (ICC version 2), from cmyk.pdf's /DefaultCMYK."""
    with pikepdf.open(RESOURCES / 'cmyk.pdf') as pdf:
        return pdf.pages[0].Resources.ColorSpace.DefaultCMYK[1].read_bytes()


def image(pdf: pikepdf.Pdf) -> pikepdf.Stream:
    return pdf.pages[0].Resources.XObject.Im0


def set_rgb_image(pdf: pikepdf.Pdf, colour_space) -> None:
    im = image(pdf)
    im.write(zlib.compress(bytes(8 * 8 * 3)), filter=Name.FlateDecode)
    im.ColorSpace = colour_space


# --- resource files -----------------------------------------------------------------


def _no_interpolate(pdf: pikepdf.Pdf) -> pikepdf.Pdf:
    # Interpolate true is a genuine 6.2.8-3 violation in these files
    for obj in pdf.objects:
        if isinstance(obj, pikepdf.Stream) and '/Interpolate' in obj:
            del obj['/Interpolate']
    return pdf


@pytest.mark.parametrize('part', ['1', '2'])
def test_icc_based_image_approved(tmp_path, part):
    pdf = _no_interpolate(make_candidate(RESOURCES / 'c03-29.pdf', part))
    report = check(pdf, tmp_path / 'c.pdf', part)
    assert report.passed, report.summary()
    assert_verapdf_agrees(tmp_path / 'c.pdf', f'{part}b')


def test_icc_based_image_interpolate_denied(tmp_path):
    report = check(make_candidate(RESOURCES / 'c03-29.pdf'), tmp_path / 'c.pdf')
    assert rule_ids(report) == {'ISO_19005_2:6.2.8-3'}
    assert_verapdf_fails(tmp_path / 'c.pdf', '2b', 'ISO_19005_2:6.2.8-3')


def test_icc_and_smask_multipage(tmp_path):
    pdf = _no_interpolate(make_candidate(RESOURCES / 'multipage.pdf'))
    report = check(pdf, tmp_path / 'c.pdf')
    assert report.passed, report.summary()
    assert_verapdf_agrees(tmp_path / 'c.pdf', '2b')

    pdf = _no_interpolate(make_candidate(RESOURCES / 'multipage.pdf', '1'))
    report = check(pdf, tmp_path / 'c1.pdf', '1')
    assert 'ISO_19005_1:6.4-2' in rule_ids(report)
    assert_verapdf_fails(tmp_path / 'c1.pdf', '1b', 'ISO_19005_1:6.4-2')


@pytest.mark.parametrize('part', ['1', '2'])
def test_indexed_image_approved(tmp_path, part):
    pdf = make_candidate(RESOURCES / 'palette.pdf', part)
    report = check(pdf, tmp_path / 'c.pdf', part)
    assert report.passed, report.summary()
    assert_verapdf_agrees(tmp_path / 'c.pdf', f'{part}b')


def test_cmyk_images_with_default_cmyk(tmp_path):
    """cmyk.pdf paints DeviceCMYK images, permitted by its ICCBased DefaultCMYK.

    It is still denied for a private image key (/ImageName, which veraPDF
    ignores: an accepted coverage gap) and for font widths (veraPDF agrees).
    """
    pdf = make_clean_candidate(RESOURCES / 'cmyk.pdf')
    report = check(pdf, tmp_path / 'c.pdf')
    assert 'ISO_19005_2:6.2.4.3-3' not in rule_ids(report)
    assert rule_ids(report) == {'pikepdf:schema-ImageXObject', 'ISO_19005_2:6.2.11.5-1'}
    failed = verapdf_failed_rules(tmp_path / 'c.pdf', '2b')
    if failed is not None:
        assert failed == {'ISO_19005_2:6.2.11.5-1'}


def test_cmyk_images_without_default_cmyk_denied(tmp_path):
    pdf = make_clean_candidate(RESOURCES / 'cmyk.pdf')
    del pdf.pages[0].Resources.ColorSpace['/DefaultCMYK']
    report = check(pdf, tmp_path / 'c.pdf')
    assert 'ISO_19005_2:6.2.4.3-3' in rule_ids(report)
    assert_verapdf_fails(tmp_path / 'c.pdf', '2b', 'ISO_19005_2:6.2.4.3-3')


def test_cmyk_images_with_cmyk_intent(tmp_path, cmyk_profile):
    pdf = make_clean_candidate(RESOURCES / 'cmyk.pdf')
    del pdf.pages[0].Resources.ColorSpace['/DefaultCMYK']
    intent = pdf.Root.OutputIntents[0]
    intent.DestOutputProfile = pdf.make_stream(cmyk_profile, N=4)
    intent.OutputConditionIdentifier = String('CMYK')
    report = check(pdf, tmp_path / 'c.pdf')
    assert 'ISO_19005_2:6.2.4.3-3' not in rule_ids(report)
    # The content's DeviceRGB text colour now needs an RGB intent
    failed = verapdf_failed_rules(tmp_path / 'c.pdf', '2b')
    if failed is not None:
        assert 'ISO_19005_2:6.2.4.3-3' not in failed
        ours = {r for r in rule_ids(report) if r.startswith('ISO')}
        assert ours <= failed | {'ISO_19005_2:6.2.11.5-1'}


def test_jpx_unsupported(tmp_path):
    report = check(
        make_clean_candidate(RESOURCES / 'lichtenstein.pdf'), tmp_path / 'c.pdf'
    )
    assert not report.passed
    assert {f.kind for f in report.findings} == {'unsupported'}


def test_vector_patterns_unsupported(tmp_path):
    """vector.pdf passes veraPDF 2b; patterns and shadings are a coverage gap."""
    report = check(make_clean_candidate(RESOURCES / 'vector.pdf'), tmp_path / 'c.pdf')
    assert not report.passed
    assert {f.kind for f in report.findings} == {'unsupported'}
    assert_verapdf_agrees(tmp_path / 'c.pdf', '2b')


# --- colour space mutations on the image-only sample ---------------------------------------


def test_icc_based_image_mutation_approved(tmp_path):
    report, path = run(
        tmp_path,
        lambda pdf: set_rgb_image(pdf, Array([Name.ICCBased, srgb_profile(pdf)])),
    )
    assert report.passed, report.summary()
    assert_verapdf_agrees(path, '2b')


@pytest.mark.parametrize(
    'mutate, rule',
    [
        (lambda s: s.__setitem__('/N', 1), 'pikepdf:icc-components'),
        (lambda s: s.__setitem__('/N', 2), 'pikepdf:schema-ICCBasedStream'),
        (
            lambda s: s.__setitem__('/Alternate', Name.DeviceGray),
            'pikepdf:schema-ICCBasedStream',
        ),
        (lambda s: s.__setitem__('/Foo', 1), 'pikepdf:schema-ICCBasedStream'),
        (lambda s: s.write(b'\x00' * 20), 'ISO_19005_2:6.2.4.2-1'),
    ],
)
def test_icc_based_mutations_denied(tmp_path, mutate, rule):
    def apply(pdf):
        profile = srgb_profile(pdf)
        mutate(profile)
        set_rgb_image(pdf, Array([Name.ICCBased, profile]))

    report, _ = run(tmp_path, apply)
    assert rule in rule_ids(report)


@pytest.mark.parametrize('field, value', [(12, b'abst'), (8, b'\x05')])
def test_icc_based_header_denied(tmp_path, field, value):
    def apply(pdf):
        data = bytearray(pdf.Root.OutputIntents[0].DestOutputProfile.read_bytes())
        data[field : field + len(value)] = value
        set_rgb_image(pdf, Array([Name.ICCBased, pdf.make_stream(bytes(data), N=3)]))

    report, path = run(tmp_path, apply)
    assert 'ISO_19005_2:6.2.4.2-1' in rule_ids(report)
    assert_verapdf_fails(path, '2b', 'ISO_19005_2:6.2.4.2-1')


def test_icc_version_4_denied_in_1b(tmp_path):
    def apply(pdf):
        data = bytearray(pdf.Root.OutputIntents[0].DestOutputProfile.read_bytes())
        data[8] = 4
        set_rgb_image(pdf, Array([Name.ICCBased, pdf.make_stream(bytes(data), N=3)]))

    report, _ = run(tmp_path, apply, '1')
    assert 'ISO_19005_1:6.2.3.2-1' in rule_ids(report)


@pytest.mark.parametrize(
    'colour_space',
    [
        lambda pdf: Array([Name.CalRGB, Dictionary(WhitePoint=[0.9505, 1, 1.089])]),
        lambda pdf: Array(
            [
                Name.CalRGB,
                Dictionary(
                    WhitePoint=[0.9505, 1, 1.089],
                    Gamma=[2.2, 2.2, 2.2],
                    Matrix=[0.41, 0.21, 0.02, 0.36, 0.72, 0.12, 0.18, 0.07, 0.95],
                ),
            ]
        ),
        lambda pdf: Array([Name.Lab, Dictionary(WhitePoint=[0.9505, 1, 1.089])]),
    ],
)
def test_cie_colour_spaces_approved(tmp_path, colour_space):
    report, path = run(tmp_path, lambda pdf: set_rgb_image(pdf, colour_space(pdf)))
    assert report.passed, report.summary()
    assert_verapdf_agrees(path, '2b')


def test_calgray_image_approved(tmp_path):
    def apply(pdf):
        image(pdf).ColorSpace = Array(
            [Name.CalGray, Dictionary(WhitePoint=[0.9505, 1, 1.089], Gamma=2.2)]
        )

    report, _ = run(tmp_path, apply)
    assert report.passed, report.summary()


@pytest.mark.parametrize(
    'colour_space, rule',
    [
        (
            Array([Name.CalRGB, Dictionary(Gamma=[1, 1, 1])]),
            'pikepdf:schema-ColorSpace',
        ),
        (
            Array([Name.CalRGB, Dictionary(WhitePoint=[1, 1])]),
            'pikepdf:schema-ColorSpace',
        ),
        (
            Array([Name.Lab, Dictionary(WhitePoint=[1, 1, 1], Foo=1)]),
            'pikepdf:schema-ColorSpace',
        ),
        (
            Array([Name.Indexed, Name.DeviceRGB, 1, String(b'\0' * 5)]),
            'pikepdf:schema-ColorSpace',
        ),
        (
            Array([Name.Indexed, Name.DeviceRGB, 256, String(b'\0' * 771)]),
            'pikepdf:schema-ColorSpace',
        ),
        (
            Array(
                [
                    Name.Indexed,
                    Array([Name.Indexed, Name.DeviceRGB, 0, String(b'\0\0\0')]),
                    0,
                    String(b'\0'),
                ]
            ),
            'pikepdf:schema-ColorSpace',
        ),
        (
            Array([Name.Indexed, Name.DeviceCMYK, 0, String(b'\0' * 4)]),
            'ISO_19005_2:6.2.4.3-3',
        ),
        (
            Array([Name.Separation, Name.Spot, Name.DeviceGray, Dictionary()]),
            'pikepdf:colour-space',
        ),
        (
            Array([Name.DeviceN, Array([Name.A]), Name.DeviceGray, Dictionary()]),
            'pikepdf:colour-space',
        ),
        (Array([Name.Pattern]), 'pikepdf:colour-space'),
        (Array([Name.Foo]), 'pikepdf:schema-ColorSpace'),
        (Name.CS0, 'pikepdf:schema-ColorSpace'),
        (Name.Pattern, 'pikepdf:colour-space'),
    ],
)
def test_image_colour_space_denied(tmp_path, colour_space, rule):
    report, _ = run(tmp_path, lambda pdf: set_rgb_image(pdf, colour_space))
    assert rule in rule_ids(report), report.summary()


def test_indexed_lookup_stream_approved(tmp_path):
    def apply(pdf):
        lookup = pdf.make_stream(bytes(range(6)))
        image(pdf).ColorSpace = Array([Name.Indexed, Name.DeviceRGB, 1, lookup])

    report, _ = run(tmp_path, apply)
    assert report.passed, report.summary()


def test_colour_space_resource_via_cs(tmp_path):
    def apply(pdf):
        pdf.pages[0].Resources.ColorSpace = Dictionary(
            CS0=Array([Name.ICCBased, srgb_profile(pdf)])
        )

    content = b'/CS0 cs 1 0 0 sc 0 0 10 10 re f /CS0 CS 0 1 0 SC ' + DRAW_IMAGE
    report, path = run(tmp_path, apply, content=content)
    assert report.passed, report.summary()
    assert_verapdf_agrees(path, '2b')
    report, _ = run(tmp_path, apply, content=b'/CS0 cs 1 sc ' + DRAW_IMAGE)
    assert 'pikepdf:content-operands' in rule_ids(report)


def test_unused_colour_space_resource_still_checked(tmp_path):
    def apply(pdf):
        pdf.pages[0].Resources.ColorSpace = Dictionary(
            CS0=Array([Name.Separation, Name.Spot, Name.DeviceGray, Dictionary()])
        )

    report, _ = run(tmp_path, apply)
    assert 'pikepdf:colour-space' in rule_ids(report)


@pytest.mark.parametrize('with_default', [True, False])
def test_default_cmyk_permits_device_cmyk(tmp_path, cmyk_profile, with_default):
    def apply(pdf):
        if with_default:
            pdf.pages[0].Resources.ColorSpace = Dictionary(
                DefaultCMYK=Array([Name.ICCBased, pdf.make_stream(cmyk_profile, N=4)])
            )

    content = b'0 0 0 1 k 0 0 10 10 re f /DeviceCMYK CS 0 0 0 1 SC ' + DRAW_IMAGE
    report, path = run(tmp_path, apply, content=content)
    if with_default:
        assert report.passed, report.summary()
        assert_verapdf_agrees(path, '2b')
    else:
        assert 'ISO_19005_2:6.2.4.3-3' in rule_ids(report)
        assert_verapdf_fails(path, '2b', 'ISO_19005_2:6.2.4.3-3')


def test_default_space_must_be_device_independent(tmp_path):
    def apply(pdf):
        pdf.pages[0].Resources.ColorSpace = Dictionary(DefaultCMYK=Name.DeviceCMYK)

    report, _ = run(tmp_path, apply, content=b'0 0 0 1 k ' + DRAW_IMAGE)
    assert 'pikepdf:colour-space' in rule_ids(report)


def test_default_cmyk_applies_to_images_per_painting_stream(tmp_path, cmyk_profile):
    """/DefaultCMYK of the page applies to images the page paints, not forms."""

    def cmyk_image(pdf):
        im = image(pdf)
        im.write(zlib.compress(bytes(8 * 8 * 4)), filter=Name.FlateDecode)
        im.ColorSpace = Name.DeviceCMYK
        pdf.pages[0].Resources.ColorSpace = Dictionary(
            DefaultCMYK=Array([Name.ICCBased, pdf.make_stream(cmyk_profile, N=4)])
        )

    report, path = run(tmp_path, cmyk_image)
    assert report.passed, report.summary()
    assert_verapdf_agrees(path, '2b')

    def via_form(pdf):
        cmyk_image(pdf)
        form = pdf.make_stream(
            DRAW_IMAGE,
            Type=Name.XObject,
            Subtype=Name.Form,
            BBox=[0, 0, 612, 792],
            Resources=Dictionary(XObject=Dictionary(Im0=image(pdf))),
        )
        pdf.pages[0].Resources.XObject.Fm0 = form

    report, path = run(tmp_path, via_form, content=b'/Fm0 Do')
    assert 'ISO_19005_2:6.2.4.3-3' in rule_ids(report)
    assert_verapdf_fails(path, '2b', 'ISO_19005_2:6.2.4.3-3')


def test_unpainted_device_cmyk_image_denied(tmp_path):
    def apply(pdf):
        im = pdf.make_stream(
            zlib.compress(bytes(4)),
            Type=Name.XObject,
            Subtype=Name.Image,
            Width=1,
            Height=1,
            ColorSpace=Name.DeviceCMYK,
            BitsPerComponent=8,
            Filter=Name.FlateDecode,
        )
        pdf.pages[0].Resources.XObject.Im1 = im

    report, _ = run(tmp_path, apply)
    assert 'ISO_19005_2:6.2.4.3-3' in rule_ids(report)


# --- masks and groups ------------------------------------------------------------------


def _stencil(pdf):
    return pdf.make_stream(
        zlib.compress(bytes(8)),
        Type=Name.XObject,
        Subtype=Name.Image,
        Width=8,
        Height=8,
        ImageMask=True,
        BitsPerComponent=1,
        Filter=Name.FlateDecode,
    )


@pytest.mark.parametrize(
    'mask, rule',
    [
        (lambda pdf: _stencil(pdf), None),
        (lambda pdf: Array([0, 10]), None),
        (lambda pdf: Array([0, 10, 20]), 'pikepdf:schema-ImageXObject'),
        (lambda pdf: Array([0, Decimal('1.5')]), 'pikepdf:schema-ImageXObject'),
        (lambda pdf: image(pdf), 'pikepdf:schema-MaskImage'),
    ],
)
def test_image_mask(tmp_path, mask, rule):
    def apply(pdf):
        image(pdf).Mask = mask(pdf)

    report, path = run(tmp_path, apply)
    if rule is None:
        assert report.passed, report.summary()
        assert_verapdf_agrees(path, '2b')
    else:
        assert rule in rule_ids(report) or 'pikepdf:role-conflict' in rule_ids(report)


def test_smask_must_be_device_gray(tmp_path):
    def apply(pdf):
        smask = pdf.make_stream(
            zlib.compress(bytes(64 * 3)),
            Type=Name.XObject,
            Subtype=Name.Image,
            Width=8,
            Height=8,
            ColorSpace=Name.DeviceRGB,
            BitsPerComponent=8,
            Filter=Name.FlateDecode,
        )
        image(pdf).SMask = smask

    report, _ = run(tmp_path, apply)
    assert 'pikepdf:schema-SMaskImage' in rule_ids(report)


@pytest.mark.parametrize('icc', [True, False])
def test_transparency_group_colour_space(tmp_path, icc):
    def apply(pdf):
        cs = Array([Name.ICCBased, srgb_profile(pdf)]) if icc else Name.DeviceCMYK
        pdf.pages[0].obj.Group = Dictionary(Type=Name.Group, S=Name.Transparency, CS=cs)

    report, path = run(tmp_path, apply)
    if icc:
        assert report.passed, report.summary()
        assert_verapdf_agrees(path, '2b')
    else:
        assert 'ISO_19005_2:6.2.4.3-3' in rule_ids(report)
        assert_verapdf_fails(path, '2b', 'ISO_19005_2:6.2.4.3-3')


# --- graphics state parameter dictionaries --------------------------------------------------


def gs(tmp_path, part: str = '2', content: bytes = b'/GS0 gs ', **params):
    def apply(pdf):
        entries = {k if k.startswith('/') else '/' + k: v for k, v in params.items()}
        pdf.pages[0].Resources.ExtGState = Dictionary(GS0=Dictionary(entries))

    return run(tmp_path, apply, part, content + DRAW_IMAGE)


@pytest.mark.parametrize('part', ['1', '2'])
def test_extgstate_approved(tmp_path, part):
    report, path = gs(
        tmp_path,
        part,
        Type=Name.ExtGState,
        LW=1,
        LC=1,
        LJ=2,
        ML=10,
        D=Array([Array([3, 1]), 0]),
        RI=Name.Perceptual,
        BM=Name.Normal,
        SMask=Name('/None'),
        CA=1,
        ca=1,
        AIS=False,
        TK=True,
        OP=False,
        op=False,
        OPM=1,
        SA=True,
        FL=1,
        SM=Decimal('0.02'),
        TR2=Name.Default,
    )
    assert report.passed, report.summary()
    assert_verapdf_agrees(path, f'{part}b')


def test_extgstate_apple_antialias_key_approved(tmp_path):
    report, _ = gs(tmp_path, **{'/AAPL:AA': False})
    assert report.passed, report.summary()


@pytest.mark.parametrize(
    'params, part, rule',
    [
        (dict(TR=Name.Identity), '2', 'ISO_19005_2:6.2.5-1'),
        (dict(TR=Name.Identity), '1', 'ISO_19005_1:6.2.8-1'),
        (dict(TR2=Name.Identity), '2', 'ISO_19005_2:6.2.5-2'),
        (dict(TR2=Name.Identity), '1', 'ISO_19005_1:6.2.8-2'),
        (dict(HTP=Array([1])), '2', 'ISO_19005_2:6.2.5-3'),
        (dict(HT=Name.Default), '2', 'pikepdf:schema-ExtGState'),
        (dict(RI=Name.Foo), '2', 'ISO_19005_2:6.2.6-1'),
        (dict(RI=Name.Foo), '1', 'ISO_19005_1:6.2.9-1'),
        (dict(BM=Name.Foo), '2', 'ISO_19005_2:6.2.10-1'),
        (dict(BM=Array([Name.Multiply, Name.Foo])), '2', 'ISO_19005_2:6.2.10-1'),
        (dict(BM=Name.Multiply), '1', 'ISO_19005_1:6.4-4'),
        (dict(CA=Decimal('0.5')), '1', 'ISO_19005_1:6.4-5'),
        (dict(ca=Decimal('0.5')), '1', 'ISO_19005_1:6.4-6'),
        (dict(ca=2), '2', 'pikepdf:schema-ExtGState'),
        (dict(Font=Array([Name.F1, 12])), '2', 'pikepdf:schema-ExtGState'),
        (dict(Foo=1), '2', 'pikepdf:schema-ExtGState'),
        (dict(OP=True, OPM=1), '2', 'ISO_19005_2:6.2.4.2-2'),
        (dict(op=True, OPM=1), '2', 'ISO_19005_2:6.2.4.2-2'),
    ],
)
def test_extgstate_denied(tmp_path, params, part, rule):
    report, path = gs(tmp_path, part, **params)
    assert rule in rule_ids(report), report.summary()
    # veraPDF does not check overprint mode unless ICCBased CMYK is used, and
    # checks only a blend mode name, not an array of them
    if (
        rule.startswith('ISO')
        and rule != 'ISO_19005_2:6.2.4.2-2'
        and not isinstance(params.get('BM'), Array)
    ):
        assert_verapdf_fails(path, f'{part}b', rule)


def test_extgstate_unsupported_kinds(tmp_path):
    for params in (dict(HT=Name.Default), dict(Font=Array([Name.F1, 12]))):
        report, _ = gs(tmp_path, **params)
        assert {f.kind for f in report.findings} == {'unsupported'}


def test_overprint_mode_across_dictionaries(tmp_path):
    def apply(pdf):
        pdf.pages[0].Resources.ExtGState = Dictionary(
            GS0=Dictionary(OP=True), GS1=Dictionary(OPM=1), GS2=Dictionary(OP=False)
        )

    rule = 'ISO_19005_2:6.2.4.2-2'
    report, _ = run(tmp_path, apply, content=b'/GS0 gs /GS1 gs ' + DRAW_IMAGE)
    assert rule in rule_ids(report)
    report, _ = run(tmp_path, apply, content=b'/GS0 gs /GS2 gs /GS1 gs ' + DRAW_IMAGE)
    assert report.passed, report.summary()
    report, _ = run(tmp_path, apply, content=b'q /GS0 gs Q /GS1 gs ' + DRAW_IMAGE)
    assert report.passed, report.summary()


def test_extgstate_resource_must_exist(tmp_path):
    report, _ = run(tmp_path, lambda pdf: None, content=b'/GS9 gs ' + DRAW_IMAGE)
    assert 'ISO_19005_2:6.2.2-2' in rule_ids(report)


def _soft_mask(pdf, group=True):
    keys = dict(
        Type=Name.XObject,
        Subtype=Name.Form,
        BBox=[0, 0, 612, 792],
        Resources=Dictionary(),
    )
    if group:
        keys['Group'] = Dictionary(
            Type=Name.Group, S=Name.Transparency, CS=Name.DeviceGray
        )
    form = pdf.make_stream(b'0.5 g 0 0 612 792 re f', **keys)
    return Dictionary(Type=Name.Mask, S=Name.Luminosity, G=form)


@pytest.mark.parametrize('part', ['1', '2'])
def test_extgstate_soft_mask(tmp_path, part):
    def apply(pdf):
        pdf.pages[0].Resources.ExtGState = Dictionary(
            GS0=Dictionary(SMask=_soft_mask(pdf), ca=Decimal('0.5'))
        )

    report, path = run(tmp_path, apply, part, b'/GS0 gs ' + DRAW_IMAGE)
    if part == '2':
        assert report.passed, report.summary()
        assert_verapdf_agrees(path, '2b')
    else:
        assert {'ISO_19005_1:6.4-1', 'ISO_19005_1:6.4-6'} <= rule_ids(report)
        failed = verapdf_failed_rules(path, '1b')
        if failed is not None:
            assert {'ISO_19005_1:6.4-1', 'ISO_19005_1:6.4-6'} <= failed


@pytest.mark.parametrize(
    'mutate, rule',
    [
        (lambda pdf, sm: sm.G.__delitem__('/Group'), 'pikepdf:schema-SoftMaskDict'),
        (
            lambda pdf, sm: sm.__setitem__('/TR', Name.Foo),
            'pikepdf:schema-SoftMaskDict',
        ),
        (lambda pdf, sm: sm.__setitem__('/S', Name.Foo), 'pikepdf:schema-SoftMaskDict'),
        (lambda pdf, sm: sm.G.write(b'1 2 foo'), 'ISO_19005_2:6.2.2-1'),
    ],
)
def test_extgstate_soft_mask_denied(tmp_path, mutate, rule):
    def apply(pdf):
        soft_mask = _soft_mask(pdf)
        mutate(pdf, soft_mask)
        pdf.pages[0].Resources.ExtGState = Dictionary(GS0=Dictionary(SMask=soft_mask))

    report, _ = run(tmp_path, apply, content=b'/GS0 gs ' + DRAW_IMAGE)
    assert rule in rule_ids(report), report.summary()


@pytest.mark.parametrize('part', ['1', '2'])
def test_transparency_1b_vs_2b(tmp_path, part):
    """Constant alpha and a transparency group: fine in 2b, not in 1b."""

    def apply(pdf):
        pdf.pages[0].Resources.ExtGState = Dictionary(GS0=Dictionary(ca=Decimal('0.5')))
        form = pdf.make_stream(
            DRAW_IMAGE,
            Type=Name.XObject,
            Subtype=Name.Form,
            BBox=[0, 0, 612, 792],
            Resources=pdf.pages[0].Resources,
            Group=Dictionary(S=Name.Transparency, CS=Name.DeviceRGB),
        )
        pdf.pages[0].Resources.XObject.Fm0 = form

    report, path = run(tmp_path, apply, part, b'/GS0 gs /Fm0 Do')
    if part == '2':
        assert report.passed, report.summary()
        assert_verapdf_agrees(path, '2b')
    else:
        assert {'ISO_19005_1:6.4-3', 'ISO_19005_1:6.4-6'} <= rule_ids(report)


# --- implementation limits -----------------------------------------------------------------


@pytest.mark.parametrize(
    'value, part, rule',
    [
        (2**31, '2', 'ISO_19005_2:6.1.13-1'),
        (-(2**31) - 1, '1', 'ISO_19005_1:6.1.12-1'),
        (b'400000000000000000000000000000000000000.0', '2', 'ISO_19005_2:6.1.13-2'),
        (Decimal('32768.5'), '1', 'ISO_19005_1:6.1.12-2'),
        (b'0.000000000000000000000000000000000000001', '2', 'ISO_19005_2:6.1.13-5'),
        (String(b'x' * 32768), '2', 'ISO_19005_2:6.1.13-3'),
        (String(b'x' * 65536), '1', 'ISO_19005_1:6.1.12-3'),
        (Name('/' + 'N' * 128), '2', 'ISO_19005_2:6.1.13-4'),
        (Array([0] * 8192), '1', 'ISO_19005_1:6.1.12-5'),
        (Dictionary({f'/K{n}': 0 for n in range(4096)}), '1', 'ISO_19005_1:6.1.12-6'),
        (Array([Dictionary(A=Array([2**31]))]), '2', 'ISO_19005_2:6.1.13-1'),
    ],
)
def test_limits_denied(tmp_path, value, part, rule):
    def apply(pdf):
        if isinstance(value, bytes):
            # pikepdf writes Decimal values through a double; parse reals
            holder = pikepdf.Object.parse(b'<< /Value ' + value + b' >>')
        else:
            holder = Dictionary(Value=value)
        pdf.Root.Foo = pdf.make_indirect(holder)

    report, path = run(tmp_path, apply, part)
    assert rule in rule_ids(report), report.summary()


@pytest.mark.parametrize(
    'value, part',
    [
        (2**31 - 1, '2'),
        (Decimal('32767'), '1'),
        (Decimal('3e38'), '2'),
        (Decimal(0), '2'),
        (String(b'x' * 32767), '2'),
        (String(b'x' * 40000), '1'),
        (Name('/' + 'N' * 127), '2'),
        (Array([0] * 8192), '2'),
    ],
)
def test_limits_approved(tmp_path, value, part):
    def apply(pdf):
        pdf.Root.Foo = pdf.make_indirect(Dictionary(Value=value))

    report, _ = run(tmp_path, apply, part)
    assert not {
        f.rule for f in report.findings if 'limit' in f.rule or '6.1.1' in f.rule
    }


@pytest.mark.parametrize(
    'content, part, rule',
    [
        (b'2147483648 0 m', '2', 'ISO_19005_2:6.1.13-1'),
        (
            b'0.00000000000000000000000000000000000000001 0 m',
            '2',
            'ISO_19005_2:6.1.13-5',
        ),
        (b'40000.5 0 m', '1', 'ISO_19005_1:6.1.12-2'),
        (b'/P << /A 2147483648 >> BDC EMC', '2', 'ISO_19005_2:6.1.13-1'),
        (
            b'BI /W 1 /H 1 /CS /G /BPC 8 /Decode [0 2147483648] ID \x00 EI',
            '2',
            'ISO_19005_2:6.1.13-1',
        ),
    ],
)
def test_limits_in_content(tmp_path, content, part, rule):
    report, path = run(tmp_path, lambda pdf: None, part, content + b' ' + DRAW_IMAGE)
    assert rule in rule_ids(report), report.summary()
    assert_verapdf_fails(path, f'{part}b', rule)


def test_limit_reports_are_verified_by_verapdf(tmp_path):
    def apply(pdf):
        pdf.pages[0].obj.Rotate = 0
        image(pdf).Decode = Array([0, 2**31])

    report, path = run(tmp_path, apply)
    assert 'ISO_19005_2:6.1.13-1' in rule_ids(report)
    assert_verapdf_fails(path, '2b', 'ISO_19005_2:6.1.13-1')
