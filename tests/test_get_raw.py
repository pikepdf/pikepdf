# SPDX-FileCopyrightText: 2025 James R. Barlow
# SPDX-License-Identifier: CC0-1.0

"""Tests for Object.get_raw(), which bypasses implicit scalar conversion."""

from __future__ import annotations

from decimal import Decimal

import pytest

import pikepdf
from pikepdf import Dictionary, Name, NamePath, Object, Real


@pytest.fixture
def d():
    return Dictionary(
        Int=42,
        Real=Real('3.5'),
        Bool=True,
        Str=pikepdf.String('hello'),
        Nested=Dictionary(Inner=Dictionary(Value=7), Arr=[1, 2, 3]),
    )


class TestGetRawScalars:
    def test_int(self, d):
        v = d.get_raw('/Int')
        assert isinstance(v, Object)
        assert not isinstance(v, int)
        assert v.as_int() == 42

    def test_real(self, d):
        v = d.get_raw('/Real')
        assert isinstance(v, Object)
        assert not isinstance(v, Decimal)
        assert v.as_decimal() == Decimal('3.5')
        assert v.as_float() == pytest.approx(3.5)

    def test_bool(self, d):
        v = d.get_raw('/Bool')
        assert isinstance(v, Object)
        assert not isinstance(v, bool)
        assert v.as_bool() is True

    def test_null_is_object_not_none(self):
        # qpdf treats a dictionary key whose value is null as absent, so use an
        # array, where a stored null survives.
        darr = pikepdf.Object.parse(b'<< /Arr [ 1 null ] >>')
        assert darr.Arr[1] is None  # implicit conversion gives None
        v = darr.get_raw(NamePath('/Arr')[1])
        assert v is not None
        assert isinstance(v, Object)
        assert v._type_code == pikepdf.ObjectType.null

    def test_nonscalar_passthrough(self, d):
        v = d.get_raw('/Nested')
        assert isinstance(v, Dictionary)


class TestGetRawKeyTypes:
    def test_name_key(self, d):
        assert d.get_raw(Name.Int).as_int() == 42

    def test_namepath(self, d):
        assert d.get_raw(NamePath('/Nested')('/Inner')('/Value')).as_int() == 7

    def test_namepath_index(self, d):
        assert d.get_raw(NamePath('/Nested')('/Arr')[1]).as_int() == 2

    def test_empty_namepath_returns_self(self, d):
        v = d.get_raw(NamePath())
        assert isinstance(v, Dictionary)
        assert v == d


class TestGetRawDefaults:
    def test_missing_str_key(self, d):
        assert d.get_raw('/Nope') is None
        assert d.get_raw('/Nope', 'fallback') == 'fallback'

    def test_missing_name_key(self, d):
        assert d.get_raw(Name.Nope) is None
        assert d.get_raw(Name.Nope, 5) == 5

    def test_bad_traversal(self, d):
        assert d.get_raw(NamePath('/Int')('/Nope')) is None
        assert d.get_raw(NamePath('/Nope')('/Deeper'), 'x') == 'x'
        assert d.get_raw(NamePath('/Nested')('/Arr')[99], 'x') == 'x'


class TestGetRawModeIndependence:
    def test_explicit_mode_same_result(self, d):
        with pikepdf.explicit_conversion():
            assert isinstance(d.get_raw('/Int'), Object)
            assert d.get_raw('/Int').as_int() == 42

    def test_owned_object(self):
        pdf = pikepdf.Pdf.new()
        pdf.Root.Test = 42
        v = pdf.Root.get_raw('/Test')
        assert isinstance(v, Object)
        assert v.as_int() == 42
