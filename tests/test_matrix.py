# SPDX-FileCopyrightText: 2022 James R. Barlow
# SPDX-License-Identifier: CC0-1.0

from __future__ import annotations

from math import isclose

import pytest

from pikepdf.models import PdfMatrix


def allclose(m1, m2, abs_tol=1e-6):
    return all(
        isclose(x, y, abs_tol=abs_tol) for x, y in zip(m1.shorthand, m2.shorthand)
    )


def test_init_6():
    m = PdfMatrix(1, 0, 0, 1, 0, 0)
    m2 = m.scaled(2, 2)
    m2t = m2.translated(2, 3)
    assert (
        repr(m2t)
        == 'pikepdf.PdfMatrix(((2.0, 0.0, 0.0), (0.0, 2.0, 0.0), (2.0, 3.0, 1.0)))'
    )
    m2tr = m2t.rotated(90)
    expected = PdfMatrix(0, 2, -2, 0, -3, 2)
    assert allclose(m2tr, expected)


def test_invalid_init():
    with pytest.raises(ValueError, match='arguments'):
        PdfMatrix('strings')


def test_matrix_from_matrix():
    m = PdfMatrix(1, 0, 0, 1, 0, 0)
    m_copy = PdfMatrix(m)
    assert m == m_copy
    assert m != 'not matrix'


def test_matrix_encode():
    m = PdfMatrix(1, 0, 0, 1, 0, 0)
    assert m.encode() == b'1.000000 0.000000 0.000000 1.000000 0.000000 0.000000'


def test_matrix_inverse():
    pytest.importorskip('numpy')

    m = PdfMatrix(2, 0, 0, 1, 0, 3)
    minv_m = m.inverse() @ m
    assert allclose(minv_m, PdfMatrix.identity())


def test_numpy():
    np = pytest.importorskip('numpy')

    m = PdfMatrix(1, 0, 0, 2, 7, 0)
    m2 = PdfMatrix(np.array([[1, 0, 0], [0, 2, 0], [7, 0, 1]]))
    assert m == m2
    arr = np.array(m)
    arr2 = np.array(m2)
    assert np.array_equal(arr, arr2)
