import io

import pikepdf
from pikepdf.form import Form


def test_duplicate_fields_are_proxied():
    pdf = pikepdf.new()
    pdf.add_blank_page()

    data1 = pikepdf.Dictionary(
        Type=pikepdf.Name.Annot,
        Subtype=pikepdf.Name.Widget,
        FT=pikepdf.Name.Tx,
        T="MyDuplicate",
        V="ValueOne",
        Rect=[0, 0, 100, 100]
    )

    data2 = pikepdf.Dictionary(
        Type=pikepdf.Name.Annot,
        Subtype=pikepdf.Name.Widget,
        FT=pikepdf.Name.Tx,
        T="MyDuplicate",
        V="ValueTwo",
        Rect=[100, 100, 200, 200]
    )

    ind_widget1 = pdf.make_indirect(data1)
    ind_widget2 = pdf.make_indirect(data2)

    # Link these same indirect objects to both Page and AcroForm
    pdf.pages[0].Annots = [ind_widget1, ind_widget2]

    pdf.Root.AcroForm = pdf.make_indirect(
        pikepdf.Dictionary(Fields=[ind_widget1, ind_widget2])
    )

    # Cycle through save/load to force QPDF to re-parse the structure
    stream = io.BytesIO()
    pdf.save(stream)
    stream.seek(0)
    pdf_reloaded = pikepdf.open(stream)

    # The Tests
    form = Form(pdf_reloaded)

    # Should not crash
    field = form['MyDuplicate']

    # Should be a list (Proxy)
    assert isinstance(field, list)
    assert len(field) == 2

    # Should act like the first field (ValueOne)
    assert field.value == "ValueOne"

    # Should allow access to the second field
    assert field[1].value == "ValueTwo"

    # Iteration check
    items = list(form.items())
    assert len(items) == 1
    assert items[0][0] == "MyDuplicate"
