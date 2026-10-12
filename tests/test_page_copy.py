# SPDX-FileCopyrightText: 2026 James R. Barlow
# SPDX-License-Identifier: MPL-2.0
from __future__ import annotations

import io
import os
import tempfile
import warnings
from pathlib import Path

import pytest

import pikepdf
from pikepdf import (
    Array,
    Dictionary,
    Job,
    Name,
    NameTree,
    PageCopyResult,
    PageCopyWarning,
    Pdf,
    String,
)
from pikepdf._page_copy import _collect_named_dest_refs


def test_pagecopywarning_is_userwarning():
    assert issubclass(PageCopyWarning, UserWarning)
    assert pikepdf.exceptions.PageCopyWarning is PageCopyWarning


def test_pagecopyresult_defaults():
    r = PageCopyResult(pages_added=3, forms='preserve')
    assert r.pages_added == 3
    assert r.forms == 'preserve'
    assert r.fields_added == 0
    assert r.renamed_fields == {}
    assert r.partial_fields == []


def _resources():
    return Path(__file__).parent / 'resources'


def test_add_pages_from_matches_job_field_structure():
    res = _resources()
    f1, f2 = str(res / 'form.pdf'), str(res / 'form_dd0293.pdf')

    out = tempfile.mktemp(suffix='.pdf')
    Job(['pikepdf', '--empty', '--pages', f1, f2, '--', out]).run()
    with Pdf.open(out) as j:
        job_terminal = len(j.acroform.fields)
        job_toplevel = len(j.Root.AcroForm.Fields)
    os.unlink(out)

    pdf = Pdf.new()
    with Pdf.open(f1) as s1, Pdf.open(f2) as s2:
        r1 = pdf.add_pages_from(s1)
        r2 = pdf.add_pages_from(s2)

    assert r1.forms == 'preserve'
    assert r1.pages_added == 1
    assert r2.pages_added == 4
    assert pdf.acroform.exists
    assert len(pdf.acroform.fields) == job_terminal
    assert len(pdf.Root.AcroForm.Fields) == job_toplevel
    assert r1.fields_added == 5  # form.pdf has 5 terminal fields


def test_add_pages_from_reports_renames_on_collision():
    res = _resources()
    f1 = str(res / 'form.pdf')

    pdf = Pdf.new()
    with Pdf.open(f1) as s1:
        pdf.add_pages_from(s1)  # first copy: names land as-is
    with Pdf.open(f1) as s2:
        result = pdf.add_pages_from(s2)  # second copy: every name collides

    # form.pdf's terminal field 'Text1' exists from the first copy, so the
    # second copy must rename it to something else.
    assert 'Text1' in result.renamed_fields
    new_name = result.renamed_fields['Text1']
    assert new_name != 'Text1'
    # The renamed field is actually reachable under its new name.
    assert pdf.acroform.get_fields_with_qualified_name(new_name)
    # Original is still reachable too (the first copy's field).
    assert pdf.acroform.get_fields_with_qualified_name('Text1')


def _two_page_shared_field_pdf():
    pdf = Pdf.new()
    pdf.add_blank_page(page_size=(300, 300))
    pdf.add_blank_page(page_size=(300, 300))
    # One field 'Shared' with two widget kids, one per page.
    field = pdf.make_indirect(
        Dictionary(FT=Name.Tx, T=String('Shared'), V=String('x'), Kids=Array([]))
    )
    kids = []
    for p in pdf.pages:
        w = pdf.make_indirect(
            Dictionary(
                Type=Name.Annot,
                Subtype=Name.Widget,
                Parent=field,
                Rect=Array([0, 0, 100, 20]),
            )
        )
        kids.append(w)
        p.Annots = Array([w])
    field.Kids = Array(kids)
    pdf.Root.AcroForm = pdf.make_indirect(
        Dictionary(Fields=Array([field]), NeedAppearances=True)
    )
    return pdf


def test_add_pages_from_reports_partial_fields():
    src = _two_page_shared_field_pdf()
    dest = Pdf.new()
    result = dest.add_pages_from(src, pages=[0])  # copy only page 0
    assert 'Shared' in result.partial_fields


def test_add_pages_from_full_copy_has_no_partial_fields():
    src = _two_page_shared_field_pdf()
    dest = Pdf.new()
    result = dest.add_pages_from(src)  # all pages
    assert result.partial_fields == []


def _three_level_shared_field_pdf():
    """3-level hierarchy: Root -> Mid -> Leaf+widgets, one widget per page."""
    pdf = Pdf.new()
    pdf.add_blank_page(page_size=(300, 300))
    pdf.add_blank_page(page_size=(300, 300))

    root = pdf.make_indirect(Dictionary(FT=Name.Tx, T=String('Root'), Kids=Array([])))
    intermediate = pdf.make_indirect(
        Dictionary(T=String('Mid'), Parent=root, Kids=Array([]))
    )
    terminal = pdf.make_indirect(
        Dictionary(T=String('Leaf'), Parent=intermediate, Kids=Array([]))
    )
    root.Kids = Array([intermediate])
    intermediate.Kids = Array([terminal])

    widgets = []
    for p in pdf.pages:
        w = pdf.make_indirect(
            Dictionary(
                Type=Name.Annot,
                Subtype=Name.Widget,
                Parent=terminal,
                Rect=Array([0, 0, 100, 20]),
            )
        )
        widgets.append(w)
        p.Annots = Array([w])
    terminal.Kids = Array(widgets)

    pdf.Root.AcroForm = pdf.make_indirect(
        Dictionary(Fields=Array([root]), NeedAppearances=True)
    )
    return pdf


def test_add_pages_from_reports_partial_fields_three_level():
    """3-level field hierarchy: partial detection must key on top-level FQN."""
    src = _three_level_shared_field_pdf()
    dest = Pdf.new()
    result = dest.add_pages_from(src, pages=[0])  # copy only page 0
    assert 'Root' in result.partial_fields


def _count_widgets(pdf):
    total = 0
    for p in pdf.pages:
        if Name.Annots in p.obj:
            total += sum(1 for a in p.obj.Annots if a.get(Name.Subtype) == Name.Widget)
    return total


def test_add_pages_from_strip_removes_widgets():
    res = _resources()
    f2 = str(res / 'form_dd0293.pdf')
    dest = Pdf.new()
    with Pdf.open(f2) as src:
        assert _count_widgets(src) > 0
        result = dest.add_pages_from(src, forms='strip')
    assert result.forms == 'strip'
    assert result.fields_added == 0
    assert _count_widgets(dest) == 0
    assert not dest.acroform.exists


def test_add_pages_from_strip_preserves_non_widget_annotations():
    src = Pdf.new()
    src.add_blank_page(page_size=(300, 300))
    page = src.pages[0]

    widget = src.make_indirect(
        Dictionary(
            Type=Name.Annot,
            Subtype=Name.Widget,
            FT=Name.Tx,
            T=String('w'),
            Rect=Array([0, 0, 100, 20]),
        )
    )
    link = src.make_indirect(
        Dictionary(
            Type=Name.Annot,
            Subtype=Name.Link,
            Rect=Array([0, 30, 100, 50]),
        )
    )
    page.Annots = Array([widget, link])
    src.Root.AcroForm = src.make_indirect(Dictionary(Fields=Array([widget])))

    dest = Pdf.new()
    dest.add_pages_from(src, forms='strip')

    dest_page = dest.pages[0]
    assert Name.Annots in dest_page.obj, 'Link annotation must survive strip'
    annots = list(dest_page.obj.Annots)
    subtypes = [a.get(Name.Subtype) for a in annots]
    assert Name.Link in subtypes, 'Link annotation must be preserved'
    assert _count_widgets(dest) == 0, 'Widget annotations must be removed'
    assert len(annots) == 1, 'Exactly one annotation (Link) must remain'


def test_extend_warns_cross_document_form_pages():
    res = _resources()
    dest = Pdf.new()
    with Pdf.open(str(res / 'form.pdf')) as src:
        with pytest.warns(PageCopyWarning):
            dest.pages.extend(src.pages)


def test_extend_warns_named_destination_pages():
    dest = Pdf.new()
    with _pdf_with_named_dest_links() as src:
        with pytest.warns(PageCopyWarning, match="named destination"):
            dest.pages.extend(src.pages)


def test_extend_no_warning_for_formless_pages():
    src = Pdf.new()
    src.add_blank_page(page_size=(200, 200))
    dest = Pdf.new()
    with warnings.catch_warnings():
        warnings.simplefilter('error', PageCopyWarning)
        dest.pages.extend(src.pages)  # must not raise


def test_extend_warning_can_be_promoted_to_error():
    """A filter that turns PageCopyWarning into an error must raise it.

    The warning is emitted from C++, where a swallowed error indicator would let
    the copy proceed as if nothing had happened.
    """
    res = _resources()
    dest = Pdf.new()
    with Pdf.open(str(res / 'form.pdf')) as src:
        with warnings.catch_warnings():
            warnings.simplefilter('error', PageCopyWarning)
            with pytest.raises(PageCopyWarning):
                dest.pages.extend(src.pages)


def test_extend_no_warning_intra_document():
    res = _resources()
    with Pdf.open(str(res / 'form.pdf')) as pdf:
        with warnings.catch_warnings():
            warnings.simplefilter('error', PageCopyWarning)
            pdf.pages.extend(pdf.pages)  # same document: no warning


def test_save_warns_on_orphaned_widgets():
    # Naive extend produces orphaned widgets (no /AcroForm).
    res = _resources()
    dest = Pdf.new()
    with Pdf.open(str(res / 'form.pdf')) as src:
        with warnings.catch_warnings():
            warnings.simplefilter('ignore', PageCopyWarning)  # silence extend warning
            dest.pages.extend(src.pages)
    assert dest._count_orphaned_widgets() > 0
    with pytest.warns(PageCopyWarning):
        dest.save(io.BytesIO())


def test_save_no_warning_for_clean_merge():
    res = _resources()
    dest = Pdf.new()
    with Pdf.open(str(res / 'form.pdf')) as src:
        dest.add_pages_from(src)  # preserves forms -> no orphans
    assert dest._count_orphaned_widgets() == 0
    with warnings.catch_warnings():
        warnings.simplefilter('error', PageCopyWarning)
        dest.save(io.BytesIO())


def test_save_no_warning_for_formless_doc():
    pdf = Pdf.new()
    pdf.add_blank_page(page_size=(200, 200))
    assert pdf._count_orphaned_widgets() == 0
    with warnings.catch_warnings():
        warnings.simplefilter('error', PageCopyWarning)
        pdf.save(io.BytesIO())


def test_add_pages_from_preserve_emits_no_formcopywarning():
    res = _resources()
    dest = Pdf.new()
    with Pdf.open(str(res / 'form.pdf')) as src:
        with warnings.catch_warnings():
            warnings.simplefilter('error', PageCopyWarning)
            dest.add_pages_from(src)  # must not raise PageCopyWarning


def test_collect_named_dest_refs_dest_and_action():
    pdf = Pdf.new()
    page = pdf.add_blank_page(page_size=(200, 200))
    # /Dest string on a Link, /A GoTo /D name, an explicit (array) dest (ignored),
    # a /Next chain, and an /AA sub-action.
    link_dest = Dictionary(Type=Name.Annot, Subtype=Name.Link, Dest=String('alpha'))
    next_action = Dictionary(S=Name.GoTo, D=String('beta'))
    link_action = Dictionary(
        Type=Name.Annot,
        Subtype=Name.Link,
        A=Dictionary(S=Name.GoTo, D=Name('/gamma'), Next=next_action),
    )
    explicit = Dictionary(
        Type=Name.Annot, Subtype=Name.Link, Dest=Array([page.obj, Name.Fit])
    )
    aa_annot = Dictionary(
        Type=Name.Annot,
        Subtype=Name.Widget,
        AA=Dictionary(U=Dictionary(S=Name.GoTo, D=String('delta'))),
    )
    page.obj.Annots = pdf.make_indirect(
        Array([link_dest, link_action, explicit, aa_annot])
    )

    refs = _collect_named_dest_refs(page.obj)
    found = {(r.kind, r.name) for r in refs}
    assert found == {
        ('string', 'alpha'),
        ('name', '/gamma'),
        ('string', 'beta'),
        ('string', 'delta'),
    }
    # explicit (array) destination is not collected
    assert ('string', 'page') not in found


def test_collect_named_dest_refs_ignores_gotor_action():
    # A GoToR action's /D targets a page in another document, not this one's
    # named-destination tree, and must not be collected for migration -- even
    # though it also carries a /D like GoTo does.
    pdf = Pdf.new()
    page = pdf.add_blank_page(page_size=(200, 200))
    link = Dictionary(
        Type=Name.Annot,
        Subtype=Name.Link,
        A=Dictionary(S=Name.GoToR, F=String('other.pdf'), D=String('epsilon')),
    )
    page.obj.Annots = pdf.make_indirect(Array([link]))

    refs = _collect_named_dest_refs(page.obj)
    assert ('string', 'epsilon') not in {(r.kind, r.name) for r in refs}


def _pdf_with_named_dest_links():
    """2-page PDF with two named destinations and cross-links.

    - ``sec.1`` (Names.Dests, string-keyed) targets page 0; page 1 has a
      Link annotation that GoTo-navigates to it.
    - ``sec.2`` (Names.Dests, string-keyed) targets page 1; page 0 has a
      Link annotation that GoTo-navigates to it.
    """
    pdf = Pdf.new()
    p0 = pdf.add_blank_page(page_size=(200, 200))
    p1 = pdf.add_blank_page(page_size=(200, 200))
    nt = NameTree.new(pdf)
    pdf.Root.Names = pdf.make_indirect(Dictionary(Dests=nt.obj))
    nt2 = NameTree(pdf.Root.Names.Dests)
    nt2['sec.1'] = pdf.make_indirect(Dictionary(D=Array([p0.obj, Name.XYZ, 0, 200, 0])))
    nt2['sec.2'] = pdf.make_indirect(Dictionary(D=Array([p1.obj, Name.XYZ, 0, 200, 0])))
    p0.obj.Annots = pdf.make_indirect(
        Array(
            [
                Dictionary(
                    Type=Name.Annot,
                    Subtype=Name.Link,
                    Rect=Array([0, 0, 50, 50]),
                    A=Dictionary(S=Name.GoTo, D=String('sec.2')),
                )
            ]
        )
    )
    p1.obj.Annots = pdf.make_indirect(
        Array(
            [
                Dictionary(
                    Type=Name.Annot,
                    Subtype=Name.Link,
                    Rect=Array([0, 0, 50, 50]),
                    A=Dictionary(S=Name.GoTo, D=String('sec.1')),
                )
            ]
        )
    )
    return pdf


def _resolves(pdf, name):
    if Name.Names not in pdf.Root or Name.Dests not in pdf.Root.Names:
        return False
    return name in NameTree(pdf.Root.Names.Dests)


def test_add_pages_from_migrates_named_destinations():
    # Destination has its own (unrelated) pages; mirrors #148 'no_links first' order.
    dest = Pdf.new()
    dest.add_blank_page(page_size=(200, 200))
    with _pdf_with_named_dest_links() as src:
        result = dest.add_pages_from(src)
    assert result.named_dests_added == 2
    assert _resolves(dest, 'sec.1')
    assert _resolves(dest, 'sec.2')
    # the copied link still references the (now-present) named destination
    copied_link = dest.pages[1].obj.Annots[0]
    assert str(copied_link.A.D) == 'sec.2'


def test_pagecopyresult_dest_defaults():
    r = PageCopyResult(pages_added=1, forms='preserve')
    assert r.named_dests_added == 0
    assert r.renamed_dests == {}
    assert r.dropped_dests == []


def test_migrated_named_dest_survives_save():
    dest = Pdf.new()
    dest.add_blank_page(page_size=(200, 200))
    with _pdf_with_named_dest_links() as src:
        dest.add_pages_from(src)
    buf = io.BytesIO()
    dest.save(buf)
    with Pdf.open(io.BytesIO(buf.getvalue())) as out:
        assert _resolves(out, 'sec.2')
        # no duplicate page was created (1 original + 2 copied)
        assert len(out.pages) == 3


def test_add_pages_from_drops_dest_to_noncopied_page():
    # page 0's link targets 'sec.2' -> page 1; copy ONLY page 0.
    dest = Pdf.new()
    with _pdf_with_named_dest_links() as src:
        result = dest.add_pages_from(src, [0])
    assert result.dropped_dests == ['sec.2']
    assert result.named_dests_added == 0
    # only the one selected page was added; no orphan target page pulled in
    assert len(dest.pages) == 1
    # the reference is left intact (dangling), unchanged
    assert str(dest.pages[0].obj.Annots[0].A.D) == 'sec.2'


def test_add_pages_from_renames_colliding_named_dest():
    dest = Pdf.new()
    dp = dest.add_blank_page(page_size=(200, 200))
    # destination already owns 'sec.2' pointing at its own page
    dnt = NameTree.new(dest)
    dest.Root.Names = dest.make_indirect(Dictionary(Dests=dnt.obj))
    NameTree(dest.Root.Names.Dests)['sec.2'] = dest.make_indirect(
        Dictionary(D=Array([dp.obj, Name.Fit]))
    )

    with _pdf_with_named_dest_links() as src:
        result = dest.add_pages_from(src)

    assert result.renamed_dests.get('sec.2') == 'sec.2.1'
    nt = NameTree(dest.Root.Names.Dests)
    assert 'sec.2' in nt and 'sec.2.1' in nt  # original preserved, migrated added
    # copied link rewritten to the new name (p0 → dest.pages[1], the first copied page)
    assert str(dest.pages[1].obj.Annots[0].A.D) == 'sec.2.1'


def _pdf_with_legacy_dests():
    pdf = Pdf.new()
    p0 = pdf.add_blank_page(page_size=(200, 200))
    p1 = pdf.add_blank_page(page_size=(200, 200))
    pdf.Root.Dests = pdf.make_indirect(Dictionary())
    pdf.Root.Dests[Name.Chap1] = pdf.make_indirect(
        Dictionary(D=Array([p1.obj, Name.Fit]))
    )
    p0.obj.Annots = pdf.make_indirect(
        Array(
            [
                Dictionary(
                    Type=Name.Annot,
                    Subtype=Name.Link,
                    Rect=Array([0, 0, 50, 50]),
                    Dest=Name.Chap1,
                )
            ]
        )
    )
    return pdf


def test_add_pages_from_migrates_legacy_name_dests():
    dest = Pdf.new()
    dest.add_blank_page(page_size=(200, 200))
    with _pdf_with_legacy_dests() as src:
        result = dest.add_pages_from(src)
    assert result.named_dests_added == 1
    assert Name.Chap1 in dest.Root.Dests
    # name-keyed reference resolves into Root.Dests, NOT the Names tree
    assert Name.Names not in dest.Root or Name.Dests not in dest.Root.get(Name.Names)


_EMPTY_NAME_LINK_PDF = b"""%PDF-1.7
1 0 obj << /Type /Catalog /Pages 2 0 R /Dests << / 3 0 R >> >> endobj
2 0 obj << /Type /Pages /Kids [4 0 R 5 0 R] /Count 2 >> endobj
3 0 obj [ 5 0 R /Fit ] endobj
4 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 200 200]
  /Annots [ << /Type /Annot /Subtype /Link /Rect [0 0 50 50]
              /A << /S /GoTo /D / >> >> ] >> endobj
5 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 200 200] >> endobj
trailer << /Root 1 0 R /Size 6 >>"""


def test_add_pages_from_migrates_empty_name_dest():
    dest = Pdf.new()
    with Pdf.open(io.BytesIO(_EMPTY_NAME_LINK_PDF)) as src:
        result = dest.add_pages_from(src)
    assert result.named_dests_added == 1
    assert dest.Root.Dests[Name('/')].D[0] == dest.pages[1].obj
    assert dest.pages[0].obj.Annots[0].A.D == Name('/')


def test_add_pages_from_renames_colliding_empty_name_dest():
    dest = Pdf.new()
    with Pdf.open(io.BytesIO(_EMPTY_NAME_LINK_PDF)) as src:
        dest.add_pages_from(src)
        result = dest.add_pages_from(src)
    assert result.renamed_dests == {'/': '/.1'}
    assert Name('/') in dest.Root.Dests and Name('/.1') in dest.Root.Dests
    assert dest.pages[2].obj.Annots[0].A.D == Name('/.1')
    assert dest.Root.Dests[Name('/.1')].D[0] == dest.pages[3].obj


# --- Optional content (layers) ---


def _ocg(pdf, name):
    return pdf.make_indirect(Dictionary(Type=Name.OCG, Name=String(name)))


def _layer_page(pdf, **groups):
    """Add a page whose /Properties name the given optional content."""
    page = pdf.add_blank_page(page_size=(200, 200))
    page.obj.Resources = Dictionary(Properties=Dictionary(**groups))
    page.obj.Contents = pdf.make_stream(
        b''.join(b'/OC /%s BDC 0 0 10 10 re f EMC\n' % k.encode() for k in groups)
    )
    return page


def _set_ocproperties(pdf, groups, **config):
    pdf.Root.OCProperties = pdf.make_indirect(
        Dictionary(OCGs=Array(groups), D=Dictionary(**config))
    )


def _names(array):
    return [str(g.Name) for g in array]


def test_pagecopyresult_layer_and_outline_defaults():
    r = PageCopyResult(pages_added=1, forms='preserve')
    assert r.layers == 'preserve'
    assert r.layers_added == 0
    assert r.outlines == 'preserve'
    assert r.outline_items_added == 0
    assert r.outline_items_dropped == 0


def test_layers_registered_in_destination_without_ocproperties():
    src = Pdf.new()
    a = _ocg(src, 'A')
    _layer_page(src, L0=a)
    _set_ocproperties(src, [a], Order=Array([a]))

    dest = Pdf.new()
    result = dest.add_pages_from(src)

    assert result.layers == 'preserve'
    assert result.layers_added == 1
    props = dest.Root.OCProperties
    assert _names(props.OCGs) == ['A']
    # The registered group is the very object the copied page refers to
    assert props.OCGs[0].is_same_object_as(dest.pages[0].obj.Resources.Properties.L0)
    assert props.OCGs[0].is_owned_by(dest)
    assert _names(props.D.Order) == ['A']
    assert Name.OFF not in props.D


def test_layers_survive_save():
    src = Pdf.new()
    a, b = _ocg(src, 'A'), _ocg(src, 'B')
    _layer_page(src, L0=a, L1=b)
    _set_ocproperties(src, [a, b], Order=Array([a, b]), OFF=Array([b]))
    dest = Pdf.new()
    dest.add_pages_from(src)
    src.close()
    buf = io.BytesIO()
    dest.save(buf)
    with Pdf.open(io.BytesIO(buf.getvalue())) as out:
        props = out.Root.OCProperties
        assert _names(props.OCGs) == ['A', 'B']
        assert _names(props.D.OFF) == ['B']
        assert props.D.OFF[0].is_same_object_as(
            out.pages[0].obj.Resources.Properties.L1
        )


def test_layers_source_without_ocproperties_is_noop():
    src = Pdf.new()
    _layer_page(src, L0=_ocg(src, 'A'))  # unregistered: viewers ignore it
    dest = Pdf.new()
    result = dest.add_pages_from(src)
    assert result.layers_added == 0
    assert Name.OCProperties not in dest.Root


def test_layers_ignore():
    src = Pdf.new()
    a = _ocg(src, 'A')
    _layer_page(src, L0=a)
    _set_ocproperties(src, [a])
    dest = Pdf.new()
    result = dest.add_pages_from(src, layers='ignore')
    assert result.layers == 'ignore'
    assert result.layers_added == 0
    assert Name.OCProperties not in dest.Root


def test_layers_invalid_mode():
    with pytest.raises(ValueError, match='layers'):
        Pdf.new().add_pages_from(Pdf.new(), layers='strip')


def test_layers_only_those_on_copied_pages():
    src = Pdf.new()
    a, b, unused = _ocg(src, 'A'), _ocg(src, 'B'), _ocg(src, 'Unused')
    _layer_page(src, L0=a)
    _layer_page(src, L0=b)
    _set_ocproperties(
        src, [a, b, unused], Order=Array([a, b, unused]), OFF=Array([a, b, unused])
    )
    dest = Pdf.new()
    result = dest.add_pages_from(src, [1])
    assert result.layers_added == 1
    props = dest.Root.OCProperties
    assert _names(props.OCGs) == ['B']
    assert _names(props.D.Order) == ['B']
    assert _names(props.D.OFF) == ['B']


def test_layers_not_listed_by_source_are_not_registered():
    src = Pdf.new()
    a, stray = _ocg(src, 'A'), _ocg(src, 'Stray')
    _layer_page(src, L0=a, L1=stray)
    _set_ocproperties(src, [a])
    dest = Pdf.new()
    dest.add_pages_from(src)
    assert _names(dest.Root.OCProperties.OCGs) == ['A']


def test_layers_found_wherever_optional_content_is_referenced():
    src = Pdf.new()
    names = ['Image', 'Annot', 'Form', 'Nested', 'M1', 'M2', 'V1', 'V2', 'Ap']
    g = {n: _ocg(src, n) for n in names}
    hidden = _ocg(src, 'OtherPage')
    page = src.add_blank_page(page_size=(200, 200))

    image = src.make_stream(
        b'\x00',
        Type=Name.XObject,
        Subtype=Name.Image,
        Width=1,
        Height=1,
        ColorSpace=Name.DeviceGray,
        BitsPerComponent=8,
        OC=g['Image'],
    )
    inner = src.make_stream(
        b'/OC /P BDC EMC',
        Type=Name.XObject,
        Subtype=Name.Form,
        BBox=Array([0, 0, 1, 1]),
        Resources=Dictionary(Properties=Dictionary(P=g['Nested'])),
    )
    form = src.make_stream(
        b'/Inner Do',
        Type=Name.XObject,
        Subtype=Name.Form,
        BBox=Array([0, 0, 1, 1]),
        OC=g['Form'],
        Resources=Dictionary(XObject=Dictionary(Inner=inner)),
    )
    membership = src.make_indirect(
        Dictionary(
            Type=Name.OCMD,
            OCGs=Array([g['M1'], g['M2']]),
            VE=Array([Name.And, g['V1'], Array([Name.Not, g['V2']])]),
        )
    )
    appearance = src.make_stream(
        b'',
        Type=Name.XObject,
        Subtype=Name.Form,
        BBox=Array([0, 0, 1, 1]),
        OC=g['Ap'],
    )
    page.obj.Resources = Dictionary(
        XObject=Dictionary(Im=image, Fm=form),
        Properties=Dictionary(MC=membership),
    )
    page.obj.Contents = src.make_stream(b'/Im Do /Fm Do /OC /MC BDC EMC')
    page.obj.Annots = Array(
        [
            src.make_indirect(
                Dictionary(
                    Type=Name.Annot,
                    Subtype=Name.Square,
                    Rect=Array([0, 0, 5, 5]),
                    OC=g['Annot'],
                    AP=Dictionary(N=appearance),
                )
            )
        ]
    )
    _layer_page(src, L0=hidden)
    _set_ocproperties(src, [*g.values(), hidden])

    dest = Pdf.new()
    result = dest.add_pages_from(src, [0])
    assert sorted(_names(dest.Root.OCProperties.OCGs)) == sorted(names)
    assert result.layers_added == len(names)


def test_layers_single_group_membership_dictionary():
    src = Pdf.new()
    a = _ocg(src, 'A')
    _layer_page(src, L0=Dictionary(Type=Name.OCMD, OCGs=a))
    _set_ocproperties(src, [a])
    dest = Pdf.new()
    dest.add_pages_from(src)
    assert _names(dest.Root.OCProperties.OCGs) == ['A']


def test_layers_default_visibility_with_source_basestate_off():
    src = Pdf.new()
    shown, hidden, both = _ocg(src, 'Shown'), _ocg(src, 'Hidden'), _ocg(src, 'Both')
    _layer_page(src, L0=shown, L1=hidden, L2=both)
    _set_ocproperties(
        src,
        [shown, hidden, both],
        BaseState=Name.OFF,
        ON=Array([shown, both]),
        OFF=Array([both]),  # OFF is applied after ON
    )
    dest = Pdf.new()
    dest.add_pages_from(src)
    config = dest.Root.OCProperties.D
    # The new default configuration has the default /BaseState, ON
    assert Name.BaseState not in config
    assert Name.ON not in config
    assert sorted(_names(config.OFF)) == ['Both', 'Hidden']


def test_layers_merge_into_destination_with_layers():
    dest = Pdf.new()
    x, y = _ocg(dest, 'X'), _ocg(dest, 'Y')
    _layer_page(dest, L0=x, L1=y)
    _set_ocproperties(
        dest, [x, y], Order=Array([x, y]), OFF=Array([y]), Locked=Array([x])
    )

    src = Pdf.new()
    a, b = _ocg(src, 'A'), _ocg(src, 'B')
    _layer_page(src, L0=a, L1=b)
    _set_ocproperties(
        src, [a, b], Order=Array([b, a]), OFF=Array([a]), Locked=Array([b])
    )

    result = dest.add_pages_from(src)
    assert result.layers_added == 2
    props = dest.Root.OCProperties
    assert _names(props.OCGs) == ['X', 'Y', 'A', 'B']
    assert _names(props.D.Order) == ['X', 'Y', 'B', 'A']
    assert _names(props.D.OFF) == ['Y', 'A']
    assert _names(props.D.Locked) == ['X', 'B']
    assert Name.ON not in props.D


def test_layers_merge_into_destination_with_basestate_off():
    dest = Pdf.new()
    x, y = _ocg(dest, 'X'), _ocg(dest, 'Y')
    _layer_page(dest, L0=x, L1=y)
    _set_ocproperties(dest, [x, y], BaseState=Name.OFF, ON=Array([x]))

    src = Pdf.new()
    a, b = _ocg(src, 'A'), _ocg(src, 'B')
    _layer_page(src, L0=a, L1=b)
    _set_ocproperties(src, [a, b], OFF=Array([b]))

    dest.add_pages_from(src)
    config = dest.Root.OCProperties.D
    assert config.BaseState == Name.OFF
    assert _names(config.ON) == ['X', 'A']  # A stays visible
    assert Name.OFF not in config  # B is off through /BaseState


def test_layers_order_keeps_labels_and_nesting():
    src = Pdf.new()
    a, a1, a2, b, c, gone, gone1 = (
        _ocg(src, n) for n in ['A', 'A1', 'A2', 'B', 'C', 'Gone', 'Gone1']
    )
    orphan = _ocg(src, 'Orphan')
    _layer_page(src, L0=a, L1=a1, L2=b, L3=c, L4=orphan)
    _layer_page(src, L0=a2, L1=gone, L2=gone1)
    _set_ocproperties(
        src,
        [a, a1, a2, b, c, gone, gone1, orphan],
        Order=Array(
            [
                a,
                Array([a1, a2]),  # sublayers of A
                Array([String('Group'), b, gone]),  # labelled collection
                Array([String('Empty'), gone1]),  # nothing survives
                gone,
                Array([orphan]),  # sublayer whose parent is not copied
                c,
            ]
        ),
    )
    dest = Pdf.new()
    dest.add_pages_from(src, [0])
    order = dest.Root.OCProperties.D.Order
    assert len(order) == 5
    assert str(order[0].Name) == 'A'
    assert _names(order[1]) == ['A1']
    assert str(order[2][0]) == 'Group' and str(order[2][1].Name) == 'B'
    assert len(order[2]) == 2
    # Not nested under the unrelated group that now precedes it
    assert str(order[3].Name) == 'Orphan'
    assert str(order[4].Name) == 'C'


def test_layers_source_without_order_adds_none():
    dest = Pdf.new()
    x = _ocg(dest, 'X')
    _layer_page(dest, L0=x)
    _set_ocproperties(dest, [x], Order=Array([x]))
    src = Pdf.new()
    a = _ocg(src, 'A')
    _layer_page(src, L0=a)
    _set_ocproperties(src, [a])
    dest.add_pages_from(src)
    assert _names(dest.Root.OCProperties.D.Order) == ['X']


def test_layers_radio_groups_and_auto_state():
    src = Pdf.new()
    a, b, c = _ocg(src, 'A'), _ocg(src, 'B'), _ocg(src, 'C')
    _layer_page(src, L0=a, L1=b)
    _layer_page(src, L0=c)
    _set_ocproperties(
        src,
        [a, b, c],
        RBGroups=Array([Array([a, b, c]), Array([a, c])]),
        AS=Array(
            [
                Dictionary(
                    Event=Name.Print, Category=Array([Name.Print]), OCGs=Array([a, c])
                ),
                Dictionary(
                    Event=Name.View, Category=Array([Name.Zoom]), OCGs=Array([c])
                ),
            ]
        ),
    )
    dest = Pdf.new()
    x = _ocg(dest, 'X')
    _layer_page(dest, L0=x)
    _set_ocproperties(
        dest,
        [x],
        AS=Array(
            [
                Dictionary(
                    Event=Name.Export, Category=Array([Name.Export]), OCGs=Array([x])
                )
            ]
        ),
    )
    dest.add_pages_from(src, [0])
    config = dest.Root.OCProperties.D
    # A group of one is no constraint, so only the first radio group survives
    assert [_names(group) for group in config.RBGroups] == [['A', 'B']]
    assert len(config.AS) == 2
    assert _names(config.AS[0].OCGs) == ['X']
    assert config.AS[1].Event == Name.Print
    assert list(config.AS[1].Category) == [Name.Print]
    assert _names(config.AS[1].OCGs) == ['A']


def test_layers_not_duplicated_by_second_copy():
    src = Pdf.new()
    a = _ocg(src, 'A')
    _layer_page(src, L0=a)
    _layer_page(src, L0=a)
    _set_ocproperties(src, [a], Order=Array([a]), OFF=Array([a]))
    dest = Pdf.new()
    first = dest.add_pages_from(src, [0])
    second = dest.add_pages_from(src, [1])
    assert (first.layers_added, second.layers_added) == (1, 0)
    props = dest.Root.OCProperties
    assert len(props.OCGs) == len(props.D.Order) == len(props.D.OFF) == 1


def test_layers_destination_ocproperties_incomplete():
    dest = Pdf.new()
    dest.Root.OCProperties = Dictionary()  # required /OCGs and /D are missing
    src = Pdf.new()
    a = _ocg(src, 'A')
    _layer_page(src, L0=a)
    _set_ocproperties(src, [a], OFF=Array([a]))
    dest.add_pages_from(src)
    props = dest.Root.OCProperties
    assert _names(props.OCGs) == ['A']
    assert _names(props.D.OFF) == ['A']


def test_layers_malformed_source_fails_closed():
    src = Pdf.new()
    a, b = _ocg(src, 'A'), _ocg(src, 'B')
    loop = src.make_indirect(Array([Name.And, a]))
    loop.append(loop)
    membership = src.make_indirect(Dictionary(Type=Name.OCMD, VE=loop, OCGs=42))
    membership.Self = membership
    page = _layer_page(src, L0=membership, L1=b, L2=Name.Bogus, L3=Dictionary())
    page.obj.Annots = Array([42, Dictionary(OC=Array([a]))])
    order = src.make_indirect(Array([a, 42, Name.Bogus]))
    order.append(order)
    _set_ocproperties(
        src,
        [a, b, 42],
        Order=order,
        ON=Name.Bogus,
        OFF=Array([b, 42, Array([a])]),
        Locked=Dictionary(),
        RBGroups=Array([a, Array([a, b, 42, a])]),
        AS=Array([42, Dictionary(OCGs=Array([a])), Dictionary(Event=Name.View)]),
    )
    dest = Pdf.new()
    result = dest.add_pages_from(src)
    assert result.layers_added == 2
    config = dest.Root.OCProperties.D
    assert _names(config.Order) == ['A']
    assert _names(config.OFF) == ['B']
    assert Name.Locked not in config
    assert [_names(group) for group in config.RBGroups] == [['A', 'B']]
    assert Name.AS not in config


@pytest.mark.parametrize('ocproperties', [42, Name.Bogus, Array([])])
def test_layers_source_ocproperties_not_a_dictionary(ocproperties):
    src = Pdf.new()
    _layer_page(src, L0=_ocg(src, 'A'))
    src.Root.OCProperties = ocproperties
    dest = Pdf.new()
    assert dest.add_pages_from(src).layers_added == 0
    assert Name.OCProperties not in dest.Root


def test_layers_deeply_nested_order_does_not_crash():
    src = Pdf.new()
    a = _ocg(src, 'A')
    _layer_page(src, L0=a)
    order = Array([a])
    for _ in range(5000):
        order = Array([order])
    _set_ocproperties(src, [a], Order=order)
    dest = Pdf.new()
    assert dest.add_pages_from(src).layers_added == 1
    assert _names(dest.Root.OCProperties.OCGs) == ['A']


# --- Outlines (bookmarks) ---


def _pdf_with_outline(n_pages=4):
    """Build a PDF with an outline.

    Part I -> page 0 (closed, bold, red)
        Chapter 1 -> page 1 /XYZ
        Chapter 2 -> page 2
    Part II (no destination)
        Chapter 3 -> page 3
    Website -> URI action
    """
    pdf = Pdf.new()
    for _ in range(n_pages):
        pdf.add_blank_page(page_size=(200, 200))
    with pdf.open_outline() as outline:
        part1 = pikepdf.OutlineItem('Part I', 0)
        part1.is_closed = True
        part1.bold = True
        part1.color = (1.0, 0.0, 0.0)
        part1.children.append(
            pikepdf.OutlineItem('Chapter 1', 1, 'XYZ', left=10, top=150, zoom=2)
        )
        part1.children.append(pikepdf.OutlineItem('Chapter 2', 2))
        part2 = pikepdf.OutlineItem('Part II')
        part2.children.append(pikepdf.OutlineItem('Chapter 3', 3))
        web = pikepdf.OutlineItem(
            'Website', action=Dictionary(S=Name.URI, URI=String('https://example.com'))
        )
        outline.root.extend([part1, part2, web])
    return pdf


def _outline_tree(pdf):
    def walk(items):
        return [(item.title, walk(item.children)) for item in items]

    with pdf.open_outline() as outline:
        return walk(outline.root)


def _page_index(item):
    return pikepdf.Page(item.destination[0]).index


def test_outlines_copied_and_retargeted():
    dest = Pdf.new()
    dest.add_blank_page(page_size=(200, 200))
    with _pdf_with_outline() as src:
        result = dest.add_pages_from(src)
    assert result.outlines == 'preserve'
    assert result.outline_items_added == 5
    assert result.outline_items_dropped == 1  # the URI item
    assert _outline_tree(dest) == [
        ('Part I', [('Chapter 1', []), ('Chapter 2', [])]),
        ('Part II', [('Chapter 3', [])]),
    ]
    with dest.open_outline() as outline:
        part1, part2 = outline.root
        assert part1.destination[0].is_owned_by(dest)
        assert _page_index(part1) == 1
        ch1, ch2 = part1.children
        assert _page_index(ch1) == 2
        assert list(ch1.destination)[1:] == [Name.XYZ, 10, 150, 2]
        assert _page_index(ch2) == 3
        assert part2.destination is None and part2.action is None
        assert _page_index(part2.children[0]) == 4
        # style
        assert part1.is_closed and part1.bold and not part1.italic
        assert part1.color == (1.0, 0.0, 0.0)
        assert not part2.is_closed and part2.color is None
    assert len(dest.pages) == 5


def test_outlines_survive_save():
    dest = Pdf.new()
    with _pdf_with_outline() as src:
        dest.add_pages_from(src)
    buf = io.BytesIO()
    dest.save(buf)
    with Pdf.open(io.BytesIO(buf.getvalue())) as out:
        assert len(out.pages) == 4
        # Part I is closed and hides its chapters; Part II shows Chapter 3
        assert out.Root.Outlines.Count == 3
        assert out.Root.Outlines.First.Count == -2
        with out.open_outline() as outline:
            assert _page_index(outline.root[1].children[0]) == 3


def test_outlines_subset_drops_items_and_keeps_ancestors():
    dest = Pdf.new()
    with _pdf_with_outline() as src:
        result = dest.add_pages_from(src, [2, 3])
    assert _outline_tree(dest) == [
        ('Part I', [('Chapter 2', [])]),
        ('Part II', [('Chapter 3', [])]),
    ]
    assert result.outline_items_added == 4
    assert result.outline_items_dropped == 2
    with dest.open_outline() as outline:
        part1 = outline.root[0]
        # Part I pointed at a page that was not copied; it survives as a heading
        assert part1.destination is None and part1.action is None
        assert part1.bold
        assert _page_index(part1.children[0]) == 0
    assert len(dest.pages) == 2


def test_outlines_nothing_lands_on_copied_pages():
    src = _pdf_with_outline(n_pages=5)
    dest = Pdf.new()
    result = dest.add_pages_from(src, [4])
    assert result.outline_items_added == 0
    assert result.outline_items_dropped == 6
    assert Name.Outlines not in dest.Root


def test_outlines_ignore():
    dest = Pdf.new()
    with _pdf_with_outline() as src:
        result = dest.add_pages_from(src, outlines='ignore')
    assert result.outlines == 'ignore'
    assert result.outline_items_added == 0
    assert Name.Outlines not in dest.Root


def test_outlines_invalid_mode():
    with pytest.raises(ValueError, match='outlines'):
        Pdf.new().add_pages_from(Pdf.new(), outlines='strip')


def test_outlines_source_without_outline():
    src = Pdf.new()
    src.add_blank_page()
    dest = Pdf.new()
    result = dest.add_pages_from(src)
    assert result.outline_items_added == 0
    assert Name.Outlines not in dest.Root


def test_outlines_appended_after_existing_items():
    dest = Pdf.new()
    dest.add_blank_page(page_size=(200, 200))
    with dest.open_outline() as outline:
        intro = pikepdf.OutlineItem('Intro', 0)
        intro.children.append(pikepdf.OutlineItem('Preface', 0))
        outline.root.append(intro)
    existing = dest.Root.Outlines.First
    with _pdf_with_outline() as src:
        dest.add_pages_from(src, [0, 1])
        dest.add_pages_from(src, [3])
    assert _outline_tree(dest) == [
        ('Intro', [('Preface', [])]),
        ('Part I', [('Chapter 1', [])]),
        ('Part II', [('Chapter 3', [])]),
    ]
    root = dest.Root.Outlines
    assert root.First.is_same_object_as(existing)
    assert str(root.Last.Title) == 'Part II'
    assert root.Last.Parent.is_same_object_as(root)
    assert str(root.Last.Prev.Title) == 'Part I'
    assert Name.Next not in root.Last
    # Intro, Preface, Part I (closed, hiding Chapter 1), Part II, Chapter 3
    assert root.Count == 5
    with dest.open_outline() as outline:
        assert _page_index(outline.root[1]) == 1
        assert _page_index(outline.root[2].children[0]) == 3


def test_outlines_named_and_action_destinations():
    src = Pdf.new()
    pages = [src.add_blank_page(page_size=(200, 200)) for _ in range(3)]
    src.Root.Names = src.make_indirect(Dictionary(Dests=NameTree.new(src).obj))
    names = NameTree(src.Root.Names.Dests)
    names['one'] = src.make_indirect(Dictionary(D=Array([pages[1].obj, Name.Fit])))
    names['absent'] = src.make_indirect(Dictionary(D=Array([pages[2].obj, Name.Fit])))
    src.Root.Dests = src.make_indirect(
        Dictionary(Legacy=Array([pages[0].obj, Name.FitH, 99]))
    )
    with src.open_outline() as outline:
        outline.root.extend(
            [
                pikepdf.OutlineItem('Named', String('one')),
                pikepdf.OutlineItem('Legacy', Name.Legacy),
                pikepdf.OutlineItem('Not copied', String('absent')),
                pikepdf.OutlineItem('Unknown', String('nonesuch')),
                pikepdf.OutlineItem(
                    'Action',
                    action=Dictionary(
                        S=Name.GoTo, D=Array([pages[1].obj, Name.XYZ, None, 5, None])
                    ),
                ),
                pikepdf.OutlineItem(
                    'Named action', action=Dictionary(S=Name.GoTo, D=String('one'))
                ),
                pikepdf.OutlineItem(
                    'Remote',
                    action=Dictionary(S=Name.GoToR, F=String('x.pdf'), D=Array([0])),
                ),
            ]
        )
    dest = Pdf.new()
    dest.add_blank_page(page_size=(200, 200))
    result = dest.add_pages_from(src, [0, 1])
    assert result.outline_items_dropped == 3
    with dest.open_outline() as outline:
        assert [i.title for i in outline.root] == [
            'Named',
            'Legacy',
            'Action',
            'Named action',
        ]
        named, legacy, action, named_action = outline.root
        assert _page_index(named) == 2
        assert list(named.destination)[1:] == [Name.Fit]
        assert _page_index(legacy) == 1
        assert list(legacy.destination)[1:] == [Name.FitH, 99]
        assert _page_index(action) == 2
        assert list(action.destination)[1:] == [Name.XYZ, None, 5, None]
        assert _page_index(named_action) == 2


def test_outlines_cyclic_source_does_not_hang():
    src = _pdf_with_outline()
    first = src.Root.Outlines.First
    last = src.Root.Outlines.Last
    last.Next = first  # siblings loop
    first.First.First = first  # a child that is its own ancestor
    dest = Pdf.new()
    result = dest.add_pages_from(src)
    assert result.outline_items_added >= 4
    assert len(dest.pages) == 4


@pytest.mark.parametrize(
    'key, value',
    [
        ('Root.Outlines', 42),
        ('First', 42),
        ('First.Next', 42),
        ('First.Dest', 42),
        ('First.Dest', Array([])),
        ('First.Dest', Array([0, Name.Fit])),
        ('First.A', 42),
    ],
)
def test_outlines_malformed_source_fails_closed(key, value):
    src = _pdf_with_outline()
    if key == 'Root.Outlines':
        src.Root.Outlines = value
    elif key == 'First':
        src.Root.Outlines.First = value
    else:
        src.Root.Outlines.First[Name('/' + key.split('.')[1])] = value
    dest = Pdf.new()
    result = dest.add_pages_from(src)
    assert result.pages_added == 4
    assert len(dest.pages) == 4


def test_outlines_destination_outline_malformed():
    dest = Pdf.new()
    dest.add_blank_page(page_size=(200, 200))
    with dest.open_outline() as outline:
        outline.root.append(pikepdf.OutlineItem('One', 0))
        outline.root.append(pikepdf.OutlineItem('Two', 0))
    del dest.Root.Outlines.Last
    del dest.Root.Outlines.Count
    with _pdf_with_outline() as src:
        dest.add_pages_from(src, [3])
    assert _outline_tree(dest) == [
        ('One', []),
        ('Two', []),
        ('Part II', [('Chapter 3', [])]),
    ]


def test_outlines_same_page_copied_twice():
    dest = Pdf.new()
    with _pdf_with_outline() as src:
        result = dest.add_pages_from(src, [3, 3])
    assert result.outline_items_added == 2
    with dest.open_outline() as outline:
        assert _page_index(outline.root[0].children[0]) == 0
