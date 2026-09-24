# SPDX-FileCopyrightText: 2026 James R. Barlow
# SPDX-License-Identifier: MPL-2.0

"""Annotations, outlines, actions and the structure tree."""

from __future__ import annotations

import pytest

pytest.importorskip('jsonschema')

from pdfa_samples import (
    RESOURCES,
    assert_verapdf_agrees,
    assert_verapdf_fails,
    make_clean_candidate,
    save_candidate,
    save_image_only_pdf,
    verapdf_failed_rules,
)

import pikepdf
from pikepdf import Array, Dictionary, Name, String
from pikepdf.pdfa import validate
from pikepdf.pdfa._report import ValidationReport

PRINT = 4
RECT = [100, 100, 200, 150]


def rule_ids(report: ValidationReport) -> set[str]:
    return {f.rule for f in report.findings}


def check(pdf: pikepdf.Pdf, path, part: str = '2') -> ValidationReport:
    save_candidate(pdf, path, part)
    return validate(path, f'{part}b')


def appearance(pdf: pikepdf.Pdf, content: bytes = b'0 0 1 rg 0 0 100 50 re f'):
    return pdf.make_stream(
        content,
        Type=Name.XObject,
        Subtype=Name.Form,
        BBox=[0, 0, 100, 50],
        Resources=Dictionary(),
    )


def annotate(tmp_path, make_annots, part: str = '2'):
    """Add the annotations *make_annots(pdf)* returns to the image-only sample."""

    def apply(pdf: pikepdf.Pdf) -> None:
        annots = [pdf.make_indirect(a) for a in make_annots(pdf)]
        for annot in annots:
            annot.P = pdf.pages[0].obj
        pdf.pages[0].obj.Annots = Array(annots)

    path = save_image_only_pdf(tmp_path / 'c.pdf', part, apply)
    return validate(path, f'{part}b'), path


def link(pdf, **keys) -> Dictionary:
    entries = dict(
        Type=Name.Annot,
        Subtype=Name.Link,
        Rect=RECT,
        F=PRINT,
        Border=[0, 0, 0],
        A=Dictionary(S=Name.URI, URI=String('https://ocrmypdf.readthedocs.io/')),
    )
    entries.update(keys)
    return Dictionary(**entries)


def text(pdf, **keys) -> Dictionary:
    entries = dict(
        Type=Name.Annot,
        Subtype=Name.Text,
        Rect=RECT,
        F=PRINT,
        Contents=String('note'),
        AP=Dictionary(N=appearance(pdf)),
    )
    entries.update(keys)
    return Dictionary(**entries)


# --- resource files -------------------------------------------------------------------


@pytest.mark.parametrize('part', ['1', '2'])
def test_link_pdf_without_annotation_flags_denied(tmp_path, part):
    pdf = make_clean_candidate(RESOURCES / 'link.pdf', part)
    report = check(pdf, tmp_path / 'c.pdf', part)
    rule = 'ISO_19005_1:6.5.3-2' if part == '1' else 'ISO_19005_2:6.3.2-1'
    assert rule_ids(report) == {rule}
    assert_verapdf_fails(tmp_path / 'c.pdf', f'{part}b', rule)


@pytest.mark.parametrize('part', ['1', '2'])
def test_link_pdf_approved(tmp_path, part):
    """link.pdf: Link annotations, ICCBased colour, gs, symbolic TrueType."""
    pdf = make_clean_candidate(RESOURCES / 'link.pdf', part)
    for page in pdf.pages:
        for annot in page.obj.get('/Annots', []):
            annot.F = PRINT
    report = check(pdf, tmp_path / 'c.pdf', part)
    assert report.passed, report.summary()
    assert_verapdf_agrees(tmp_path / 'c.pdf', f'{part}b')


@pytest.mark.parametrize('part', ['1', '2'])
def test_outlines_approved(tmp_path, part):
    """francais.pdf has an outline; its XMP is replaced as the pipeline does."""
    pdf = make_clean_candidate(RESOURCES / 'francais.pdf', part)
    assert '/Outlines' in pdf.Root
    report = check(pdf, tmp_path / 'c.pdf', part)
    assert report.passed, report.summary()
    assert_verapdf_agrees(tmp_path / 'c.pdf', f'{part}b')


@pytest.mark.parametrize('name', ['toc.pdf', 'acroform.pdf'])
def test_interactive_forms_unsupported(tmp_path, name):
    report = check(make_clean_candidate(RESOURCES / name), tmp_path / 'c.pdf')
    assert not report.passed
    assert {f.kind for f in report.findings} == {'unsupported'}


def test_optional_content_unsupported(tmp_path):
    report = check(make_clean_candidate(RESOURCES / 'blank.pdf'), tmp_path / 'c.pdf')
    assert not report.passed
    assert {f.kind for f in report.findings} == {'unsupported'}
    assert any('/OCProperties' in f.where for f in report.findings)


def test_needs_rendering_denied(tmp_path):
    report = check(
        make_clean_candidate(RESOURCES / 'livecycle.pdf'), tmp_path / 'c.pdf'
    )
    assert 'ISO_19005_2:6.4.2-2' in rule_ids(report)
    assert_verapdf_fails(tmp_path / 'c.pdf', '2b', 'ISO_19005_2:6.4.2-2')


def test_overlay_blocked_by_producer_keys(tmp_path):
    """overlay.pdf passes veraPDF, but PDFpen's private keys are not allowed.

    An accepted coverage gap: unknown keys in form XObjects, content streams
    and pages are denied because the validator cannot know what they mean.
    """
    pdf = make_clean_candidate(
        RESOURCES / 'overlay.pdf', strip_keys=('/PDFpenVersion', '/Thumb')
    )
    report = check(pdf, tmp_path / 'c.pdf')
    assert not report.passed
    assert all(
        'PDFpen' in f.message
        for f in report.findings
        if f.rule.startswith('pikepdf:schema-')
    ), report.summary()
    assert_verapdf_agrees(tmp_path / 'c.pdf', '2b')


@pytest.mark.parametrize('part', ['1', '2'])
def test_structure_tree_approved(tmp_path, part):
    pdf = make_clean_candidate(
        RESOURCES / 'tagged.pdf', part, strip_keys=('/DocChecksum',)
    )
    report = check(pdf, tmp_path / 'c.pdf', part)
    assert report.passed, report.summary()
    assert_verapdf_agrees(tmp_path / 'c.pdf', f'{part}b')


def _first_element(pdf: pikepdf.Pdf) -> pikepdf.Dictionary:
    kids = pdf.Root.StructTreeRoot.K
    element = kids[0] if isinstance(kids, pikepdf.Array) else kids
    while isinstance(element.get('/K'), pikepdf.Array) and isinstance(
        element.K[0], pikepdf.Dictionary
    ):
        element = element.K[0]
    return element


@pytest.mark.parametrize('where', ['element', 'rolemap'])
def test_structure_type_not_utf8_denied(tmp_path, where):
    pdf = make_clean_candidate(
        RESOURCES / 'tagged.pdf', '2', strip_keys=('/DocChecksum',)
    )
    bad = pikepdf.Object.parse(b'/\xb0\xa1')
    if where == 'element':
        _first_element(pdf).S = bad
    else:
        pdf.Root.StructTreeRoot.RoleMap = pikepdf.Object.parse(b'<< /\xb0\xa1 /P >>')
    report = check(pdf, tmp_path / 'c.pdf')
    assert 'ISO_19005_2:6.1.8-1' in rule_ids(report)
    assert_verapdf_fails(tmp_path / 'c.pdf', '2b', 'ISO_19005_2:6.1.8-1')


def test_structure_tree_cycle_terminates(tmp_path):
    pdf = make_clean_candidate(
        RESOURCES / 'tagged.pdf', '2', strip_keys=('/DocChecksum',)
    )
    element = _first_element(pdf)
    element.K = Array([element])
    report = check(pdf, tmp_path / 'c.pdf')
    assert report.passed, report.summary()


# --- synthetic annotations ------------------------------------------------------------


@pytest.mark.parametrize('part', ['1', '2'])
def test_annotations_approved(tmp_path, part):
    def make(pdf):
        popup = pdf.make_indirect(
            Dictionary(Type=Name.Annot, Subtype=Name.Popup, Rect=RECT, F=PRINT)
        )
        note = pdf.make_indirect(text(pdf, Popup=popup, T=String('me')))
        popup.Parent = note
        square = Dictionary(
            Type=Name.Annot,
            Subtype=Name.Square,
            Rect=RECT,
            F=PRINT,
            C=[1, 0, 0],
            AP=Dictionary(N=appearance(pdf, b'1 0 0 RG 1 1 98 48 re S')),
        )
        return [link(pdf), note, popup, square]

    report, path = annotate(tmp_path, make, part)
    assert report.passed, report.summary()
    assert_verapdf_agrees(path, f'{part}b')


def test_popup_without_flags(tmp_path):
    def make(pdf):
        return [Dictionary(Type=Name.Annot, Subtype=Name.Popup, Rect=RECT)]

    report, path = annotate(tmp_path, make)
    assert report.passed, report.summary()
    assert_verapdf_agrees(path, '2b')
    report, path = annotate(tmp_path, make, '1')
    assert 'ISO_19005_1:6.5.3-2' in rule_ids(report)
    assert_verapdf_fails(path, '1b', 'ISO_19005_1:6.5.3-2')


@pytest.mark.parametrize(
    'flags, part, rule',
    [
        (None, '2', 'ISO_19005_2:6.3.2-1'),
        (None, '1', 'ISO_19005_1:6.5.3-2'),
        (0, '2', 'ISO_19005_2:6.3.2-2'),
        (PRINT | 2, '2', 'ISO_19005_2:6.3.2-2'),
        (PRINT | 1, '1', 'ISO_19005_1:6.5.3-2'),
        (PRINT | 32, '2', 'ISO_19005_2:6.3.2-2'),
        (PRINT | 256, '2', 'ISO_19005_2:6.3.2-2'),
        (PRINT | 256, '1', None),
        (PRINT | 128, '2', None),
    ],
)
def test_annotation_flags(tmp_path, flags, part, rule):
    def make(pdf):
        annot = link(pdf)
        if flags is None:
            del annot['/F']
        else:
            annot.F = flags
        return [annot]

    report, path = annotate(tmp_path, make, part)
    if rule is None:
        assert report.passed, report.summary()
        assert_verapdf_agrees(path, f'{part}b')
    else:
        assert rule in rule_ids(report), report.summary()
        assert_verapdf_fails(path, f'{part}b', rule)


@pytest.mark.parametrize(
    'mutate, part, rule',
    [
        (lambda pdf, a: a.__delitem__('/AP'), '2', 'ISO_19005_2:6.3.3-1'),
        (
            lambda pdf, a: a.AP.__setitem__('/D', appearance(pdf)),
            '2',
            'ISO_19005_2:6.3.3-2',
        ),
        (
            lambda pdf, a: a.AP.__setitem__('/R', appearance(pdf)),
            '1',
            'ISO_19005_1:6.5.3-4',
        ),
        (
            lambda pdf, a: a.AP.__setitem__('/N', Dictionary(On=appearance(pdf))),
            '2',
            'ISO_19005_2:6.3.3-4',
        ),
        (
            lambda pdf, a: a.AP.__setitem__(
                '/N', pdf.make_indirect(Dictionary(On=appearance(pdf)))
            ),
            '1',
            'ISO_19005_1:6.5.3-6',
        ),
        (lambda pdf, a: a.__setitem__('/CA', 0.5), '1', 'ISO_19005_1:6.5.3-1'),
        (
            lambda pdf, a: a.__setitem__('/AA', Dictionary()),
            '2',
            'pikepdf:schema-TextAnnot',
        ),
        (lambda pdf, a: a.__setitem__('/Foo', 1), '2', 'pikepdf:schema-TextAnnot'),
        (
            lambda pdf, a: a.AP.N.write(b'1 2 foo'),
            '2',
            'ISO_19005_2:6.2.2-1',
        ),
        (
            lambda pdf, a: a.AP.N.write(b'0 0 0 1 k'),
            '2',
            'ISO_19005_2:6.2.4.3-3',
        ),
    ],
)
def test_text_annotation_denied(tmp_path, mutate, part, rule):
    def make(pdf):
        annot = text(pdf)
        mutate(pdf, annot)
        return [annot]

    report, path = annotate(tmp_path, make, part)
    assert rule in rule_ids(report), report.summary()
    if rule.startswith('ISO'):
        assert_verapdf_fails(path, f'{part}b', rule)


def test_zero_size_annotation_needs_no_appearance(tmp_path):
    def make(pdf):
        annot = text(pdf, Rect=[100, 100, 100, 100])
        del annot['/AP']
        return [annot]

    report, path = annotate(tmp_path, make)
    assert report.passed, report.summary()
    assert_verapdf_agrees(path, '2b')


def test_appearance_stream_starts_with_default_state(tmp_path):
    """Appearance streams do not inherit the page's graphics state."""

    def make(pdf):
        return [text(pdf, AP=Dictionary(N=appearance(pdf, b'BT (x) Tj ET')))]

    report, _ = annotate(tmp_path, make)
    assert 'pikepdf:text-no-font' in rule_ids(report)


def test_colour_in_1b_needs_rgb_intent(tmp_path):
    def make(pdf):
        del pdf.Root['/OutputIntents']
        return [link(pdf, C=[1, 0, 0])]

    report, _ = annotate(tmp_path, make, '1')
    assert 'ISO_19005_1:6.5.3-3' in rule_ids(report)


@pytest.mark.filterwarnings('ignore:This document has 1 form widget')
@pytest.mark.parametrize(
    'subtype, part, rule, kind',
    [
        (Name.Sound, '2', 'ISO_19005_2:6.3.1-1', 'violation'),
        (Name.Movie, '2', 'ISO_19005_2:6.3.1-1', 'violation'),
        (Name('/3D'), '2', 'ISO_19005_2:6.3.1-1', 'violation'),
        (Name.Foo, '2', 'ISO_19005_2:6.3.1-1', 'violation'),
        (Name.FileAttachment, '1', 'ISO_19005_1:6.5.2-1', 'violation'),
        (Name.Polygon, '1', 'ISO_19005_1:6.5.2-1', 'violation'),
        (Name.Widget, '2', 'pikepdf:schema-Annot', 'unsupported'),
        (Name.FileAttachment, '2', 'pikepdf:schema-Annot', 'unsupported'),
        (Name.FreeText, '2', 'pikepdf:schema-Annot', 'unsupported'),
    ],
)
def test_annotation_types(tmp_path, subtype, part, rule, kind):
    def make(pdf):
        return [text(pdf, Subtype=subtype)]

    report, path = annotate(tmp_path, make, part)
    finding = next(f for f in report.findings if f.rule == rule)
    assert finding.kind == kind
    if kind == 'violation' and subtype != Name.Foo:
        failed = verapdf_failed_rules(path, f'{part}b')
        if failed is not None:
            assert rule in failed


def test_link_action_denied(tmp_path):
    def make(pdf):
        return [link(pdf, A=Dictionary(S=Name.JavaScript, JS=String('app.alert(1)')))]

    report, path = annotate(tmp_path, make)
    assert 'ISO_19005_2:6.5.1-1' in rule_ids(report)
    assert_verapdf_fails(path, '2b', 'ISO_19005_2:6.5.1-1')


def test_link_destination_approved(tmp_path):
    def make(pdf):
        annot = link(pdf, Dest=Array([pdf.pages[0].obj, Name.Fit]))
        del annot['/A']
        return [annot]

    report, path = annotate(tmp_path, make)
    assert report.passed, report.summary()
    assert_verapdf_agrees(path, '2b')


def test_popup_parent_cycle_is_not_a_role_conflict(tmp_path):
    """A popup is reached from the page and from its parent's /Popup."""

    def make(pdf):
        popup = pdf.make_indirect(
            Dictionary(Type=Name.Annot, Subtype=Name.Popup, Rect=RECT, F=PRINT)
        )
        note = pdf.make_indirect(text(pdf, Popup=popup, IRT=popup))
        popup.Parent = note
        return [popup, note]

    report, _ = annotate(tmp_path, make)
    assert 'pikepdf:role-conflict' not in rule_ids(report)
    assert report.passed, report.summary()


def test_shared_appearance_stream_is_checked_once(tmp_path):
    def make(pdf):
        stream = appearance(pdf)
        return [text(pdf, AP=Dictionary(N=stream)) for _ in range(3)]

    report, _ = annotate(tmp_path, make)
    assert report.passed, report.summary()


@pytest.mark.parametrize(
    'part, rule', [('1', 'ISO_19005_1:6.5.3-4'), ('2', 'ISO_19005_2:6.3.3-2')]
)
def test_empty_appearance_dictionary_denied(tmp_path, part, rule):
    def make(pdf):
        return [text(pdf, AP=Dictionary())]

    report, path = annotate(tmp_path, make, part)
    assert rule in rule_ids(report)
    assert_verapdf_fails(path, f'{part}b', rule)


@pytest.mark.parametrize(
    'part, rule', [('1', 'ISO_19005_1:6.6.1-2'), ('2', 'ISO_19005_2:6.5.1-2')]
)
def test_named_action_without_name_denied(tmp_path, part, rule):
    def make(pdf):
        return [link(pdf, A=Dictionary(S=Name.Named))]

    report, path = annotate(tmp_path, make, part)
    assert rule in rule_ids(report)
    assert_verapdf_fails(path, f'{part}b', rule)


def test_named_action_approved(tmp_path):
    def make(pdf):
        return [link(pdf, A=Dictionary(S=Name.Named, N=Name.NextPage))]

    report, path = annotate(tmp_path, make)
    assert report.passed, report.summary()
    assert_verapdf_agrees(path, '2b')


def _uri_action() -> Dictionary:
    return Dictionary(S=Name.URI, URI=String('https://ocrmypdf.readthedocs.io/'))


@pytest.mark.parametrize(
    'make_next',
    [
        lambda: _uri_action(),
        lambda: Array([_uri_action(), _uri_action()]),
    ],
    ids=['dict', 'array'],
)
def test_action_next_approved(tmp_path, make_next):
    def make(pdf):
        return [link(pdf, A=Dictionary(S=Name.URI, URI=String('x'), Next=make_next()))]

    report, path = annotate(tmp_path, make)
    assert report.passed, report.summary()
    assert_verapdf_agrees(path, '2b')


@pytest.mark.parametrize(
    'make_next',
    [lambda: Dictionary(), lambda: Dictionary(X=_uri_action())],
    ids=['empty', 'wrapper'],
)
def test_action_next_is_one_action(tmp_path, make_next):
    def make(pdf):
        return [link(pdf, A=Dictionary(S=Name.URI, URI=String('x'), Next=make_next()))]

    report, path = annotate(tmp_path, make)
    assert 'pikepdf:schema-Action' in rule_ids(report), report.summary()
    assert_verapdf_fails(path, '2b', 'ISO_19005_2:6.5.1-1')
