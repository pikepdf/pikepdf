"""
Test IPython/Jupyter display hooks
"""

import pytest

import pikepdf


@pytest.fixture
def pal(resources):
    return pikepdf.open(resources / 'pal-1bit-trivial.pdf')


def test_display_page(pal):
    page0 = pal.pages[0]
    mimebundle = page0._repr_mimebundle_(include=None, exclude=None)
    assert 'application/pdf' in mimebundle


def test_display_image(pal):
    im0 = pal.pages[0].Resources.XObject['/Im0']
    pim = pikepdf.PdfImage(im0)
    result = pim._repr_png_()
    assert result[1:4] == b'PNG'


def test_display_pdf(pal):
    mimebundle = pal._repr_mimebundle_(
        include=['application/pdf'], exclude=['text/css']
    )
    assert 'application/pdf' in mimebundle and mimebundle['application/pdf'].startswith(
        b'%PDF'
    )


def test_object_key_completion(pal):
    page0 = pal.pages[0]
    assert '/Type' in page0._ipython_key_completions_()
