# SPDX-FileCopyrightText: 2026 James R. Barlow
# SPDX-License-Identifier: MPL-2.0
from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pikepdf
from pikepdf import (
    Array,
    Dictionary,
    FormCopyWarning,
    Job,
    Name,
    PageCopyResult,
    Pdf,
    String,
)


def test_formcopywarning_is_userwarning():
    assert issubclass(FormCopyWarning, UserWarning)
    assert pikepdf.exceptions.FormCopyWarning is FormCopyWarning


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
