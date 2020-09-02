import pytest

from pikepdf import Pdf

# pylint: disable=redefined-outer-name,pointless-statement,expression-not-assigned


@pytest.fixture
def congress(resources):
    pdf = Pdf.open(resources / 'congress.pdf')
    pdfimage = pdf.pages[0].Resources.XObject['/Im0']
    return pdfimage, pdf


def test_get_equality_stream(congress):
    image = congress[0]
    assert image.ColorSpace == image['/ColorSpace'] == image.get('/ColorSpace')
    assert image.ColorSpace == image.stream_dict.ColorSpace

    with pytest.raises(AttributeError):
        image.NoSuchKey
    with pytest.raises(KeyError):
        image['/NoSuchKey']

    image.get('/NoSuchKey', 42) == 42


def test_get_equality_dict(congress):
    page = congress[1].pages[0]

    assert page.MediaBox == page['/MediaBox'] == page.get('/MediaBox')

    with pytest.raises(RuntimeError):
        page.stream_dict
    with pytest.raises(AttributeError):
        page.NoSuchKey
    with pytest.raises(KeyError):
        page['/NoSuchKey']

    page.get('/NoSuchKey', 42) == 42
