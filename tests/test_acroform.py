# SPDX-FileCopyrightText: 2022 James R. Barlow
# SPDX-License-Identifier: CC0-1.0

from __future__ import annotations

import pytest

from pikepdf import AcroFormDocument, Pdf


@pytest.fixture
def form(resources):
    with Pdf.open(resources / 'form.pdf') as pdf:
        yield pdf


def test_set_form_field_name(form):
    afd = AcroFormDocument(form)
    field = form.Root.AcroForm.Fields[0]
    assert field.T == 'Text1'
    afd.set_form_field_name(field, 'new_field_name')
    assert field.T == 'new_field_name'
