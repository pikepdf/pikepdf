import io

import pytest

import pikepdf
from pikepdf.form import Form


def test_duplicate_text_fields_and_proxy_behavior():
    """
    Covers:
    - Basic duplicate handling (Text fields)
    - MultipleFieldProxy.__getattr__
    - MultipleFieldProxy.__setattr__ (both proxy and local)
    - MultipleFieldProxy.__repr__
    - Form.__getitem__ (success and KeyError)
    - Form.items() (standard deduplication)
    """
    pdf = pikepdf.new()
    pdf.add_blank_page()

    # Create two Text fields with the same name
    data1 = pikepdf.Dictionary(
        Type=pikepdf.Name.Annot,
        Subtype=pikepdf.Name.Widget,
        FT=pikepdf.Name.Tx,
        T="MyDuplicate",
        V="ValueOne",
        Rect=[0, 0, 100, 100],
    )
    data2 = pikepdf.Dictionary(
        Type=pikepdf.Name.Annot,
        Subtype=pikepdf.Name.Widget,
        FT=pikepdf.Name.Tx,
        T="MyDuplicate",
        V="ValueTwo",
        Rect=[100, 100, 200, 200],
    )

    ind1 = pdf.make_indirect(data1)
    ind2 = pdf.make_indirect(data2)

    pdf.pages[0].Annots = [ind1, ind2]
    pdf.Root.AcroForm = pdf.make_indirect(pikepdf.Dictionary(Fields=[ind1, ind2]))

    # Reload to simulate opening file
    stream = io.BytesIO()
    pdf.save(stream)
    stream.seek(0)
    pdf = pikepdf.open(stream)
    form = Form(pdf)

    # 1. Test Proxy Access
    field = form["MyDuplicate"]
    assert isinstance(field, list)
    assert len(field) == 2
    assert field.value == "ValueOne"  # Proxy read

    # 2. Test Proxy Write (Line 47-50)
    field.value = "NewValue"
    assert field[0].value == "NewValue"

    # 3. Test Proxy Local Attribute (Line 51-53)
    # Setting an attribute that DOES NOT exist on the field should set it on the list object
    field._local_python_attr = "I am a list attribute"
    assert field._local_python_attr == "I am a list attribute"
    assert not hasattr(
        field[0], "_local_python_attr"
    )  # Ensure it didn't leak to the PDF object

    # 4. Test Repr (Line 55-56)
    assert "MultipleFieldProxy" in repr(field)

    # 5. Test KeyError (Line 113-114)
    with pytest.raises(KeyError):
        _ = form["NonExistentField"]

    # 6. Test Basic Iteration (Line 165-167)
    # For text fields, it should yield the first one and skip the second
    items = list(form.items())
    assert len(items) == 1
    assert items[0][0] == "MyDuplicate"


def test_duplicate_radio_buttons():
    """
    Covers:
    - Form.items() specific logic for Radio Buttons (Lines 148-164)
    """
    pdf = pikepdf.new()
    pdf.add_blank_page()

    # Radio Button Flag = 1 << 15 (32768)
    # We need duplicates to trigger the special block in items()
    radio1 = pikepdf.Dictionary(
        Type=pikepdf.Name.Annot,
        Subtype=pikepdf.Name.Widget,
        FT=pikepdf.Name.Btn,
        Ff=32768,
        T="MyRadioGroup",
        V=pikepdf.Name.Yes,
        Rect=[0, 0, 100, 100],
    )
    radio2 = pikepdf.Dictionary(
        Type=pikepdf.Name.Annot,
        Subtype=pikepdf.Name.Widget,
        FT=pikepdf.Name.Btn,
        Ff=32768,
        T="MyRadioGroup",  # Duplicate name
        V=pikepdf.Name.Off,
        Rect=[100, 100, 200, 200],
    )

    ind1 = pdf.make_indirect(radio1)
    ind2 = pdf.make_indirect(radio2)

    pdf.pages[0].Annots = [ind1, ind2]
    pdf.Root.AcroForm = pdf.make_indirect(pikepdf.Dictionary(Fields=[ind1, ind2]))

    stream = io.BytesIO()
    pdf.save(stream)
    stream.seek(0)
    pdf = pikepdf.open(stream)
    form = Form(pdf)

    # This specific call triggers the logic at lines 159-162
    # (Handling duplicate radio buttons during iteration)
    items = list(form.items())

    assert len(items) == 1
    name, field = items[0]
    assert name == "MyRadioGroup"
    assert isinstance(field, list)  # Should be proxied
    assert len(field) == 2
