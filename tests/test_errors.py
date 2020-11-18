import pytest

from pikepdf import Pdf


@pytest.fixture
def vera(resources):
    # A file that is not linearized
    return Pdf.open(resources / 'veraPDF test suite 6-2-10-t02-pass-a.pdf')


def test_foreign_linearization(vera):
    assert not vera.is_linearized
    with pytest.raises(RuntimeError, match="not linearized"):
        vera.check_linearization()
