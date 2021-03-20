import pytest

import pikepdf
from pikepdf.models import PdfMatrix


def test_init_6():
    m = PdfMatrix(1, 0, 0, 1, 0, 0)
    m2 = m.scaled(2, 2)
    m2t = m2.translated(2, 3)
    assert (
        repr(m2t)
        == 'pikepdf.Matrix(((2.0, 0.0, 0.0), (0.0, 2.0, 0.0), (2.0, 3.0, 1.0)))'
    )


def test_invalid_init():
    with pytest.raises(ValueError, match='arguments'):
        PdfMatrix('strings')


def test_matrix_from_matrix():
    m = PdfMatrix(1, 0, 0, 1, 0, 0)
    m_copy = PdfMatrix(m)
    assert m == m_copy
    assert m != 'not matrix'
