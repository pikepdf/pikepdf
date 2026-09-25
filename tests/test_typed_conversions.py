# SPDX-FileCopyrightText: 2026 James R. Barlow
# SPDX-License-Identifier: CC0-1.0

"""Tests for the module-level typed conversions pikepdf.as_int() and friends."""

from __future__ import annotations

from decimal import Decimal

import pytest

import pikepdf
from pikepdf import Array, Dictionary, Name, Real, String

pytestmark = pytest.mark.abi3_smoke

MISS = object()  # the default; expected wherever a conversion refuses the value

KEYS = ['/A', '/B', '/C', '/D', '/E', '/F', '/G']


@pytest.fixture(params=['implicit', 'explicit'])
def mode(request):
    ctx = (
        pikepdf.implicit_conversion
        if request.param == 'implicit'
        else pikepdf.explicit_conversion
    )
    with ctx():
        yield request.param


@pytest.fixture
def d():
    return Dictionary(
        A=1,
        B=True,
        C=Real('1.5'),
        D=String('x'),
        E=String(b'x'),
        F=[1],
        G={'/X': 1},
    )


@pytest.fixture
def stream():
    pdf = pikepdf.Pdf.new()
    return pikepdf.Stream(pdf, b'abc', Width=1)


# Expected result of each conversion for each key of the fixture dictionary,
# read with d[key] so that the value is native in implicit mode and an Object
# in explicit mode. Keys that are absent from a row give the default.
FROM_DICT = {
    'as_int': {'/A': 1},
    'as_bool': {'/B': True},
    'as_float': {'/A': 1.0, '/C': 1.5},
    'as_decimal': {'/C': Decimal('1.5')},
    'as_str': {'/D': 'x', '/E': 'x'},
    'as_bytes': {'/D': b'x', '/E': b'x'},
}
FROM_DICT_COERCED = {
    'as_int': {'/A': 1, '/C': 1},
    'as_bool': {'/A': True, '/B': True, '/C': True},
    'as_float': {'/A': 1.0, '/C': 1.5},
    'as_decimal': {'/A': Decimal(1), '/C': Decimal('1.5')},
}

NATIVE = [None, 1, True, 1.5, Decimal('1.5'), 'x', b'x', [1], {}]
# Lists of (value, result) pairs rather than dicts: 1 == True == 1.0 and
# 1.5 == Decimal('1.5'), so they would collide as dict keys.
FROM_NATIVE = {
    'as_int': [(1, 1)],
    'as_bool': [(True, True)],
    'as_float': [(1, 1.0), (1.5, 1.5), (Decimal('1.5'), 1.5)],
    'as_decimal': [(1.5, Decimal('1.5')), (Decimal('1.5'), Decimal('1.5'))],
    'as_dict': [],
    'as_list': [],
    'as_str': [('x', 'x')],
    'as_bytes': [(b'x', b'x')],
}
FROM_NATIVE_COERCED = {
    'as_int': [(1, 1), (1.5, 1), (Decimal('1.5'), 1)],
    'as_bool': [(True, True), (1, True), (1.5, True), (Decimal('1.5'), True)],
    'as_float': [(1, 1.0), (1.5, 1.5), (Decimal('1.5'), 1.5)],
    'as_decimal': [
        (1, Decimal(1)),
        (1.5, Decimal('1.5')),
        (Decimal('1.5'), Decimal('1.5')),
    ],
}

ALL = list(FROM_NATIVE)
COERCING = list(FROM_NATIVE_COERCED)


def _lookup(pairs, value):
    for k, v in pairs:
        if type(k) is type(value) and k == value:
            return v
    return MISS


def _check(result, expected):
    if expected is MISS:
        assert result is MISS
    else:
        assert type(result) is type(expected)
        assert result == expected


@pytest.mark.parametrize('fn', ALL)
@pytest.mark.parametrize('key', KEYS)
def test_value_read_from_dictionary(d, mode, fn, key):
    value = d[key]
    result = getattr(pikepdf, fn)(value, MISS)
    if fn == 'as_dict':
        if key == '/G':
            assert dict(result) == {'/X': 1}
        else:
            assert result is MISS
        return
    if fn == 'as_list':
        if key == '/F':
            assert list(result) == [1]
        else:
            assert result is MISS
        return
    _check(result, FROM_DICT[fn].get(key, MISS))


@pytest.mark.parametrize('fn', COERCING)
@pytest.mark.parametrize('key', KEYS)
def test_value_read_from_dictionary_coerced(d, mode, fn, key):
    result = getattr(pikepdf, fn)(d[key], MISS, coerce=True)
    _check(result, FROM_DICT_COERCED[fn].get(key, MISS))


@pytest.mark.parametrize('fn', ALL)
@pytest.mark.parametrize('key', KEYS)
def test_matches_typed_getter(d, mode, fn, key):
    getter = getattr(d, 'get_' + fn.removeprefix('as_'))
    result = getattr(pikepdf, fn)(d[key], MISS)
    expected = getter(key, MISS)
    if fn in ('as_dict', 'as_list') and expected is not MISS:
        assert type(result) is type(expected)
        assert list(result) == list(expected)
    else:
        assert result == expected
        assert type(result) is type(expected)


@pytest.mark.parametrize('fn', COERCING)
@pytest.mark.parametrize('key', KEYS)
def test_matches_typed_getter_coerced(d, mode, fn, key):
    getter = getattr(d, 'get_' + fn.removeprefix('as_'))
    result = getattr(pikepdf, fn)(d[key], MISS, coerce=True)
    expected = getter(key, MISS, coerce=True)
    assert result == expected
    assert type(result) is type(expected)


@pytest.mark.parametrize('fn', ALL)
@pytest.mark.parametrize('value', NATIVE, ids=repr)
def test_native_value(fn, value):
    _check(getattr(pikepdf, fn)(value, MISS), _lookup(FROM_NATIVE[fn], value))


@pytest.mark.parametrize('fn', COERCING)
@pytest.mark.parametrize('value', NATIVE, ids=repr)
def test_native_value_coerced(fn, value):
    result = getattr(pikepdf, fn)(value, MISS, coerce=True)
    _check(result, _lookup(FROM_NATIVE_COERCED[fn], value))


@pytest.mark.parametrize('fn', ALL)
def test_name_and_stream_give_default(fn, stream):
    assert getattr(pikepdf, fn)(Name.X, MISS) is MISS
    assert getattr(pikepdf, fn)(stream, MISS) is MISS


@pytest.mark.parametrize('fn', ALL)
def test_default_defaults_to_none(fn):
    assert getattr(pikepdf, fn)(Name.X) is None
    assert getattr(pikepdf, fn)(None) is None


@pytest.mark.parametrize('fn', ALL)
def test_default_returned_by_identity(fn):
    sentinel = object()
    assert getattr(pikepdf, fn)(None, sentinel) is sentinel
    assert getattr(pikepdf, fn)(object(), sentinel) is sentinel
    assert getattr(pikepdf, fn)(value=None, default=sentinel) is sentinel


def test_bool_is_not_int():
    assert pikepdf.as_int(True) is None
    assert pikepdf.as_int(pikepdf.Boolean(True)) is None
    assert pikepdf.as_int(True, coerce=True) is None
    assert pikepdf.as_float(True) is None
    assert pikepdf.as_decimal(False, coerce=True) is None


def test_coerce_mirrors_object_methods():
    assert pikepdf.as_int(Real('2.7'), coerce=True) == 2
    assert pikepdf.as_int(2.7, coerce=True) == 2
    assert pikepdf.as_int(Decimal('-2.7'), coerce=True) == -2
    assert pikepdf.as_bool(1, coerce=True) is True
    assert pikepdf.as_bool(0, coerce=True) is False
    assert pikepdf.as_bool(0.0, coerce=True) is False
    assert pikepdf.as_int(String('12'), coerce=True) == 12
    assert pikepdf.as_int('12', coerce=True) == 12
    assert pikepdf.as_int('12') is None
    assert pikepdf.as_float('2.5', coerce=True) == 2.5
    assert pikepdf.as_decimal('2.50', coerce=True) == Decimal('2.50')
    assert pikepdf.as_bool('1', coerce=True) is None


def test_coerce_is_keyword_only():
    with pytest.raises(TypeError):
        pikepdf.as_int(1.5, None, True)  # type: ignore[misc]


@pytest.mark.parametrize('fn', ['as_dict', 'as_list', 'as_str', 'as_bytes'])
def test_no_coerce(fn):
    with pytest.raises(TypeError):
        getattr(pikepdf, fn)(1, coerce=True)


def test_non_finite_numbers_give_default():
    for value in (float('nan'), float('inf'), Decimal('NaN'), Decimal('-Infinity')):
        assert pikepdf.as_float(value) is None
        assert pikepdf.as_decimal(value) is None
        assert pikepdf.as_int(value, coerce=True) is None
        assert pikepdf.as_bool(value, coerce=True) is None


def test_out_of_range_int_gives_default():
    assert pikepdf.as_int(2**70) is None
    assert pikepdf.as_int(-(2**70), -1) == -1
    assert pikepdf.as_int(1e30, coerce=True) is None


def test_decimal_precision_preserved():
    value = Decimal('1.23456789012345678901234567890')
    assert pikepdf.as_decimal(value) == value
    assert str(pikepdf.as_decimal(value)) == str(value)


def test_str_and_bytes_are_not_interchangeable():
    assert pikepdf.as_str(b'x') is None
    assert pikepdf.as_bytes('x') is None
    assert pikepdf.as_str('\udc80') == '\udc80'


def test_containers():
    arr = Array([1, 2])
    d = Dictionary(A=1)
    assert list(pikepdf.as_list(arr)) == [1, 2]
    assert dict(pikepdf.as_dict(d)) == {'/A': 1}
    assert pikepdf.as_list(d) is None
    assert pikepdf.as_dict(arr) is None
    assert pikepdf.as_list((1, 2)) is None


def test_exported():
    for fn in ALL:
        assert fn in pikepdf.__all__
