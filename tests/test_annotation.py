import pytest
from conftest import needs_libqpdf_v

from pikepdf import Annotation, Dictionary, Name, Pdf


@pytest.fixture
def form(resources):
    yield Pdf.open(resources / 'form.pdf')


@needs_libqpdf_v('10.3.0', reason="decimal -> integer truncation")
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


@needs_libqpdf_v('10.3.0', reason="decimal -> integer truncation")
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
