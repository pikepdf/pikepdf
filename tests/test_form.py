# SPDX-FileCopyrightText: 2025 Dominick Johnson
# SPDX-License-Identifier: CC0-1.0

from __future__ import annotations

import pytest

from pikepdf import Name, Pdf
from pikepdf.form import (
    CheckboxField,
    ChoiceField,
    DefaultAppearanceStreamGenerator,
    ExtendedAppearanceStreamGenerator,
    Form,
    RadioButtonGroup,
    TextField,
)


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


@pytest.fixture
def va210966(resources):
    """This is a real-world fillable form with significantly more complexity than the
    basic example form above. It has examples of:

    * Combed text fields
    * Radio buttons with parent fields
    * Digital signature fields
    * Fields with an alternate name
    """
    with Pdf.open(resources / 'form_210966.pdf') as pdf:
        yield pdf


def test_form_getitem(form):
    f = Form(form)
    assert isinstance(f['Text1'], TextField)
    assert isinstance(f['Check Box3'], CheckboxField)
    assert isinstance(f['Group4'], RadioButtonGroup)


def test_form_items(form):
    f = Form(form)
    d = dict(f.items())
    assert isinstance(d['Text1'], TextField)
    assert isinstance(d['Check Box3'], CheckboxField)
    assert isinstance(d['Group4'], RadioButtonGroup)


def test_text(form):
    f = Form(form)
    field = f['Text1']
    assert field.is_multiline is False
    assert field.is_required is False
    assert field.value == ''
    field.value = 'Stuff'
    assert field.value == 'Stuff'
    assert f._acroform.needs_appearances


def test_checkbox(form):
    f = Form(form)
    field = f['Check Box3']
    assert field.checked is False
    assert field.on_value == Name.Yes
    field.checked = True
    assert field.checked is True
    assert field._field.obj.AS == Name.Yes
    field.checked = False
    assert field.checked is False


def test_radio(form):
    f = Form(form)
    field = f['Group4']
    assert field.value is None
    assert field.selected is None
    assert len(field.states) == 2
    assert len(field.options) == 2
    assert Name('/Choice1') in field.states
    assert Name('/Choice2') in field.states
    assert field.options[0].on_value == Name('/Choice1')
    assert field.options[1].on_value == Name('/Choice2')
    assert not field.options[0].checked
    assert not field.options[1].checked
    # Set value directly
    field.value = Name('/Choice1')
    assert field.value == Name('/Choice1')
    assert field.options[0].checked
    assert not field.options[1].checked
    assert field.options[0]._annot_dict.AS == Name('/Choice1')
    assert field.options[1]._annot_dict.AS == Name('/Off')
    # Using `group.selected`
    field.selected = field.options[1]
    assert field.value == Name('/Choice2')
    assert not field.options[0].checked
    assert field.options[1].checked
    assert field.options[0]._annot_dict.AS == Name('/Off')
    assert field.options[1]._annot_dict.AS == Name('/Choice2')
    # Using `option.select`
    field.options[0].select()
    assert field.value == Name('/Choice1')
    assert field.options[0].checked
    assert not field.options[1].checked
    assert field.options[0]._annot_dict.AS == Name('/Choice1')
    assert field.options[1]._annot_dict.AS == Name('/Off')
    # Using `option.checked`
    field.options[1].checked = True
    assert field.value == Name('/Choice2')
    assert not field.options[0].checked
    assert field.options[1].checked
    assert field.options[0]._annot_dict.AS == Name('/Off')
    assert field.options[1]._annot_dict.AS == Name('/Choice2')
    # We don't support directly unchecking a radio button
    with pytest.raises(ValueError):
        field.options[1].checked = False


def test_radio_with_parent(va210966):
    f = Form(va210966)
    field = f['F[0].Page_1[0].RadioButtonList[1]']
    assert field.value == Name.Off
    assert field.selected is None
    assert len(field.states) == 7
    assert len(field.options) == 7
    assert Name('/0') in field.states
    assert Name('/6') in field.states
    assert field.options[0].on_value == Name('/0')
    assert field.options[6].on_value == Name('/6')
    assert not field.options[0].checked
    assert not field.options[6].checked
    # Set value directly
    field.value = Name('/0')
    assert field.value == Name('/0')
    assert field.options[0].checked
    assert field.options[0]._annot_dict.AS == Name('/0')
    # Using `group.selected`
    field.selected = field.options[1]
    assert field.value == Name('/1')
    assert not field.options[0].checked
    assert field.options[1].checked
    assert field.options[0]._annot_dict.AS == Name('/Off')
    assert field.options[1]._annot_dict.AS == Name('/1')
    # Using `option.select`
    field.options[2].select()
    assert field.value == Name('/2')
    assert field.options[2].checked
    assert not field.options[1].checked
    assert field.options[2]._annot_dict.AS == Name('/2')
    assert field.options[1]._annot_dict.AS == Name('/Off')
    # Using `option.checked`
    field.options[3].checked = True
    assert field.value == Name('/3')
    assert not field.options[2].checked
    assert field.options[3].checked
    assert field.options[2]._annot_dict.AS == Name('/Off')
    assert field.options[3]._annot_dict.AS == Name('/3')


def test_choice(dd0293):
    f = Form(dd0293)
    field = f['form1[0].page1[0].#subform[2].DropDownList1[5]']
    assert isinstance(field, ChoiceField)
    assert field.is_combobox
    assert not field.is_multiselect
    assert not field.allow_edit
    assert field.value is None
    assert field.options[1].display_value == 'SPC1/E-1'
    assert field.options[1].export_value == 'SPC1/E-1'
    assert not field.options[1].selected
    field.value = 'SPC1/E-1'
    assert field.value == 'SPC1/E-1'
    assert f._acroform.needs_appearances
    assert field.options[1].selected
    with pytest.raises(ValueError):
        field.value = 'PVT/E-1'
    field.options[2].select()
    assert field.value == 'SPC2/E-2'


def test_signature_stamp(resources, dd0293):
    f = Form(dd0293)
    field = f['form1[0].page2[0].SignatureField1[0]']
    with Pdf.open(resources / 'pike-jp2.pdf') as sig_pdf:
        xobj_name = field.stamp_overlay(sig_pdf.pages[0])
    assert xobj_name in dd0293.pages[1].Resources.XObject
    stream = dd0293.pages[1].Contents.read_bytes()
    assert bytes(xobj_name) + b' Do' in stream


def test_signature_stamp_expand(resources, va210966):
    f = Form(va210966)
    field = f['F[0].#subform[1].Digital_Signature[0]']
    with Pdf.open(resources / 'pike-jp2.pdf') as sig_pdf:
        xobj_name = field.stamp_overlay(sig_pdf.pages[0], expand_rect=(0, 17))
    assert xobj_name in va210966.pages[1].Resources.XObject
    stream = va210966.pages[1].Contents.read_bytes()
    assert bytes(xobj_name) + b' Do' in stream


def test_default_appearance_generator_text(form):
    f = Form(form, DefaultAppearanceStreamGenerator)
    field = f['Text1']
    field.value = 'Stuff'
    assert field.value == 'Stuff'
    assert not f._acroform.needs_appearances
    stream = field._field.obj.AP.N.read_bytes()
    assert field._field.default_appearance in stream
    assert b"(Stuff)" in stream


def test_extended_appearance_generator_multiline_text(dd0293):
    text = (
        "Manual Break:\n"
        "This is a really long line designed to trigger a line break in the word-wrap "
        "code. It should totally be long enough to break to the second line. If not, "
        "we'll just type some more nonsense. Nonsense is actually sometimes quite "
        "useful. You might think I'm stalling, but actually, I'm filibustering. They're "
        "totally different things. *Wink* *Nod* *Nod off*"
    )
    f = Form(dd0293, ExtendedAppearanceStreamGenerator)
    field = f['form1[0].page2[0].TextField4[0]']
    field.value = text
    assert field.value == text
    assert not f._acroform.needs_appearances
    stream = field._field.obj.AP.N.read_bytes()
    assert field._field.default_appearance in stream
    assert b"Manual" in stream
    assert b"nonsense" in stream


def test_extended_appearance_generator_combed_text(va210966):
    f = Form(va210966, ExtendedAppearanceStreamGenerator)
    field = f['F[0].Page_1[0].Veterans_First_Name[0]']
    field.value = 'Nemo'
    assert field.value == 'Nemo'
    assert not f._acroform.needs_appearances
    stream = field._field.obj.AP.N.read_bytes()
    assert field._field.default_appearance in stream
    assert b"(N)" in stream
    assert b"(e)" in stream
    assert b"(m)" in stream
    assert b"(o)" in stream
    assert b"] TJ" in stream
