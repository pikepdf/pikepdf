# SPDX-FileCopyrightText: 2026 James R. Barlow
# SPDX-License-Identifier: MPL-2.0

from __future__ import annotations

import pytest

pytest.importorskip('jsonschema')

from pdfa_samples import (
    assert_verapdf_agrees,
    assert_verapdf_fails,
    make_image_only_pdf,
    save_candidate,
    save_image_only_pdf,
    verapdf_failed_rules,
)

import pikepdf
from pikepdf import Dictionary, Name
from pikepdf.pdfa import Flavour, validate_written
from pikepdf.pdfa._content import (
    MAX_Q_DEPTH,
    OPERATORS,
    ContentWalker,
    operands_match,
    scan_raw_content,
)
from pikepdf.pdfa._context import ValidationContext
from pikepdf.pdfa._report import ValidationReport

DRAW_IMAGE = b'q 612 0 0 792 0 0 cm /Im0 Do Q'


def rule_ids(report: ValidationReport) -> set[str]:
    return {f.rule for f in report.findings}


def run(tmp_path, content: bytes, part: str = '2', mutate=None) -> ValidationReport:
    """Validate the image-only sample with *content* as its page content."""

    def set_content(pdf: pikepdf.Pdf) -> None:
        pdf.pages[0].Contents = pdf.make_stream(content)
        if mutate is not None:
            mutate(pdf)

    path = save_image_only_pdf(tmp_path / 'c.pdf', part, set_content)
    return validate_written(path, f'{part}b')


def add_form(pdf: pikepdf.Pdf, content: bytes, **keys) -> pikepdf.Stream:
    form = pdf.make_stream(
        content, Type=Name.XObject, Subtype=Name.Form, BBox=[0, 0, 612, 792], **keys
    )
    pdf.pages[0].Resources.XObject.Fm0 = form
    return form


def test_operator_table_is_table_a1():
    assert len(OPERATORS) == 73 - 3  # Table A.1 less BI, ID, EI (inline image)
    assert 'PS' not in OPERATORS
    assert operands_match('nnnnnn', [1, 0, 0, 1, 0, 0])
    assert not operands_match('nnnnnn', [1, 0])
    assert not operands_match('n', [True])
    assert not operands_match('N', [pikepdf.String('x')])


@pytest.mark.parametrize('part', ['1', '2'])
def test_graphics_and_text_state_operators_approved(tmp_path, part):
    content = (
        b'q 1 0 0 1 0 0 cm 2 J 1 j 0.5 w 4 M [3 1] 0 d /Perceptual ri 1 i '
        b'0 0 m 10 10 l 5 5 5 5 10 0 c 1 1 2 2 v 1 1 2 2 y h S '
        b'0 0 10 10 re W n 0.5 g 0.5 G 1 0 0 rg 0 1 0 RG /DeviceGray cs 0.3 sc '
        b'/DeviceRGB CS 0 0 1 SC /DeviceRGB cs 1 0 0 scn f '
        b'/P BMC EMC /P << /MCID 0 >> BDC EMC /X MP /Y << /A 1 >> DP '
        b'BX EX 1 Tc 2 Tw 100 Tz 12 TL 0 Tr 0 Ts Q ' + DRAW_IMAGE
    )
    report = run(tmp_path, content, part)
    assert report.passed, report.summary()
    assert_verapdf_agrees(tmp_path / 'c.pdf', f'{part}b')


@pytest.mark.parametrize(
    'content, part, rule',
    [
        (b'1 2 foo', '2', 'ISO_19005_2:6.2.2-1'),
        (b'BX 1 2 foo EX', '2', 'ISO_19005_2:6.2.2-1'),
        (b'(x) PS', '2', 'ISO_19005_2:6.2.2-1'),
        (b'1 2 foo', '1', 'ISO_19005_1:6.2.10-1'),
    ],
)
def test_undefined_operator_denied(tmp_path, content, part, rule):
    assert rule in rule_ids(run(tmp_path, content + b' ' + DRAW_IMAGE, part))


def test_q_depth(tmp_path):
    ok = b'q ' * MAX_Q_DEPTH + b'Q ' * MAX_Q_DEPTH
    assert run(tmp_path, ok + DRAW_IMAGE).passed
    deep = b'q ' * (MAX_Q_DEPTH + 1) + b'Q ' * (MAX_Q_DEPTH + 1)
    assert 'ISO_19005_2:6.1.13-8' in rule_ids(run(tmp_path, deep + DRAW_IMAGE))
    assert 'ISO_19005_1:6.1.12-8' in rule_ids(run(tmp_path, deep + DRAW_IMAGE, '1'))


def test_q_depth_is_cumulative_through_forms(tmp_path):
    def mutate(pdf):
        add_form(pdf, b'q q Q Q', Resources=Dictionary())

    outer = b'q ' * (MAX_Q_DEPTH - 1)
    content = outer + b'/Fm0 Do ' + b'Q ' * (MAX_Q_DEPTH - 1)
    assert 'ISO_19005_2:6.1.13-8' in rule_ids(run(tmp_path, content, mutate=mutate))
    # The second use of the form is served from the cache and still checked
    content = b'/Fm0 Do ' + outer + b'/Fm0 Do ' + b'Q ' * (MAX_Q_DEPTH - 1)
    assert 'ISO_19005_2:6.1.13-8' in rule_ids(run(tmp_path, content, mutate=mutate))


@pytest.mark.parametrize(
    'content',
    [b'Q', b'ET', b'BT BT ET ET', b'(x) Tj', b'1 2 Td', b'BT', b'EX'],
)
def test_content_syntax_denied(tmp_path, content):
    assert 'pikepdf:content-syntax' in rule_ids(run(tmp_path, content))


@pytest.mark.parametrize(
    'content', [b'1 2 cm', b'/F1 Tf', b'1 2 Tr', b'(a) (b) Tj', b'8 Tr', b'1.5 Tr']
)
def test_bad_operands_denied(tmp_path, content):
    assert 'pikepdf:content-operands' in rule_ids(run(tmp_path, content))


@pytest.mark.parametrize('content', [b'(abc', b'<< /A 1', b'<00', b'1 Tr 2'])
def test_truncated_content_denied(tmp_path, content):
    assert 'pikepdf:content-parse' in rule_ids(run(tmp_path, content))


@pytest.mark.parametrize(
    'item, rule',
    [
        # An indirect scalar is encoded as its value, which the schema checks
        (1, 'pikepdf:schema-Page'),
        (True, 'pikepdf:schema-Page'),
        # The schema sees other indirect elements only as references, so the
        # content walk checks that each one is a stream
        (Name.Foo, 'pikepdf:content-parse'),
        (pikepdf.Array(), 'pikepdf:content-parse'),
    ],
)
def test_contents_array_item_not_a_stream_denied(tmp_path, item, rule):
    def mutate(pdf):
        pdf.pages[0].Contents = pikepdf.Array(
            [pdf.make_stream(b'q Q'), pdf.make_indirect(item)]
        )

    report = run(tmp_path, b'', mutate=mutate)
    assert rule in rule_ids(report), report.summary()


@pytest.mark.parametrize('content', [b'true Tr', b'[1 true] 0 d', b'true g'])
def test_boolean_operand_is_not_a_number(tmp_path, content):
    assert 'pikepdf:content-operands' in rule_ids(run(tmp_path, content))


def test_text_without_font_denied(tmp_path):
    assert 'pikepdf:text-no-font' in rule_ids(run(tmp_path, b'BT (x) Tj ET'))


def test_missing_font_resource_denied(tmp_path):
    report = run(tmp_path, b'BT /F9 12 Tf (x) Tj ET')
    assert 'ISO_19005_2:6.2.2-2' in rule_ids(report)


@pytest.mark.parametrize(
    'content, rule',
    [
        (b'1 0 0 rg', None),
        (b'0 0 0 1 k', 'ISO_19005_2:6.2.4.3-3'),
        (b'/DeviceCMYK cs', 'ISO_19005_2:6.2.4.3-3'),
        (b'0 0 0 1 K', 'ISO_19005_2:6.2.4.3-3'),
    ],
)
def test_device_colour_with_rgb_intent(tmp_path, content, rule):
    report = run(tmp_path, content + b' ' + DRAW_IMAGE)
    if rule is None:
        assert report.passed, report.summary()
    else:
        assert rule in rule_ids(report)


def test_device_colour_without_intent(tmp_path):
    def mutate(pdf):
        del pdf.Root['/OutputIntents']

    report = run(tmp_path, b'1 0 0 rg 0.5 g', mutate=mutate)
    assert {'ISO_19005_2:6.2.4.3-2', 'ISO_19005_2:6.2.4.3-4'} <= rule_ids(report)
    report = run(tmp_path, b'1 0 0 rg', '1', mutate=mutate)
    assert 'ISO_19005_1:6.2.3.3-1' in rule_ids(report)


def test_colour_space_resources_unsupported(tmp_path):
    report = run(tmp_path, b'/CS0 cs 1 sc')
    assert 'ISO_19005_2:6.2.2-2' in rule_ids(report)
    report = run(tmp_path, b'/Pattern cs /P0 scn')
    assert 'pikepdf:pattern' in rule_ids(report)


def test_colour_operand_count_denied(tmp_path):
    report = run(tmp_path, b'/DeviceRGB cs 0.5 sc')
    assert 'pikepdf:content-operands' in rule_ids(report)


@pytest.mark.parametrize(
    'intent, part, rule',
    [
        (b'/Foo', '2', 'ISO_19005_2:6.2.6-1'),
        (b'/Foo', '1', 'ISO_19005_1:6.2.9-1'),
        (b'/Saturation', '2', None),
    ],
)
def test_rendering_intent(tmp_path, intent, part, rule):
    report = run(tmp_path, intent + b' ri ' + DRAW_IMAGE, part)
    if rule is None:
        assert report.passed, report.summary()
    else:
        assert rule in rule_ids(report)


def test_shading_unsupported(tmp_path):
    assert 'pikepdf:shading' in rule_ids(run(tmp_path, b'/Sh0 sh'))


def test_d0_d1_outside_type3_denied(tmp_path):
    assert 'pikepdf:d0-d1' in rule_ids(run(tmp_path, b'500 0 d0'))


# --- inline images -----------------------------------------------------------------


def inline(dictionary: bytes, data: bytes = b'\x00') -> bytes:
    return b'q 10 0 0 10 0 0 cm BI ' + dictionary + b' ID ' + data + b' EI Q '


@pytest.mark.parametrize('part', ['1', '2'])
def test_inline_image_approved(tmp_path, part):
    report = run(tmp_path, inline(b'/W 1 /H 1 /CS /G /BPC 8') + DRAW_IMAGE, part)
    assert report.passed, report.summary()
    assert_verapdf_agrees(tmp_path / 'c.pdf', f'{part}b')


@pytest.mark.parametrize(
    'dictionary, part, rule',
    [
        (b'/W 1 /H 1 /CS /G /BPC 8 /F /LZW', '2', 'ISO_19005_2:6.1.10-1'),
        (b'/W 1 /H 1 /CS /G /BPC 8 /F [/AHx /LZW]', '1', 'ISO_19005_1:6.1.10-2'),
        (b'/W 1 /H 1 /CS /G /BPC 8 /F /JPX', '2', 'pikepdf:inline-image'),
        (b'/W 1 /H 1 /CS /G /BPC 8 /I true', '2', 'ISO_19005_2:6.2.8-3'),
        (b'/W 1 /H 1 /CS /G /BPC 8 /I true', '1', 'ISO_19005_1:6.2.4-3'),
        (b'/W 1 /H 1 /CS /G /BPC 8 /L 1', '2', 'pikepdf:inline-image'),
        (b'/W 1 /H 1 /CS /G /BPC 16', '1', 'ISO_19005_1:6.2.4-4'),
        (b'/W 1 /H 1 /CS /G /BPC 8 /Intent /Foo', '2', 'ISO_19005_2:6.2.6-1'),
        (b'/W 1 /H 1 /CS /CMYK /BPC 8', '2', 'ISO_19005_2:6.2.4.3-3'),
        (b'/W 1 /H 1 /CS /CS0 /BPC 8', '2', 'ISO_19005_2:6.2.2-2'),
        (
            b'/W 1 /H 1 /CS [/I /RGB 1 <000000>] /BPC 8',
            '2',
            'pikepdf:schema-ColorSpace',
        ),
        (b'/W 1 /H 1 /CS [/I /CMYK 0 <00000000>] /BPC 8', '2', 'ISO_19005_2:6.2.4.3-3'),
        (b'/W 1 /H 1 /BPC 8', '2', 'pikepdf:inline-image'),
        # /BitsPerComponent is an Integer: a Real or Boolean is not one, even
        # if it compares equal to an allowed value
        (b'/W 1 /H 1 /CS /G /BPC 8.0', '2', 'ISO_19005_2:6.2.8-4'),
        (b'/W 1 /H 1 /CS /G /BPC 1.0', '1', 'ISO_19005_1:6.2.4-4'),
        (b'/W 1 /H 1 /CS /G /BPC true', '2', 'ISO_19005_2:6.2.8-4'),
        (b'/W 1 /H 1 /IM true /BPC 1.0', '2', 'pikepdf:inline-image'),
        (b'/W 1 /H 1 /IM true /BPC true', '2', 'pikepdf:inline-image'),
    ],
)
def test_inline_image_denied(tmp_path, dictionary, part, rule):
    assert rule in rule_ids(run(tmp_path, inline(dictionary), part))


@pytest.mark.parametrize(
    'dictionary',
    [
        b'/W 1 /H 1 /CS [/I /RGB 1 <000000FFFFFF>] /BPC 8',
        b'/W 1 /H 1 /CS [/Indexed /DeviceRGB 1 <000000FFFFFF>] /BPC 1',
    ],
)
def test_inline_image_indexed_approved(tmp_path, dictionary):
    report = run(tmp_path, inline(dictionary) + DRAW_IMAGE)
    assert report.passed, report.summary()
    assert_verapdf_agrees(tmp_path / 'c.pdf', '2b')


def test_inline_image_mask_approved(tmp_path):
    report = run(tmp_path, inline(b'/W 1 /H 1 /IM true') + DRAW_IMAGE)
    assert report.passed, report.summary()


# --- Form XObjects -----------------------------------------------------------------


@pytest.mark.parametrize('part', ['1', '2'])
def test_form_with_resources_approved(tmp_path, part):
    def mutate(pdf):
        add_form(pdf, DRAW_IMAGE, Resources=pdf.pages[0].Resources)

    report = run(tmp_path, b'/Fm0 Do', part, mutate)
    assert report.passed, report.summary()
    assert_verapdf_agrees(tmp_path / 'c.pdf', f'{part}b')


def test_form_without_resources_denied(tmp_path):
    def mutate(pdf):
        add_form(pdf, DRAW_IMAGE)

    report = run(tmp_path, b'/Fm0 Do', mutate=mutate)
    assert 'ISO_19005_2:6.2.2-2' in rule_ids(report)
    report = run(tmp_path, b'/Fm0 Do', '1', mutate)
    assert 'pikepdf:resource-missing' in rule_ids(report)


def test_form_cycle_denied(tmp_path):
    def mutate(pdf):
        form = add_form(pdf, b'/Fm0 Do')
        form.Resources = Dictionary(XObject=Dictionary(Fm0=form))

    report = run(tmp_path, b'/Fm0 Do', mutate=mutate)
    assert 'pikepdf:form-cycle' in rule_ids(report)


def test_unused_form_content_is_checked(tmp_path):
    def mutate(pdf):
        add_form(pdf, b'1 2 foo', Resources=Dictionary())

    report = run(tmp_path, DRAW_IMAGE, mutate=mutate)
    assert 'ISO_19005_2:6.2.2-1' in rule_ids(report)


@pytest.mark.parametrize(
    'key, value, part, rule',
    [
        ('/Ref', Dictionary(), '2', 'ISO_19005_2:6.2.9-2'),
        ('/PS', Dictionary(), '2', 'ISO_19005_2:6.2.9-1'),
        ('/Subtype2', Name.PS, '2', 'ISO_19005_2:6.2.9-1'),
        ('/OPI', Dictionary(), '2', 'ISO_19005_2:6.2.9-1'),
        ('/Ref', Dictionary(), '1', 'ISO_19005_1:6.2.6-1'),
        ('/PS', Dictionary(), '1', 'ISO_19005_1:6.2.5-1'),
        ('/Foo', 1, '2', 'pikepdf:schema-FormXObject'),
        (
            '/Group',
            Dictionary(S=Name.Transparency, CS=Name.DeviceRGB),
            '1',
            'ISO_19005_1:6.4-3',
        ),
    ],
)
def test_form_dictionary_denied(tmp_path, key, value, part, rule):
    def mutate(pdf):
        form = add_form(pdf, DRAW_IMAGE, Resources=pdf.pages[0].Resources)
        form[key] = value

    assert rule in rule_ids(run(tmp_path, b'/Fm0 Do', part, mutate))


def test_form_group_approved_in_2b(tmp_path):
    def mutate(pdf):
        form = add_form(pdf, DRAW_IMAGE, Resources=pdf.pages[0].Resources)
        form.Group = Dictionary(S=Name.Transparency, CS=Name.DeviceRGB)

    report = run(tmp_path, b'/Fm0 Do', mutate=mutate)
    assert report.passed, report.summary()


def test_do_inside_text_object_unsupported(tmp_path):
    report = run(tmp_path, b'BT /Im0 Do ET')
    assert 'pikepdf:content-syntax' in rule_ids(report)


# --- marked content -------------------------------------------------------------------


def test_optional_content_marked_content(tmp_path):
    report = run(tmp_path, b'/OC /MC0 BDC EMC ' + DRAW_IMAGE)
    finding = next(f for f in report.findings if f.rule == 'pikepdf:optional-content')
    assert finding.kind == 'unsupported'
    report = run(tmp_path, b'/OC /MC0 BDC EMC ' + DRAW_IMAGE, '1')
    assert 'ISO_19005_1:6.1.13-1' in rule_ids(report)


def test_marked_content_property_name_must_resolve(tmp_path):
    report = run(tmp_path, b'/Span /P0 BDC EMC ' + DRAW_IMAGE)
    assert 'ISO_19005_2:6.2.2-2' in rule_ids(report)


# --- resources and the page tree ---------------------------------------------------------


def _inherit_resources(pdf: pikepdf.Pdf) -> None:
    page = pdf.pages[0].obj
    resources = page.Resources
    del page['/Resources']
    pdf.Root.Pages.Resources = resources


@pytest.mark.parametrize('part, passes', [('1', True), ('2', False)])
def test_page_tree_resources(tmp_path, part, passes):
    """Resources inherited from /Pages fail 6.2.2-2 in veraPDF (2b only)."""
    path = save_image_only_pdf(tmp_path / 'c.pdf', part, _inherit_resources)
    report = validate_written(path, f'{part}b')
    assert report.passed is passes, report.summary()
    if not passes:
        assert 'ISO_19005_2:6.2.2-2' in rule_ids(report)
    failed = verapdf_failed_rules(path, f'{part}b')
    if failed is not None:
        assert (not failed) is passes, failed


def test_instruction_budget(tmp_path):
    with make_image_only_pdf() as pdf:
        pdf.pages[0].Contents = pdf.make_stream(b'q Q ' * 10)
        path = save_candidate(pdf, tmp_path / 'c.pdf', '2')
    with pikepdf.open(path) as pdf:
        report = ValidationReport(Flavour('2b'))
        ctx = ValidationContext(Flavour('2b'), pdf, report)
        ctx.output_intent_cs = 'RGB '
        ctx.max_instructions = 5
        ContentWalker(ctx).walk_page(pdf.pages[0], 'page')
    assert 'pikepdf:content-budget' in rule_ids(report)


# --- raw content bytes ------------------------------------------------------------


@pytest.mark.parametrize(
    'content, part, rule',
    [
        (b'BT /F1 12 Tf <48455> Tj ET', '2', 'ISO_19005_2:6.1.6-1'),
        (b'BT /F1 12 Tf <48455> Tj ET', '1', 'ISO_19005_1:6.1.6-1'),
        (b'/P << /ActualText <FEFF004> >> BDC EMC', '2', 'ISO_19005_2:6.1.6-1'),
        (b'/P << /ActualText <FEFF 00 4> >> BDC EMC', '2', 'ISO_19005_2:6.1.6-1'),
        (b'/P << /ActualText <FEFF00ZZ> >> BDC EMC', '2', 'pikepdf:content-parse'),
    ],
)
def test_malformed_hex_string_denied(tmp_path, content, part, rule):
    report = run(tmp_path, content + b' ' + DRAW_IMAGE, part)
    assert rule in rule_ids(report), report.summary()
    if rule.startswith('ISO'):
        assert_verapdf_fails(tmp_path / 'c.pdf', f'{part}b', rule)


@pytest.mark.parametrize(
    'data, images, clauses',
    [
        (b'<0> <00> <0 0> < 0 >', [], ['6.1.6-1', '6.1.6-1']),
        (b'<0g> <0.> <<>>', [], ['6.1.6-2', '6.1.6-2']),
        (b'(<0> \\) <0>) (() <0>) % <0>\r<00>', [], []),
        (b'BI /W 1 ID <0> EI <00>', [b'<0> '], []),
        (b'BI /W 1 ID\n<0>\nEI BI ID xyz EI', [b'<0>\n', b'xyz '], []),
        (b'BI /W 1 ID <0> EI', [b'other'], ['inline-image']),
        (b'BI /W 1 ID <0> EI', [], ['inline-image']),
        (b'<00>', [b'x'], ['inline-image']),
        (b'/ID <0> 1 IDx <00>', [], ['6.1.6-1']),
    ],
)
def test_scan_raw_content(data, images, clauses):
    assert [clause for clause, _ in scan_raw_content(data, images)] == clauses


def test_malformed_hex_string_in_form_denied(tmp_path):
    def mutate(pdf):
        add_form(pdf, b'/P << /ActualText <FEFF004> >> BDC EMC', Resources=Dictionary())

    report = run(tmp_path, b'/Fm0 Do ' + DRAW_IMAGE, mutate=mutate)
    assert 'ISO_19005_2:6.1.6-1' in rule_ids(report), report.summary()


def test_malformed_hex_string_in_second_content_stream_denied(tmp_path):
    def mutate(pdf):
        pdf.pages[0].Contents = pikepdf.Array(
            [pdf.make_stream(DRAW_IMAGE), pdf.make_stream(b'/P <</A <123>>> BDC EMC')]
        )

    report = run(tmp_path, b'', mutate=mutate)
    assert 'ISO_19005_2:6.1.6-1' in rule_ids(report), report.summary()


@pytest.mark.parametrize(
    'content',
    [
        b'/P << /ActualText <FEFF 0041\n> /Alt (a <b> c) >> BDC EMC',
        b'% a comment <123>\n/P << /A (\\) <1>) >> BDC EMC',
        b'/P << /A ((nested) <1>) >> BDC EMC',
        b'/P <</A<<>>/B<>>> BDC EMC',
        inline(b'/W 3 /H 1 /CS /G /BPC 8', b'<1>'),
        inline(b'/W 1 /H 1 /CS /G /BPC 8 /Decode [1 0]'),
    ],
)
def test_well_formed_hex_strings_approved(tmp_path, content):
    report = run(tmp_path, content + b' ' + DRAW_IMAGE)
    assert report.passed, report.summary()
    assert_verapdf_agrees(tmp_path / 'c.pdf', '2b')


@pytest.mark.parametrize(
    'data',
    [
        b'\x00 EI 0 0 0 1 k \xff\xfe',
        b'\x00\tEI\t0 0 0 1 k \xff',
        b'\x00\rEI\r0 0 0 1 k \xff',
    ],
)
def test_inline_image_with_ei_in_data_denied(tmp_path, data):
    report = run(tmp_path, inline(b'/W 4 /H 4 /BPC 8 /CS /G', data) + DRAW_IMAGE)
    assert 'pikepdf:inline-image' in rule_ids(report), report.summary()
    failed = verapdf_failed_rules(tmp_path / 'c.pdf', '2b')
    if failed is not None:
        assert failed
