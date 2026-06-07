# SPDX-FileCopyrightText: 2026 James R. Barlow
# SPDX-License-Identifier: CC0-1.0

from __future__ import annotations

import pytest

import pikepdf
from pikepdf import (
    Array,
    AttachedFileSpec,
    Dictionary,
    Name,
    Pdf,
    String,
)
from pikepdf.sanitize import (
    Sanitizer,
    remove_attachments,
    remove_external_access,
    remove_javascript,
    remove_search_index,
    remove_thumbnails,
)


def _js_action(pdf, code='app.alert(1)'):
    return pdf.make_indirect(Dictionary(S=Name.JavaScript, JS=String(code)))


@pytest.fixture
def pal(resources):
    with Pdf.open(resources / 'pal.pdf') as pdf:
        yield pdf


@pytest.fixture
def pdf_with_js(pal):
    """A PDF with JavaScript injected into every action-holder slot."""
    # Document-level named JavaScript.
    nt = pikepdf.NameTree.new(pal)
    nt['evil'] = _js_action(pal)
    pal.Root.Names = Dictionary(JavaScript=nt.obj)

    # Catalog OpenAction and additional actions.
    pal.Root.OpenAction = _js_action(pal)
    pal.Root.AA = Dictionary(WC=_js_action(pal))

    # Page additional actions.
    pal.pages[0].obj.AA = Dictionary(O=_js_action(pal))

    # Annotation /A and /AA.
    annot = pal.make_indirect(
        Dictionary(
            Type=Name.Annot,
            Subtype=Name.Widget,
            Rect=Array([0, 0, 10, 10]),
            A=_js_action(pal),
            AA=Dictionary(E=_js_action(pal)),
        )
    )
    pal.pages[0].obj.Annots = Array([annot])
    return pal


@pytest.fixture
def pdf_with_external(pal):
    """A PDF with each external-access action subtype, plus a /Next chain."""
    subtypes = [
        Dictionary(S=Name.URI, URI=String('http://example.com')),
        Dictionary(S=Name.Launch, F=String('calc.exe')),
        Dictionary(S=Name.GoToR, F=String('other.pdf')),
        Dictionary(S=Name.SubmitForm, F=String('http://example.com/submit')),
        Dictionary(S=Name.ImportData, F=String('data.fdf')),
    ]
    annots = []
    for action in subtypes:
        annots.append(
            pal.make_indirect(
                Dictionary(
                    Type=Name.Annot,
                    Subtype=Name.Link,
                    Rect=Array([0, 0, 10, 10]),
                    A=pal.make_indirect(action),
                )
            )
        )
    pal.pages[0].obj.Annots = Array(annots)
    return pal


@pytest.fixture
def pdf_with_attachments(pal, resources):
    fs = AttachedFileSpec.from_filepath(pal, resources / 'rle.pdf')
    pal.attachments['rle.pdf'] = fs
    pal.Root.AF = Array([fs.obj])
    pal.pages[0].obj.AF = Array([fs.obj])
    annot = pal.make_indirect(
        Dictionary(
            Type=Name.Annot,
            Subtype=Name.FileAttachment,
            Rect=Array([0, 0, 10, 10]),
            FS=fs.obj,
        )
    )
    pal.pages[0].obj.Annots = Array([annot])
    return pal


# --- remove_javascript ---------------------------------------------------


def test_removes_named_javascript(pdf_with_js):
    remove_javascript(pdf_with_js)
    assert Name.JavaScript not in pdf_with_js.Root.Names


def test_removes_openaction_js(pdf_with_js):
    remove_javascript(pdf_with_js)
    assert Name.OpenAction not in pdf_with_js.Root


def test_removes_catalog_aa_js(pdf_with_js):
    remove_javascript(pdf_with_js)
    assert Name.AA not in pdf_with_js.Root


def test_removes_page_aa_js(pdf_with_js):
    remove_javascript(pdf_with_js)
    assert Name.AA not in pdf_with_js.pages[0].obj


def test_removes_annotation_a_and_aa_js(pdf_with_js):
    remove_javascript(pdf_with_js)
    annot = pdf_with_js.pages[0].obj.Annots[0]
    assert Name.A not in annot
    assert Name.AA not in annot


def test_preserves_nonjs_openaction(pal):
    pal.Root.OpenAction = pal.make_indirect(
        Dictionary(S=Name.GoTo, D=Array([pal.pages[0].obj, Name.Fit]))
    )
    remove_javascript(pal)
    assert pal.Root.OpenAction.S == Name.GoTo


def test_preserves_destination_array_openaction(pal):
    pal.Root.OpenAction = Array([pal.pages[0].obj, Name.Fit])
    remove_javascript(pal)
    assert isinstance(pal.Root.OpenAction, Array)


def test_javascript_idempotent(pdf_with_js):
    remove_javascript(pdf_with_js)
    remove_javascript(pdf_with_js)  # must not raise
    assert Name.JavaScript not in pdf_with_js.Root.Names


def test_javascript_noop_on_clean_pdf(pal):
    remove_javascript(pal)  # no Names, no actions: must not raise
    assert Name.OpenAction not in pal.Root


def test_javascript_visible_content_intact(pdf_with_js):
    before_pages = len(pdf_with_js.pages)
    before_box = list(pdf_with_js.pages[0].obj.MediaBox)
    remove_javascript(pdf_with_js)
    assert len(pdf_with_js.pages) == before_pages
    assert list(pdf_with_js.pages[0].obj.MediaBox) == before_box
    # Annotation is retained, only its scripts removed.
    assert len(pdf_with_js.pages[0].obj.Annots) == 1


def test_javascript_roundtrip(pdf_with_js, outpdf):
    remove_javascript(pdf_with_js)
    pdf_with_js.save(outpdf)
    with Pdf.open(outpdf) as out:
        assert Name.JavaScript not in out.Root.get(Name.Names, Dictionary())
        assert Name.OpenAction not in out.Root


# --- remove_external_access ----------------------------------------------


@pytest.mark.parametrize('index', range(5))
def test_removes_each_external_subtype(pdf_with_external, index):
    remove_external_access(pdf_with_external)
    annot = pdf_with_external.pages[0].obj.Annots[index]
    assert Name.A not in annot


def test_link_annotation_retained_action_removed(pdf_with_external):
    remove_external_access(pdf_with_external)
    annots = pdf_with_external.pages[0].obj.Annots
    assert len(annots) == 5
    for annot in annots:
        assert annot.Subtype == Name.Link
        assert Name.Rect in annot
        assert Name.A not in annot


def test_splices_next_chain_array(pal):
    benign = Dictionary(S=Name.GoTo, D=Array([pal.pages[0].obj, Name.Fit]))
    action = pal.make_indirect(
        Dictionary(
            S=Name.GoTo,
            D=Array([pal.pages[0].obj, Name.Fit]),
            Next=Array(
                [
                    Dictionary(S=Name.URI, URI=String('http://evil')),
                    benign,
                    Dictionary(S=Name.Launch, F=String('x')),
                ]
            ),
        )
    )
    annot = pal.make_indirect(Dictionary(Type=Name.Annot, Subtype=Name.Link, A=action))
    pal.pages[0].obj.Annots = Array([annot])

    remove_external_access(pal)

    surviving = annot.A.Next
    # Only the benign GoTo survives; it is the single remaining /Next node.
    assert surviving.S == Name.GoTo


def test_splices_next_chain_single(pal):
    survivor = Dictionary(S=Name.GoTo, D=Array([pal.pages[0].obj, Name.Fit]))
    action = pal.make_indirect(
        Dictionary(
            S=Name.GoTo,
            D=Array([pal.pages[0].obj, Name.Fit]),
            Next=Dictionary(
                S=Name.URI,
                URI=String('http://evil'),
                Next=survivor,
            ),
        )
    )
    annot = pal.make_indirect(Dictionary(Type=Name.Annot, Subtype=Name.Link, A=action))
    pal.pages[0].obj.Annots = Array([annot])

    remove_external_access(pal)

    # The URI node is spliced out and its survivor grafted up.
    assert annot.A.Next.S == Name.GoTo


def test_cyclic_next_guard(pal):
    a = pal.make_indirect(Dictionary(S=Name.GoTo))
    b = pal.make_indirect(Dictionary(S=Name.URI, URI=String('http://evil')))
    a.Next = b
    b.Next = a  # cycle
    annot = pal.make_indirect(Dictionary(Type=Name.Annot, Subtype=Name.Link, A=a))
    pal.pages[0].obj.Annots = Array([annot])

    remove_external_access(pal)  # must terminate, not hang or overflow


def test_external_idempotent(pdf_with_external):
    remove_external_access(pdf_with_external)
    remove_external_access(pdf_with_external)
    for annot in pdf_with_external.pages[0].obj.Annots:
        assert Name.A not in annot


def test_external_noop_on_clean_pdf(pal):
    remove_external_access(pal)


# --- remove_attachments --------------------------------------------------


def test_clears_embedded_files(pdf_with_attachments):
    remove_attachments(pdf_with_attachments)
    assert len(pdf_with_attachments.attachments) == 0
    assert Name.EmbeddedFiles not in pdf_with_attachments.Root.get(
        Name.Names, Dictionary()
    )


def test_removes_af_catalog_and_page(pdf_with_attachments):
    remove_attachments(pdf_with_attachments)
    assert Name.AF not in pdf_with_attachments.Root
    assert Name.AF not in pdf_with_attachments.pages[0].obj


def test_defangs_file_attachment_annot(pdf_with_attachments):
    remove_attachments(pdf_with_attachments)
    annot = pdf_with_attachments.pages[0].obj.Annots[0]
    assert annot.Subtype == Name.FileAttachment  # annotation retained
    assert Name.FS not in annot


def test_attachments_roundtrip(pdf_with_attachments, outpdf):
    remove_attachments(pdf_with_attachments)
    pdf_with_attachments.save(outpdf)
    with Pdf.open(outpdf) as out:
        assert not out.attachments._has_embedded_files


def test_attachments_idempotent(pdf_with_attachments):
    remove_attachments(pdf_with_attachments)
    remove_attachments(pdf_with_attachments)
    assert len(pdf_with_attachments.attachments) == 0


def test_attachments_noop_on_clean_pdf(pal):
    remove_attachments(pal)
    assert len(pal.attachments) == 0


# --- remove_thumbnails ---------------------------------------------------


@pytest.fixture
def pdf_with_thumbnails(pal):
    for page in pal.pages:
        page.obj.Thumb = pal.make_stream(b'fake thumbnail data')
    return pal


def test_removes_thumbnails(pdf_with_thumbnails):
    remove_thumbnails(pdf_with_thumbnails)
    for page in pdf_with_thumbnails.pages:
        assert Name.Thumb not in page.obj


def test_thumbnails_roundtrip(pdf_with_thumbnails, outpdf):
    remove_thumbnails(pdf_with_thumbnails)
    pdf_with_thumbnails.save(outpdf)
    with Pdf.open(outpdf) as out:
        assert all(Name.Thumb not in page.obj for page in out.pages)


def test_thumbnails_idempotent_and_noop(pal):
    remove_thumbnails(pal)  # no thumbnails: must not raise
    remove_thumbnails(pal)
    assert Name.Thumb not in pal.pages[0].obj


# --- remove_search_index -------------------------------------------------


def test_removes_search_index(pal):
    pal.Root.PieceInfo = Dictionary(SearchIndex=Dictionary(ModID=String('abc')))
    remove_search_index(pal)
    assert Name.PieceInfo not in pal.Root


def test_search_index_preserves_other_pieceinfo(pal):
    pal.Root.PieceInfo = Dictionary(
        SearchIndex=Dictionary(ModID=String('abc')),
        SomeApp=Dictionary(LastModified=String('D:20240101')),
    )
    remove_search_index(pal)
    assert Name.PieceInfo in pal.Root
    assert Name.SearchIndex not in pal.Root.PieceInfo
    assert Name.SomeApp in pal.Root.PieceInfo


def test_search_index_idempotent_and_noop(pal):
    remove_search_index(pal)  # no PieceInfo: must not raise
    pal.Root.PieceInfo = Dictionary(SearchIndex=Dictionary())
    remove_search_index(pal)
    remove_search_index(pal)
    assert Name.PieceInfo not in pal.Root


# --- Sanitizer (fluent builder) ------------------------------------------


def test_sanitizer_chaining_returns_self():
    s = Sanitizer()
    assert s.remove_javascript() is s
    assert s.remove_external_access() is s
    assert s.remove_attachments() is s
    assert s.remove_thumbnails() is s
    assert s.remove_search_index() is s


def test_sanitizer_apply_returns_pdf(pal):
    out = Sanitizer().remove_javascript().apply(pal)
    assert out is pal


def test_sanitizer_combined_operations(pdf_with_js, resources):
    pdf = pdf_with_js
    fs = AttachedFileSpec.from_filepath(pdf, resources / 'rle.pdf')
    pdf.attachments['rle.pdf'] = fs
    pdf.pages[0].obj.Thumb = pdf.make_stream(b'thumb')
    pdf.pages[0].obj.Annots.append(
        pdf.make_indirect(
            Dictionary(
                Type=Name.Annot,
                Subtype=Name.Link,
                Rect=Array([0, 0, 10, 10]),
                A=Dictionary(S=Name.URI, URI=String('http://evil')),
            )
        )
    )

    (
        Sanitizer()
        .remove_javascript()
        .remove_external_access()
        .remove_attachments()
        .remove_thumbnails()
        .apply(pdf)
    )

    assert Name.JavaScript not in pdf.Root.Names
    assert len(pdf.attachments) == 0
    assert Name.Thumb not in pdf.pages[0].obj
    for annot in pdf.pages[0].obj.Annots:
        assert Name.A not in annot


def test_sanitizer_reusable_across_pdfs(resources):
    scrubber = Sanitizer().remove_javascript().remove_thumbnails()
    for _ in range(2):
        with Pdf.open(resources / 'pal.pdf') as pdf:
            nt = pikepdf.NameTree.new(pdf)
            nt['evil'] = _js_action(pdf)
            pdf.Root.Names = Dictionary(JavaScript=nt.obj)
            pdf.pages[0].obj.Thumb = pdf.make_stream(b'thumb')

            scrubber.apply(pdf)

            assert Name.JavaScript not in pdf.Root.Names
            assert Name.Thumb not in pdf.pages[0].obj


def test_sanitizer_matches_freefunctions(pdf_with_external):
    # The combined single-traversal must match calling the free functions.
    builder_result = (
        Sanitizer()
        .remove_javascript()
        .remove_external_access()
        .apply(pdf_with_external)
    )
    for annot in builder_result.pages[0].obj.Annots:
        assert Name.A not in annot


def test_sanitizer_empty_is_noop(pal):
    before = len(pal.pages)
    Sanitizer().apply(pal)
    assert len(pal.pages) == before


# --- cross-cutting -------------------------------------------------------


def test_all_three_any_order(pdf_with_js, resources):
    pdf = pdf_with_js
    fs = AttachedFileSpec.from_filepath(pdf, resources / 'rle.pdf')
    pdf.attachments['rle.pdf'] = fs
    pdf.pages[0].obj.Annots.append(
        pdf.make_indirect(
            Dictionary(
                Type=Name.Annot,
                Subtype=Name.Link,
                Rect=Array([0, 0, 10, 10]),
                A=Dictionary(S=Name.URI, URI=String('http://evil')),
            )
        )
    )

    remove_external_access(pdf)
    remove_attachments(pdf)
    remove_javascript(pdf)

    assert len(pdf.attachments) == 0
    assert Name.JavaScript not in pdf.Root.Names
    for annot in pdf.pages[0].obj.Annots:
        assert Name.A not in annot


def test_functions_return_none(pal):
    assert remove_javascript(pal) is None
    assert remove_attachments(pal) is None
    assert remove_external_access(pal) is None
    assert remove_thumbnails(pal) is None
    assert remove_search_index(pal) is None


def test_public_api_exports():
    assert 'sanitize' in pikepdf.__all__
    assert pikepdf.sanitize.remove_javascript is remove_javascript
    assert set(pikepdf.sanitize.__all__) == {
        'Sanitizer',
        'remove_attachments',
        'remove_external_access',
        'remove_javascript',
        'remove_search_index',
        'remove_thumbnails',
    }
