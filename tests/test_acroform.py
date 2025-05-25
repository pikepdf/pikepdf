# SPDX-FileCopyrightText: 2022 James R. Barlow
# SPDX-License-Identifier: CC0-1.0

from __future__ import annotations

import pytest

from pikepdf import Annotation, Name, Pdf


@pytest.fixture
def form(resources):
    with Pdf.open(resources / 'form.pdf') as pdf:
        yield pdf


@pytest.fixture
def dd0293(resources):
    """This is a real-world fillable form with significantly more complexity than the
    basic example form above. It has examples of:

    * Choice fields
    * Digital signature fields
    * Multi-line text fields
    * Fields with an alternate name
    """
    with Pdf.open(resources / 'form_dd0293.pdf') as pdf:
        yield pdf


def test_acroform(form):
    acro = form.acroform
    assert acro.exists
    assert len(acro.fields) == 5


def test_appearances(form):
    acro = form.acroform
    acro.needs_appearances = True
    assert acro.needs_appearances is True
    acro.generate_appearances_if_needed()
    assert acro.needs_appearances is False


def test_text(form):
    field = form.acroform.get_fields_with_qualified_name('Text1')[0]
    assert field.fully_qualified_name == 'Text1'
    assert field.default_appearance == b"/Helv 12 Tf 0 g"
    assert field.get_inheritable_field_value('/DA') == b"/Helv 12 Tf 0 g"
    assert field.get_inheritable_field_value_as_string('/DA') == "/Helv 12 Tf 0 g"
    assert Name.Font in field.default_resources
    assert field.top_level_field == field
    assert field.is_text
    assert not field.is_checkbox
    assert not field.is_radio_button
    assert not field.is_pushbutton
    assert not field.is_choice


def test_button(form):
    field = form.acroform.get_fields_with_qualified_name('Button2')[0]
    assert field.fully_qualified_name == 'Button2'
    assert field.top_level_field == field
    assert not field.is_text
    assert not field.is_checkbox
    assert not field.is_radio_button
    assert field.is_pushbutton
    assert not field.is_choice


def test_checkbox(form):
    field = form.acroform.get_fields_with_qualified_name('Check Box3')[0]
    assert field.fully_qualified_name == 'Check Box3'
    assert field.top_level_field == field
    assert not field.is_text
    assert field.is_checkbox
    assert not field.is_radio_button
    assert not field.is_pushbutton
    assert not field.is_choice


def test_radio_button(form):
    fields = form.acroform.get_fields_with_qualified_name('Group4')
    assert len(fields) == 1  # 1 group, but not the 2 individual radio buttons
    top_field = fields[0]
    assert top_field.fully_qualified_name == 'Group4'
    assert top_field.top_level_field == top_field
    assert not top_field.is_text
    assert not top_field.is_checkbox
    assert top_field.is_radio_button
    assert not top_field.is_pushbutton
    assert not top_field.is_choice
    terminal_fields = list(
        filter(lambda f: f.fully_qualified_name == 'Group4', form.acroform.fields)
    )
    assert len(terminal_fields) == 2
    for field in terminal_fields:
        assert field.top_level_field != field
        assert field.parent == top_field
        assert field.top_level_field == top_field
        assert field.get_inheritable_field_value_as_name('/FT') == top_field.field_type
        assert not field.is_text
        assert not field.is_checkbox
        assert field.is_radio_button
        assert not field.is_pushbutton
        assert not field.is_choice


def test_choice(dd0293):
    field = dd0293.acroform.get_fields_with_qualified_name(
        'form1[0].page1[0].#subform[2].DropDownList1[0]'
    )[0]
    assert (
        field.fully_qualified_name == 'form1[0].page1[0].#subform[2].DropDownList1[0]'
    )
    assert field.partial_name == 'DropDownList1[0]'
    assert (
        field.alternate_name
        == 'SECTION 2: SERVICE INFORMATION (Information from DD Form 214. Include Member Copy of DD Form 214 and enter as much as is readily available. - 7. GRADE/RANK AT DISCHARGE - ARMY - Select from drop-down list.'
    )
    assert field.top_level_field.partial_name == 'form1[0]'
    assert not field.is_text
    assert not field.is_checkbox
    assert not field.is_radio_button
    assert not field.is_pushbutton
    assert field.is_choice
    # In theory, field.choices should be populated. However, this does not
    # work. The underlaying QPDF implementation appears to be at fault. See
    # https://github.com/qpdf/qpdf/issues/1433


def test_existing_value(dd0293):
    field = dd0293.acroform.get_fields_with_qualified_name(
        'form1[0].#pageSet[0].Page1[0].TextField7[0]'
    )[0]
    assert field.value == "Controlled by: CUI Category: LDC: POC: "
    assert field.value_as_string == "Controlled by: CUI Category: LDC: POC: "
    assert field.default_value == "Controlled by: \nCUI Category: \nLDC: \nPOC: "
    assert (
        field.default_value_as_string == "Controlled by: \nCUI Category: \nLDC: \nPOC: "
    )


def test_remove_fields(form):
    acro = form.acroform
    fields = acro.get_fields_with_qualified_name('Button2')
    assert len(fields) == 1
    acro.remove_fields(fields)
    fields = acro.get_fields_with_qualified_name('Button2')
    assert len(fields) == 0


def test_disable_signatures(dd0293):
    sigs = [f for f in dd0293.pages[1].Annots if hasattr(f, 'FT') and f.FT == '/Sig']
    assert len(sigs) == 1
    dd0293.acroform.disable_digital_signatures()
    sigs = [f for f in dd0293.pages[1].Annots if hasattr(f, 'FT') and f.FT == '/Sig']
    assert len(sigs) == 0


def test_get_annotations_for_field(form):
    field = form.acroform.get_fields_with_qualified_name('Text1')[0]
    annots = form.acroform.get_annotations_for_field(field)
    assert len(annots) == 1
    print(annots[0])
    assert annots[0].subtype == Name.Widget


def test_get_widget_annotations_for_page(form):
    page = form.pages[0]
    annots = form.acroform.get_widget_annotations_for_page(page)
    assert (
        len(annots) == 5
    )  # 1 annotation per terminal field (radio buttons each have their own)


def test_get_form_fields_for_page(form):
    page = form.pages[0]
    fields = form.acroform.get_form_fields_for_page(page)
    assert len(fields) == 4  # 1 field per top-level field (2 radio buttons count as 1)


def test_get_field_for_annotation(form):
    annot = Annotation(form.Root.AcroForm.Fields[1])
    field = form.acroform.get_field_for_annotation(annot)
    assert field.fully_qualified_name == 'Button2'


def test_copy_form(form, dd0293):
    orig_count = len(dd0293.acroform.fields)
    dd0293.pages.extend(form.pages)
    copied_fields = dd0293.acroform.fix_copied_annotations(
        dd0293.pages[-1], form.pages[0], form.acroform
    )
    new_count = len(dd0293.acroform.fields)
    assert len(copied_fields) == 4  # Count is top-level fields
    assert new_count == orig_count + 5  # Count is terminal fields
