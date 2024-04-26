# SPDX-FileCopyrightText: 2022 James R. Barlow
# SPDX-License-Identifier: CC0-1.0

from __future__ import annotations

import pytest

from pikepdf import AcroFormDocument, Annotation, Array, Dictionary, Name, Pdf


@pytest.fixture
def form(resources):
    with Pdf.open(resources / 'form.pdf') as pdf:
        yield pdf


def test_set_form_field_name(form):
    afd = AcroFormDocument(form)
    annot = Annotation(form.Root.AcroForm.Fields[0])
    assert annot.T == 'Text1'
    afd.set_form_field_name(annot, 'new_field_name')
    assert annot.T == 'new_field_name'
