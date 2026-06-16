# SPDX-FileCopyrightText: 2026 James R. Barlow
# SPDX-License-Identifier: MPL-2.0
from __future__ import annotations

import pikepdf
from pikepdf import FormCopyWarning, PageCopyResult


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
