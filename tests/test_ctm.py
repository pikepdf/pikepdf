# SPDX-FileCopyrightText: 2025 rakurtz, James R. Barlow
# SPDX-License-Identifier: CC0-1.0
from __future__ import annotations

import pytest

from pikepdf import Matrix, Pdf, get_objects_with_ctm
from pikepdf.models.ctm import MatrixStack


# Crafted test PDF that contains 4 'Do' (Draw Object) operations
# However only three of those have a valid CTM
# First: 'Do' without previous 'cm' operation
# Second: 'Do' with 'cm' operation (100 0 0 100 100 100 cm)
# Third: 'Do' preceed by invalid 'cm' operation (0 cm)
# Fourth: 'Do' after invalid CTM has been popped off stack
@pytest.fixture
def ctm_cm(resources):
    with Pdf.open(resources / 'ctm_cm.pdf') as pdf:
        yield pdf


def test_get_matrices(ctm_cm):
    matrixes = [matrix for _, matrix in get_objects_with_ctm(ctm_cm.pages[0])]

    first = Matrix(1, 0, 0, 1, 0, 0)  # identity matrix
    second = Matrix(100, 0, 0, 100, 100, 100)
    # third drawn object doesn't have a valid CTM and is skipped
    fourth = Matrix(2, 0, 0, 2, 2, 2)

    assert len(matrixes) == 3
    assert matrixes[0] == first
    assert matrixes[1] == second
    assert matrixes[2] == second @ fourth


def test_get_matrices_scaled(ctm_cm):
    scale = Matrix(7, 0, 0, 7, 0, 0)
    matrixes = [matrix for _, matrix in get_objects_with_ctm(ctm_cm.pages[0], scale)]

    first = scale
    second = Matrix(700, 0, 0, 700, 100, 100)
    # third drawn object doesn't have a valid CTM and is skipped
    fourth = Matrix(2, 0, 0, 2, 2, 2)

    assert len(matrixes) == 3
    assert matrixes[0] == first
    assert matrixes[1] == second
    assert matrixes[2] == second @ fourth


def test_underflow():
    stack = MatrixStack()
    for _ in range(4):
        stack.pop()
    assert stack.ctm == Matrix.identity()


def test_invalid_ctm():
    stack = MatrixStack()
    stack.invalidate_current_transformation_matrix()
    assert stack.ctm is None
