"""
Test IPython/Jupyter display hooks
"""

import pikepdf
import pytest


@pytest.fixture
def graph(resources):
    return pikepdf.open(resources / 'graph.pdf')


def test_display_page(graph):
    page0 = graph.pages[0]
    mimebundle = page0._repr_mimebundle_(include=None, exclude=None)
    assert 'application/pdf' in mimebundle


def test_display_image(graph):
    im0 = graph.pages[0].Resources.XObject['/Im0']
    pim = pikepdf.PdfImage(im0)
    result = pim._repr_png_()
    assert result[1:4] == b'PNG'
