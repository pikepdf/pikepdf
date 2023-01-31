# SPDX-FileCopyrightText: 2022 James R. Barlow
# SPDX-License-Identifier: CC0-1.0

from __future__ import annotations

import pytest

from pikepdf import Annotation, Name, Pdf


@pytest.fixture
def form(resources):
    with Pdf.open(resources / 'form.pdf') as pdf:
        yield pdf


def test_button(form):
    annot = Annotation(form.Root.AcroForm.Fields[1])
    assert annot.subtype == Name.Widget
    assert annot.flags == 4
    assert annot.appearance_state is None
    assert Name.N in annot.appearance_dict
    stream = annot.get_appearance_stream(Name.N)
    assert stream == annot.obj.AP.N
    assert (
        annot.get_page_content_for_appearance(Name.XYZ, 0)
        == b'q\n1 0 0 1 0 24.0182 cm\n/XYZ Do\nQ\n'
    )


def test_checkbox(form):
    annot = Annotation(form.Root.AcroForm.Fields[2])
    assert annot.subtype == Name.Widget
    assert annot.flags == 4
    assert annot.appearance_state == Name.Off
    assert Name.N in annot.appearance_dict
    assert Name.D in annot.appearance_dict
    stream = annot.get_appearance_stream(Name.D, Name.Yes)
    assert stream == annot.obj.AP.D.Yes
    assert (
        annot.get_page_content_for_appearance(Name.XYZ, 0)
        == b'q\n1 0 0 1 4.41818 3.10912 cm\n/XYZ Do\nQ\n'
    )


def test_annot_eq(form):
    button = Annotation(form.Root.AcroForm.Fields[1])
    checkbox = Annotation(form.Root.AcroForm.Fields[2])
    assert button != checkbox
    assert button == button
