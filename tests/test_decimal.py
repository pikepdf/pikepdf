# SPDX-FileCopyrightText: 2022 James R. Barlow
# SPDX-License-Identifier: CC0-1.0

from __future__ import annotations

from decimal import Decimal, getcontext

import pytest

import pikepdf
from pikepdf.settings import get_decimal_precision, set_decimal_precision

encode = pikepdf._core._encode

# pylint: disable=redefined-outer-name


def test_decimal_precision():
    d = Decimal('0.1234567890123456789')
    assert str(encode(d)) == '0.123456789012346'


def test_decimal_change_precision():
    d = Decimal('0.1234567890123456789')
    saved = get_decimal_precision()
    try:
        set_decimal_precision(10)
        assert str(encode(d)) == '0.1234567890'
        assert get_decimal_precision() == 10
    finally:
        set_decimal_precision(saved)


def test_decimal_independent_of_app():
    d = Decimal('0.1234567890123456789')
    pikepdf_prec = get_decimal_precision()
    decimal_prec = getcontext().prec
    try:
        getcontext().prec = 6
        set_decimal_precision(8)
        assert str(encode(d)) == '0.12345679'
        assert get_decimal_precision() != 6
    finally:
        set_decimal_precision(pikepdf_prec)
        getcontext().prec = decimal_prec


@pytest.fixture
def pal(resources):
    return pikepdf.open(resources / 'pal-1bit-trivial.pdf')


def test_output_rounded(pal, outdir):
    pal.pages[0].MediaBox[2] = pal.pages[0].MediaBox[2] * Decimal(
        '1.2345678912345678923456789123456789'
    )
    pal.save(outdir / 'round.pdf')

    with pikepdf.open(outdir / 'round.pdf') as pdf:
        assert len(str(pdf.pages[0].MediaBox[2])) == 16


def test_nonfinite(pal):
    with pytest.raises(ValueError):
        pal.pages[0].MediaBox[2] = Decimal('NaN')
    with pytest.raises(ValueError):
        pal.pages[0].MediaBox[2] = Decimal('Infinity')
    with pytest.raises(ValueError):
        pal.pages[0].MediaBox[2] = float('NaN')
    with pytest.raises(ValueError):
        pal.pages[0].MediaBox[2] = float('Infinity')
