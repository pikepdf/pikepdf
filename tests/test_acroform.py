# SPDX-FileCopyrightText: 2022 James R. Barlow
# SPDX-License-Identifier: CC0-1.0

from __future__ import annotations

import pytest

from pikepdf import AcroFormDocument, Array, Dictionary, Name, Pdf


@pytest.fixture
def form(resources):
    with Pdf.open(resources / 'form.pdf') as pdf:
        yield pdf


def test_set_form_field_name(form):
    afd = AcroFormDocument(form)
    for page in form.pages:
        if Name.Annots not in page:
            continue
        annotations = page[Name.Annots]
        for index, annot in annotations:
            if "/T" in annot:
                newName = annot + 'test' + index
                afd.set_form_field_name(annot, newName)
                assert annot.T == newName
