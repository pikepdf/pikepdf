# SPDX-FileCopyrightText: 2025 James R. Barlow
# SPDX-License-Identifier: CC0-1.0

"""Tests for the mode-independent typed getters get_int(), get_bool(), etc."""

from __future__ import annotations

from decimal import Decimal

import pytest

import pikepdf
from pikepdf import Dictionary, Name, NamePath, Real


@pytest.fixture
def d():
    return Dictionary(
        Int=42,
        Real=Real('3.9'),
        Bool=True,
        Str=pikepdf.String('7'),
        Dict=Dictionary(A=1),
        List=[1, 2, 3],
        Nested=Dictionary(Inner=Dictionary(Value=7)),
    )


@pytest.fixture(
    params=['implicit', 'explicit'],
)
def mode(request):
    if request.param == 'implicit':
        with pikepdf.implicit_conversion():
            yield request.param
    else:
        with pikepdf.explicit_conversion():
            yield request.param


class TestTypedGetters:
    def test_get_int(self, d, mode):
        assert d.get_int('/Int') == 42
        assert type(d.get_int('/Int')) is int

    def test_get_bool(self, d, mode):
        assert d.get_bool('/Bool') is True

    def test_get_float(self, d, mode):
        assert d.get_float('/Real') == pytest.approx(3.9)
        assert type(d.get_float('/Real')) is float
        assert d.get_float('/Int') == pytest.approx(42.0)

    def test_get_decimal(self, d, mode):
        assert d.get_decimal('/Real') == Decimal('3.9')

    def test_get_dict(self, d, mode):
        assert dict(d.get_dict('/Dict')) == {'/A': 1}

    def test_get_list(self, d, mode):
        assert list(d.get_list('/List')) == [1, 2, 3]

    def test_missing_key_returns_default(self, d, mode):
        assert d.get_int('/Nope') is None
        assert d.get_bool('/Nope', False) is False
        assert d.get_float('/Nope', 1.5) == 1.5
        assert d.get_decimal('/Nope', Decimal(1)) == Decimal(1)
        assert d.get_dict('/Nope') is None
        assert d.get_list('/Nope', []) == []

    def test_type_mismatch_returns_default(self, d, mode):
        assert d.get_int('/Str') is None
        assert d.get_int('/Str', -1) == -1
        assert d.get_bool('/Int', False) is False
        assert d.get_float('/Str', 0.0) == 0.0
        assert d.get_decimal('/Int', None) is None
        assert d.get_dict('/List', {}) == {}
        assert d.get_list('/Dict', []) == []

    def test_coerce(self, d, mode):
        assert d.get_int('/Real', coerce=True) == 3
        assert d.get_int('/Str', coerce=True) == 7
        assert d.get_bool('/Int', coerce=True) is True
        assert d.get_float('/Str', coerce=True) == pytest.approx(7.0)
        assert d.get_decimal('/Int', coerce=True) == Decimal(42)
        # Missing key still returns default even with coerce
        assert d.get_int('/Nope', 5, coerce=True) == 5

    def test_coerce_is_keyword_only(self, d, mode):
        with pytest.raises(TypeError):
            d.get_int('/Real', None, True)  # type: ignore[misc]

    def test_dict_list_have_no_coerce(self, d, mode):
        with pytest.raises(TypeError):
            d.get_dict('/List', coerce=True)  # type: ignore[call-arg]
        with pytest.raises(TypeError):
            d.get_list('/Dict', coerce=True)  # type: ignore[call-arg]


class TestTypedGetterKeys:
    def test_str_key(self, d):
        assert d.get_int('/Int') == 42

    def test_name_key(self, d):
        assert d.get_int(Name.Int) == 42
        assert d.get_bool(Name.Bool) is True
        assert dict(d.get_dict(Name.Dict)) == {'/A': 1}

    def test_namepath_key(self, d):
        assert d.get_int(NamePath('/Nested')('/Inner')('/Value')) == 7
        assert d.get_int(NamePath('/Nested')('/Inner')('/Nope'), -1) == -1
        assert dict(d.get_dict(NamePath('/Nested')('/Inner'))) == {'/Value': 7}

    def test_namepath_index_key(self):
        d = Dictionary(Arr=[1, Real('2.5')])
        assert d.get_int(NamePath('/Arr')[0]) == 1
        assert d.get_float(NamePath('/Arr')[1]) == pytest.approx(2.5)
        assert d.get_int(NamePath('/Arr')[5], -1) == -1


class TestTypedGettersPerPdfMode:
    @pytest.mark.parametrize('conversion_mode', [None, 'implicit', 'explicit'])
    def test_per_pdf_mode(self, conversion_mode):
        pdf = pikepdf.Pdf.new(conversion_mode=conversion_mode)
        pdf.Root.Meta = Dictionary(Count=5, Ratio=Real('0.25'), Flag=True)
        meta = pdf.Root.get_raw('/Meta')
        assert meta.get_int('/Count') == 5
        assert type(meta.get_int('/Count')) is int
        assert meta.get_float('/Ratio') == pytest.approx(0.25)
        assert meta.get_bool('/Flag') is True
        assert meta.get_decimal('/Ratio') == Decimal('0.25')
        assert meta.get_int('/Nope', 0) == 0

    def test_stream_dict(self):
        pdf = pikepdf.Pdf.new(conversion_mode='explicit')
        stream = pikepdf.Stream(pdf, b'abc', Width=100)
        assert stream.get_int('/Width') == 100
        assert type(stream.get_int('/Width')) is int
