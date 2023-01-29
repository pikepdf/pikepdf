# SPDX-FileCopyrightText: 2022 James R. Barlow
# SPDX-License-Identifier: CC0-1.0

from __future__ import annotations

from math import isclose

import pytest

from pikepdf.models import PdfMatrix


def test_init_6():
    m = PdfMatrix(1, 0, 0, 1, 0, 0)
    m2 = m.scaled(2, 2)
    m2t = m2.translated(2, 3)
    assert (
        repr(m2t)
        == 'pikepdf.PdfMatrix(((2.0, 0.0, 0.0), (0.0, 2.0, 0.0), (2.0, 3.0, 1.0)))'
    )
    m2tr = m2t.rotated(90)
    assert isclose(m2tr.a, 0, abs_tol=1e-6)
    assert isclose(m2tr.b, 2, abs_tol=1e-6)
    assert isclose(m2tr.c, -2, abs_tol=1e-6)
    assert isclose(m2tr.d, 0, abs_tol=1e-6)
    assert isclose(m2tr.e, -3, abs_tol=1e-6)
    assert isclose(m2tr.f, 2, abs_tol=1e-6)


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
