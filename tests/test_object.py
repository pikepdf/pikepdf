from decimal import Decimal
from math import isclose, isfinite
from pikepdf import _qpdf as qpdf, Pdf
from hypothesis import given, strategies as st, example
from hypothesis.strategies import (none, integers, binary, lists, floats, 
    characters, recursive, booleans)
import pytest


encode = qpdf._encode
decode = qpdf._decode


def decode_encode(obj):
    return decode(encode(obj))


def test_bool_involution():
    assert decode_encode(True) == True
    assert decode_encode(False) == False


@given(integers(min_value=-2**31, max_value=(2**31-1)))
def test_integer_involution(n):
    assert decode_encode(n) == n


@given(characters(min_codepoint=0x20, max_codepoint=0x7f))
@example('')
def test_ascii_involution(ascii):
    b = ascii.encode('ascii')
    assert decode_encode(b) == b


@given(binary(min_size=0, max_size=10000, average_size=10))
def test_binary_involution(binary):
    assert decode_encode(binary) == binary


@given(integers(-10**12, 10**12), integers(-10**12, 10**12))
def test_integer_comparison(a, b):
    equals = (a == b)
    encoded_equals = (qpdf._encode(a) == qpdf._encode(b))
    assert encoded_equals == equals

    lessthan = (a < b)
    encoded_lessthan = (qpdf._encode(a) < qpdf._encode(b))
    assert lessthan == encoded_lessthan


@given(integers(max_value=9223372036854775807), integers(max_value=9223372036854775807))
def test_crosstype_comparison(a, b):
    equals = (a == b)
    encoded_equals = (a == qpdf._encode(b))
    assert encoded_equals == equals

    lessthan = (a < b)
    encoded_lessthan = (qpdf._encode(a) < b)
    assert lessthan == encoded_lessthan


@given(integers(-10**12, 10**12), integers(0, 12))
def test_decimal_involution(num, radix):
    strnum = str(num)
    if radix > len(strnum):
        strnum = strnum[:radix] + '.' + strnum[radix:]

    d = Decimal(strnum)

    assert qpdf.Real(d).decode() == d


@given(floats())
def test_decimal_from_float(f):
    d = Decimal(f)
    if isfinite(f) and d.is_finite():
        py_d = qpdf.Real(d)
        assert isclose(py_d.decode(), d), (d, f.hex())
    else:
        with pytest.raises(ValueError, message=repr(f)):
            qpdf.Real(f)
        with pytest.raises(ValueError, message=repr(d)):
            qpdf.Real(d)


@given(lists(integers(-10, 10), min_size=0, average_size=5, max_size=10))
def test_list(array):
    assert decode_encode(array) == array


@given(lists(lists(integers(1,10), min_size=1, max_size=5),min_size=1,max_size=5))
def test_nested_list(array):
    assert decode_encode(array) == array


@given(recursive(none() | booleans(), lambda children: lists(children), max_leaves=20))
def test_nested_list(array):
    assert decode_encode(array) == array


def test_stack_depth():
    a = [150]
    for n in range(150):
        a = [a]
    assert decode_encode(a) == a
    with pytest.raises(RuntimeError, message="recursion"):
        encode(a) == encode(a)