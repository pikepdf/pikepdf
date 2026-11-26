# SPDX-FileCopyrightText: 2025 Dominick Johnson
# SPDX-License-Identifier: CC0-1.0

from __future__ import annotations

from decimal import Decimal
from io import BytesIO

import pytest

import pikepdf
from pikepdf import Array, Dictionary, FormFieldFlag, Name, Pdf, String
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


def test_choice_malformed_opt(dd0293):
    """A /Opt that is not an array must not raise; the field has no options."""
    f = Form(dd0293)
    field = f['form1[0].page1[0].#subform[2].DropDownList1[5]']
    field._field.obj.Opt = String('not an array')
    assert field.options == ()
    assert field.selected is None or field.selected.export_value == field.value


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


def test_signature_stamp_once_when_annot_names_page(resources, dd0293):
    """A widget whose /P names its page is stamped once, not twice."""
    f = Form(dd0293)
    field = f['form1[0].page2[0].SignatureField1[0]']
    annot = f._acroform.get_annotations_for_field(field._field)[0]
    annot.obj.P = dd0293.pages[1].obj
    xobjects = dd0293.pages[1].Resources.get(Name.XObject)
    xobjects_before = set(xobjects.keys()) if xobjects is not None else set()
    with Pdf.open(resources / 'pike-jp2.pdf') as sig_pdf:
        xobj_name = field.stamp_overlay(sig_pdf.pages[0])
    added = set(dd0293.pages[1].Resources.XObject.keys()) - xobjects_before
    assert added == {str(xobj_name)}
    stream = dd0293.pages[1].Contents.read_bytes()
    assert stream.count(bytes(xobj_name) + b' Do') == 1


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


def test_extended_appearance_generator_explicit_mode(va210966):
    """Appearance generation lays out text with numbers, in either mode.

    The /DA font size and the font's glyph widths are read from PDF objects;
    in explicit conversion mode those must still be usable as numbers.
    """
    with pikepdf.explicit_conversion():
        f = Form(va210966, ExtendedAppearanceStreamGenerator)
        field = f['F[0].Page_1[0].Veterans_First_Name[0]']
        field.value = 'Nemo'
        assert field.value == 'Nemo'
        stream = field._field.obj.AP.N.read_bytes()
        assert b"(N)" in stream


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


def _make_text_field_pdf(max_length, *, combed, conversion_mode, child_max_length=None):
    with Pdf.new() as pdf:
        page = pdf.add_blank_page()
        parent = pdf.make_indirect(Dictionary(FT=Name.Tx, T=String('parent')))
        if max_length is not None:
            parent.MaxLen = max_length
        if combed:
            parent.Ff = int(FormFieldFlag.tx_comb)

        descriptor = pdf.make_indirect(
            Dictionary(
                Type=Name.FontDescriptor,
                FontName=Name.Helvetica,
                Flags=32,
                FontBBox=[-166, -225, 1000, 931],
                ItalicAngle=0,
                Ascent=718,
                Descent=-207,
                CapHeight=718,
                StemV=88,
            )
        )
        font = pdf.make_indirect(
            Dictionary(
                Type=Name.Font,
                Subtype=Name.Type1,
                BaseFont=Name.Helvetica,
                Encoding=Name.WinAnsiEncoding,
                FirstChar=65,
                LastChar=69,
                Widths=[667, 667, 722, 722, 667],
                FontDescriptor=descriptor,
            )
        )
        resources = Dictionary(Font=Dictionary(Helv=font))
        bbox = [0, 0, 120, 20]
        appearance = pdf.make_stream(
            b'/Tx BMC q BT /Helv 12 Tf 0 g 3 10 Td (AB) Tj ET Q EMC\n',
            Type=Name.XObject,
            Subtype=Name.Form,
            BBox=bbox,
            Resources=resources,
        )
        widget = pdf.make_indirect(
            Dictionary(
                Type=Name.Annot,
                Subtype=Name.Widget,
                T=String('code'),
                Parent=parent,
                P=page.obj,
                Rect=bbox,
                V=String('AB'),
                AP=Dictionary(N=appearance),
            )
        )
        if child_max_length is not None:
            widget.MaxLen = 1234 if child_max_length == 'null' else child_max_length
        parent.Kids = Array([widget])
        page.obj.Annots = Array([widget])
        pdf.Root.AcroForm = pdf.make_indirect(
            Dictionary(
                Fields=[parent],
                DA=String('/Helv 12 Tf 0 g'),
                DR=resources,
                NeedAppearances=False,
            )
        )
        stream = BytesIO()
        pdf.save(stream)

    data = stream.getvalue()
    if child_max_length == 'null':
        # qpdf omits null dictionary entries when saving. The replacement
        # keeps the xref offsets valid and leaves a literal null in the input.
        assert data.count(b'/MaxLen 1234') == 1
        data = data.replace(b'/MaxLen 1234', b'/MaxLen null')
    return Pdf.open(BytesIO(data), conversion_mode=conversion_mode)


@pytest.fixture(
    params=[None, DefaultAppearanceStreamGenerator, ExtendedAppearanceStreamGenerator],
    ids=['deferred', 'default', 'extended'],
)
def text_appearance_generator(request):
    return request.param


@pytest.mark.parametrize('conversion_mode', ['implicit', 'explicit'])
@pytest.mark.parametrize(
    'child_max_length, expected_limit',
    [(None, 4), ('null', 4), (2, 2)],
    ids=['inherited', 'literal-null', 'overridden'],
)
def test_combed_text_inherits_max_length(
    text_appearance_generator, conversion_mode, child_max_length, expected_limit
):
    with _make_text_field_pdf(
        4,
        combed=True,
        conversion_mode=conversion_mode,
        child_max_length=child_max_length,
    ) as pdf:
        form = Form(pdf, text_appearance_generator)
        field = form['parent.code']
        assert field.is_combed
        assert type(field.max_length) is int
        assert field.max_length == expected_limit

        value = 'ABCDE'
        field.value = value
        expected_text = value[:expected_limit]
        assert field.value == expected_text
        assert form.needs_appearances is (text_appearance_generator is None)
        stream = field.obj.AP.N.read_bytes()
        if text_appearance_generator is ExtendedAppearanceStreamGenerator:
            assert b'] TJ' in stream
            assert all(f'({char})'.encode() in stream for char in expected_text)
            assert f'({value[expected_limit]})'.encode() not in stream
        elif text_appearance_generator is DefaultAppearanceStreamGenerator:
            assert f'({expected_text}) Tj'.encode() in stream


@pytest.mark.parametrize('conversion_mode', ['implicit', 'explicit'])
@pytest.mark.parametrize('value', ['', 'ABCDE'], ids=['empty', 'truncated'])
def test_combed_text_zero_max_length(text_appearance_generator, conversion_mode, value):
    with _make_text_field_pdf(0, combed=True, conversion_mode=conversion_mode) as pdf:
        form = Form(pdf, text_appearance_generator)
        field = form['parent.code']
        assert type(field.max_length) is int
        assert field.max_length == 0

        field.value = value
        assert field.value == ''
        assert form.needs_appearances is (text_appearance_generator is None)
        if text_appearance_generator is DefaultAppearanceStreamGenerator:
            assert b'() Tj' in field.obj.AP.N.read_bytes()
        elif text_appearance_generator is ExtendedAppearanceStreamGenerator:
            assert not pikepdf.parse_content_stream(field.obj.AP.N, 'Tj TJ')


@pytest.mark.parametrize('conversion_mode', ['implicit', 'explicit'])
@pytest.mark.parametrize(
    'max_length, error, message',
    [
        pytest.param(None, ValueError, 'require /MaxLen', id='missing'),
        pytest.param(Name.Oops, TypeError, '/MaxLen must be an integer', id='name'),
        pytest.param(True, TypeError, '/MaxLen must be an integer', id='boolean'),
        pytest.param(
            Decimal('2.5'), TypeError, '/MaxLen must be an integer', id='real'
        ),
        pytest.param(-1, ValueError, 'nonnegative', id='negative'),
    ],
)
def test_combed_text_rejects_invalid_max_length(
    text_appearance_generator, conversion_mode, max_length, error, message
):
    with _make_text_field_pdf(
        max_length, combed=True, conversion_mode=conversion_mode
    ) as pdf:
        form = Form(pdf, text_appearance_generator, ignore_max_length=True)
        field = form['parent.code']
        annotation = field.obj
        old_value = annotation.V.unparse()
        old_appearance = annotation.AP.N
        old_contents = old_appearance.read_bytes()

        if max_length is None:
            assert field.max_length is None
        else:
            with pytest.raises(error, match=message):
                _ = field.max_length
        with pytest.raises(error, match=message):
            field.value = 'ABCDE'
        if text_appearance_generator is ExtendedAppearanceStreamGenerator:
            raw_field = pdf.acroform.get_fields_with_qualified_name('parent.code')[0]
            with pytest.raises(error, match=message):
                form.generate_appearances.generate_text(raw_field)

        assert annotation.V.unparse() == old_value
        assert annotation.AP.N.is_same_object_as(old_appearance)
        assert annotation.AP.N.read_bytes() == old_contents
        assert not form.needs_appearances
        assert pdf.Root.AcroForm.get_raw(Name.NeedAppearances).unparse() == b'false'


@pytest.mark.parametrize('max_length, expected', [(None, 'ABCDE'), (0, '')])
def test_noncombed_text_allows_missing_and_zero_max_length(max_length, expected):
    with _make_text_field_pdf(
        max_length, combed=False, conversion_mode='implicit'
    ) as pdf:
        field = Form(pdf)['parent.code']
        assert field.max_length == max_length
        field.value = 'ABCDE'
        assert field.value == expected


@pytest.mark.parametrize('conversion_mode', ['implicit', 'explicit'])
def test_combed_text_inherits_max_length_through_direct_parents(conversion_mode):
    with Pdf.new(conversion_mode=conversion_mode) as pdf:
        page = pdf.add_blank_page()
        ancestor = pdf.make_indirect(
            Dictionary(
                T=String('parent'),
                FT=Name.Tx,
                Ff=int(FormFieldFlag.tx_comb),
                MaxLen=4,
            )
        )
        middle = Dictionary(Parent=ancestor)
        parent = Dictionary(Parent=middle)
        widget = pdf.make_indirect(
            Dictionary(
                Subtype=Name.Widget,
                T=String('code'),
                Parent=parent,
                P=page.obj,
                Rect=[0, 0, 120, 20],
            )
        )
        page.obj.Annots = Array([widget])
        pdf.Root.AcroForm = Dictionary(Fields=[widget])

        field = Form(pdf)['parent.code']
        assert field.is_combed
        assert not field.obj.Parent.is_indirect
        assert not field.obj.Parent.Parent.is_indirect
        assert field.max_length == 4
        field.value = 'ABCDE'
        assert field.value == 'ABCD'


@pytest.mark.timeout(10, method='thread')
@pytest.mark.parametrize('parent_kind', ['direct', 'mixed', 'indirect'])
def test_text_max_length_parent_cycle(parent_kind):
    with _make_text_field_pdf(None, combed=False, conversion_mode='implicit') as pdf:
        field = Form(pdf)['parent.code']
        first = Dictionary()
        second = Dictionary()
        if parent_kind != 'direct':
            first = pdf.make_indirect(first)
        if parent_kind == 'indirect':
            second = pdf.make_indirect(second)

        field.obj.Parent = first
        first.Parent = second
        second.Parent = first
        try:
            assert field.max_length is None
        finally:
            del second.Parent
