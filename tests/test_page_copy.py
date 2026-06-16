# SPDX-FileCopyrightText: 2026 James R. Barlow
# SPDX-License-Identifier: MPL-2.0
from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pikepdf
from pikepdf import FormCopyWarning, Job, PageCopyResult, Pdf


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
