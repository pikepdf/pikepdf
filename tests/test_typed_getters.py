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
        Text=pikepdf.String('héllo'),
        Binary=pikepdf.String(b'\x80\x81\xff'),
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

    def test_get_str(self, d, mode):
        assert d.get_str('/Text') == 'héllo'
        assert type(d.get_str('/Text')) is str

    def test_get_bytes(self, d, mode):
        assert d.get_bytes('/Binary') == b'\x80\x81\xff'
        assert type(d.get_bytes('/Binary')) is bytes
        assert d.get_bytes('/Text') == b'h\xe9llo'

    def test_missing_key_returns_default(self, d, mode):
        assert d.get_int('/Nope') is None
        assert d.get_bool('/Nope', False) is False
        assert d.get_float('/Nope', 1.5) == 1.5
        assert d.get_decimal('/Nope', Decimal(1)) == Decimal(1)
        assert d.get_dict('/Nope') is None
        assert d.get_list('/Nope', []) == []
        assert d.get_str('/Nope') is None
        assert d.get_bytes('/Nope', b'') == b''

    def test_type_mismatch_returns_default(self, d, mode):
        assert d.get_int('/Str') is None
        assert d.get_int('/Str', -1) == -1
        assert d.get_bool('/Int', False) is False
        assert d.get_float('/Str', 0.0) == 0.0
        assert d.get_decimal('/Int', None) is None
        assert d.get_dict('/List', {}) == {}
        assert d.get_list('/Dict', []) == []
        assert d.get_str('/Int') is None
        assert d.get_str('/Dict', '') == ''
        assert d.get_bytes('/Int', b'') == b''

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
        with pytest.raises(TypeError):
            d.get_str('/Str', coerce=True)  # type: ignore[call-arg]
        with pytest.raises(TypeError):
            d.get_bytes('/Str', coerce=True)  # type: ignore[call-arg]


class TestTypedGetterKeys:
    def test_str_key(self, d):
        assert d.get_int('/Int') == 42

    def test_name_key(self, d):
        assert d.get_int(Name.Int) == 42
        assert d.get_str(Name.Text) == 'héllo'
        assert d.get_bool(Name.Bool) is True
        assert dict(d.get_dict(Name.Dict)) == {'/A': 1}

    def test_namepath_key(self, d):
        assert d.get_int(NamePath('/Nested')('/Inner')('/Value')) == 7
        assert d.get_int(NamePath('/Nested')('/Inner')('/Nope'), -1) == -1
        assert dict(d.get_dict(NamePath('/Nested')('/Inner'))) == {'/Value': 7}
        assert d.get_bytes(NamePath('/Binary')) == b'\x80\x81\xff'

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


class TestTypedGetterEdgeCases:
    def test_keyword_arguments(self, d):
        assert d.get_int(key='/Int', default=0) == 42
        assert d.get_int('/Nope', default=0) == 0
        assert d.get_list(key='/Nope', default=[]) == []

    def test_default_returned_as_is(self, d):
        sentinel = object()
        for getter in ('get_int', 'get_bool', 'get_float', 'get_decimal'):
            assert getattr(d, getter)('/Nope', sentinel) is sentinel
            assert getattr(d, getter)('/Dict', sentinel, coerce=True) is sentinel
        assert d.get_dict('/List', sentinel) is sentinel
        assert d.get_list('/Dict', sentinel) is sentinel
        assert d.get_str('/Int', sentinel) is sentinel
        assert d.get_bytes('/Nope', sentinel) is sentinel

    def test_key_holding_null_is_absent(self, mode):
        d = pikepdf.Object.parse(b'<< /N null >>')
        assert d.get_int('/N', -1) == -1

    def test_non_container_receiver_returns_default(self):
        assert pikepdf.Array([1, 2]).get_int('/Int', -1) == -1
        assert pikepdf.Array([1, 2]).get_int(Name.Int, -1) == -1
        assert pikepdf.Array([1, 2]).get_int(NamePath('/Int'), -1) == -1

    def test_empty_namepath_reads_self(self, d):
        assert d.get_raw('/Int').get_int(NamePath()) == 42
        assert dict(d.get_raw('/Dict').get_dict(NamePath())) == {'/A': 1}

    def test_invalid_key_type(self, d):
        with pytest.raises(TypeError):
            d.get_int(42)  # type: ignore[arg-type]
        with pytest.raises(TypeError):
            d.get_list(None)  # type: ignore[arg-type]

    def test_overflow_without_coerce_still_default(self):
        d = Dictionary(S=pikepdf.String('99999999999999999999'))
        assert d.get_int('/S', 0) == 0
