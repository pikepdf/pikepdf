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
    remove_collection,
    remove_external_access,
    remove_javascript,
    remove_multimedia,
    remove_private_app_data,
    remove_search_index,
    remove_thumbnails,
    remove_web_capture,
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


# The pdf_with_js fixture injects a bare /Widget annotation with no /AcroForm,
# so saving it legitimately raises PageCopyWarning about the orphaned widget.
@pytest.mark.filterwarnings("ignore::pikepdf.PageCopyWarning")
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


def test_removes_gotoe_embedded_action(pal):
    annot = pal.make_indirect(
        Dictionary(
            Type=Name.Annot,
            Subtype=Name.Link,
            Rect=Array([0, 0, 10, 10]),
            A=pal.make_indirect(Dictionary(S=Name.GoToE, F=String('embedded.pdf'))),
        )
    )
    pal.pages[0].obj.Annots = Array([annot])
    remove_external_access(pal)
    assert Name.A not in annot


def test_external_idempotent(pdf_with_external):
    remove_external_access(pdf_with_external)
    remove_external_access(pdf_with_external)
    for annot in pdf_with_external.pages[0].obj.Annots:
        assert Name.A not in annot


def test_external_noop_on_clean_pdf(pal):
    remove_external_access(pal)


# --- outline (bookmark) actions ------------------------------------------


def _outline_item(pdf, action, title='item'):
    return pdf.make_indirect(Dictionary(Title=String(title), A=action))


def _install_outline(pdf, *items):
    outlines = pdf.make_indirect(
        Dictionary(Type=Name.Outlines, First=items[0], Last=items[-1], Count=len(items))
    )
    for i, item in enumerate(items):
        item.Parent = outlines
        if i > 0:
            item.Prev = items[i - 1]
        if i < len(items) - 1:
            item.Next = items[i + 1]
    pdf.Root.Outlines = outlines
    return outlines


def test_removes_javascript_from_outline_item(pal):
    item = _outline_item(pal, _js_action(pal))
    _install_outline(pal, item)
    remove_javascript(pal)
    assert Name.A not in item


def test_removes_external_access_from_outline_item(pal):
    item = _outline_item(pal, Dictionary(S=Name.URI, URI=String('http://evil')))
    _install_outline(pal, item)
    remove_external_access(pal)
    assert Name.A not in item


def test_outline_traverses_siblings_and_children(pal):
    sibling = _outline_item(pal, _js_action(pal), 'sibling')
    child = _outline_item(pal, _js_action(pal), 'child')
    first = _outline_item(pal, _js_action(pal), 'first')
    _install_outline(pal, first, sibling)
    # Give the first item a child.
    first.First = child
    first.Last = child
    child.Parent = first
    remove_javascript(pal)
    assert Name.A not in first
    assert Name.A not in sibling
    assert Name.A not in child


def test_outline_preserves_dest_only_item(pal):
    item = pal.make_indirect(
        Dictionary(Title=String('x'), Dest=Array([pal.pages[0].obj, Name.Fit]))
    )
    _install_outline(pal, item)
    remove_javascript(pal)
    assert Name.Dest in item


def test_outline_cyclic_guard(pal):
    a = _outline_item(pal, _js_action(pal), 'a')
    b = _outline_item(pal, _js_action(pal), 'b')
    _install_outline(pal, a, b)
    b.Next = a  # cycle back
    remove_javascript(pal)  # must terminate
    assert Name.A not in a
    assert Name.A not in b


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


def test_removes_af_from_xobject(pdf_with_attachments):
    pdf = pdf_with_attachments
    fs = pdf.pages[0].obj.AF[0]  # reuse the existing file spec
    xobj = pdf.make_indirect(
        Dictionary(Type=Name.XObject, Subtype=Name.Form, AF=Array([fs]))
    )
    pdf.pages[0].obj.Resources = Dictionary(XObject=Dictionary(Fm0=xobj))
    remove_attachments(pdf)
    assert Name.AF not in xobj


def test_removes_af_from_structure_element(pdf_with_attachments):
    pdf = pdf_with_attachments
    fs = pdf.pages[0].obj.AF[0]
    elem = pdf.make_indirect(Dictionary(Type=Name.StructElem, S=Name.P, AF=Array([fs])))
    pdf.Root.StructTreeRoot = pdf.make_indirect(
        Dictionary(Type=Name.StructTreeRoot, K=elem)
    )
    remove_attachments(pdf)
    assert Name.AF not in elem


def test_preserves_unrelated_af_key(pal):
    # An /AF key whose value is not an embedded-file specification must be left
    # alone: it is not an associated-files reference.
    obj = pal.make_indirect(Dictionary(AF=String('innocent value')))
    pal.Root.SomeKey = obj
    remove_attachments(pal)
    assert Name.AF in obj


def test_preserves_external_associated_file_without_ef(pal):
    # An associated file that references an external file (no embedded /EF
    # payload) carries no embedded bytes, so it is preserved.
    spec = pal.make_indirect(Dictionary(Type=Name.Filespec, F=String('external.txt')))
    obj = pal.make_indirect(Dictionary(AF=Array([spec])))
    pal.Root.SomeKey = obj
    remove_attachments(pal)
    assert Name.AF in obj


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


# --- remove_multimedia ---------------------------------------------------


@pytest.fixture
def pdf_with_multimedia(pal):
    """A PDF with multimedia annotations, a rendition action, and named
    renditions."""
    screen = pal.make_indirect(
        Dictionary(
            Type=Name.Annot,
            Subtype=Name.Screen,
            Rect=Array([0, 0, 10, 10]),
            A=pal.make_indirect(Dictionary(S=Name.Rendition)),
        )
    )
    movie = pal.make_indirect(
        Dictionary(
            Type=Name.Annot,
            Subtype=Name.Movie,
            Rect=Array([0, 0, 10, 10]),
            Movie=Dictionary(F=String('movie.avi')),
        )
    )
    sound = pal.make_indirect(
        Dictionary(
            Type=Name.Annot,
            Subtype=Name.Sound,
            Rect=Array([0, 0, 10, 10]),
            Sound=pal.make_stream(b'sounddata'),
        )
    )
    richmedia = pal.make_indirect(
        Dictionary(
            Type=Name.Annot,
            Subtype=Name.RichMedia,
            Rect=Array([0, 0, 10, 10]),
            RichMediaContent=Dictionary(),
            RichMediaSettings=Dictionary(),
        )
    )
    three_d = pal.make_indirect(
        Dictionary(Type=Name.Annot, Subtype=Name('/3D'), Rect=Array([0, 0, 10, 10]))
    )
    three_d[Name('/3DD')] = pal.make_stream(b'3ddata')
    pal.pages[0].obj.Annots = Array([screen, movie, sound, richmedia, three_d])

    nt = pikepdf.NameTree.new(pal)
    nt['clip'] = pal.make_indirect(Dictionary(S=Name.Rendition))
    pal.Root.Names = Dictionary(Renditions=nt.obj)
    return pal


def test_removes_rendition_action(pdf_with_multimedia):
    remove_multimedia(pdf_with_multimedia)
    screen = pdf_with_multimedia.pages[0].obj.Annots[0]
    assert screen.Subtype == Name.Screen  # annotation retained
    assert Name.A not in screen


def test_defangs_movie_annotation(pdf_with_multimedia):
    remove_multimedia(pdf_with_multimedia)
    movie = pdf_with_multimedia.pages[0].obj.Annots[1]
    assert movie.Subtype == Name.Movie
    assert Name.Movie not in movie


def test_defangs_sound_annotation(pdf_with_multimedia):
    remove_multimedia(pdf_with_multimedia)
    sound = pdf_with_multimedia.pages[0].obj.Annots[2]
    assert sound.Subtype == Name.Sound
    assert Name.Sound not in sound


def test_defangs_richmedia_annotation(pdf_with_multimedia):
    remove_multimedia(pdf_with_multimedia)
    rm = pdf_with_multimedia.pages[0].obj.Annots[3]
    assert rm.Subtype == Name.RichMedia
    assert Name.RichMediaContent not in rm
    assert Name.RichMediaSettings not in rm


def test_defangs_3d_annotation(pdf_with_multimedia):
    remove_multimedia(pdf_with_multimedia)
    three_d = pdf_with_multimedia.pages[0].obj.Annots[4]
    assert three_d.Subtype == Name('/3D')
    assert Name('/3DD') not in three_d


def test_removes_named_renditions(pdf_with_multimedia):
    remove_multimedia(pdf_with_multimedia)
    assert Name.Renditions not in pdf_with_multimedia.Root.get(Name.Names, Dictionary())


def test_removes_richmediaexecute_action(pal):
    annot = pal.make_indirect(
        Dictionary(
            Type=Name.Annot,
            Subtype=Name.RichMedia,
            Rect=Array([0, 0, 10, 10]),
            A=pal.make_indirect(Dictionary(S=Name.RichMediaExecute)),
        )
    )
    pal.pages[0].obj.Annots = Array([annot])
    remove_multimedia(pal)
    assert Name.A not in annot


def test_multimedia_idempotent_and_noop(pal):
    remove_multimedia(pal)  # clean PDF: must not raise
    remove_multimedia(pal)


# --- remove_web_capture --------------------------------------------------


def test_removes_web_capture(pal):
    pal.Root.SpiderInfo = Dictionary(V=String('1.0'))
    remove_web_capture(pal)
    assert Name.SpiderInfo not in pal.Root


def test_web_capture_noop(pal):
    remove_web_capture(pal)  # no SpiderInfo: must not raise
    assert Name.SpiderInfo not in pal.Root


# --- remove_private_app_data ---------------------------------------------


def test_private_app_data_removes_catalog_pieceinfo(pal):
    pal.Root.PieceInfo = Dictionary(SomeApp=Dictionary(Private=String('x')))
    remove_private_app_data(pal)
    assert Name.PieceInfo not in pal.Root


def test_private_app_data_removes_page_pieceinfo(pal):
    pal.pages[0].obj.PieceInfo = Dictionary(SomeApp=Dictionary(Private=String('x')))
    remove_private_app_data(pal)
    assert Name.PieceInfo not in pal.pages[0].obj


def test_private_app_data_subsumes_search_index(pal):
    pal.Root.PieceInfo = Dictionary(SearchIndex=Dictionary(ModID=String('abc')))
    remove_private_app_data(pal)
    assert Name.PieceInfo not in pal.Root


def test_private_app_data_noop(pal):
    remove_private_app_data(pal)  # no PieceInfo anywhere: must not raise
    assert Name.PieceInfo not in pal.Root


# --- remove_collection ---------------------------------------------------


def test_removes_collection(pal):
    pal.Root.Collection = Dictionary(View=Name.D)
    remove_collection(pal)
    assert Name.Collection not in pal.Root


def test_collection_noop(pal):
    remove_collection(pal)  # no Collection: must not raise
    assert Name.Collection not in pal.Root


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
    assert s.remove_multimedia() is s
    assert s.remove_web_capture() is s
    assert s.remove_private_app_data() is s
    assert s.remove_collection() is s


def test_sanitizer_applies_multimedia(pdf_with_multimedia):
    Sanitizer().remove_multimedia().apply(pdf_with_multimedia)
    movie = pdf_with_multimedia.pages[0].obj.Annots[1]
    assert Name.Movie not in movie
    assert Name.A not in pdf_with_multimedia.pages[0].obj.Annots[0]


def test_sanitizer_applies_new_structural(pal):
    pal.Root.SpiderInfo = Dictionary(V=String('1.0'))
    pal.Root.PieceInfo = Dictionary(SomeApp=Dictionary())
    pal.Root.Collection = Dictionary(View=Name.D)
    (
        Sanitizer()
        .remove_web_capture()
        .remove_private_app_data()
        .remove_collection()
        .apply(pal)
    )
    assert Name.SpiderInfo not in pal.Root
    assert Name.PieceInfo not in pal.Root
    assert Name.Collection not in pal.Root


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
    assert remove_multimedia(pal) is None
    assert remove_web_capture(pal) is None
    assert remove_private_app_data(pal) is None
    assert remove_collection(pal) is None


def test_public_api_exports():
    assert 'sanitize' in pikepdf.__all__
    assert pikepdf.sanitize.remove_javascript is remove_javascript
    assert set(pikepdf.sanitize.__all__) == {
        'Sanitizer',
        'remove_attachments',
        'remove_collection',
        'remove_external_access',
        'remove_javascript',
        'remove_multimedia',
        'remove_private_app_data',
        'remove_search_index',
        'remove_thumbnails',
        'remove_web_capture',
    }
