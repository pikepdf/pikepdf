from decimal import Decimal
from math import isclose, isfinite
from pikepdf import _qpdf as qpdf
from hypothesis import given, strategies as st, example
import pytest


def decode_encode(obj):
    return qpdf._decode(qpdf._encode(obj))


def test_bool_involution():
    assert decode_encode(True) == True
    assert decode_encode(False) == False


@given(st.integers(min_value=-2**30, max_value=2**30))
def test_integer_involution(n):
    assert decode_encode(n) == n


@given(st.characters(min_codepoint=0x20, max_codepoint=0x7f))
@example('')
def test_ascii_involution(ascii):
    b = ascii.encode('ascii')
    assert decode_encode(b) == b


@given(st.binary(min_size=0, max_size=10000, average_size=10))
def test_binary_involution(binary):
    assert decode_encode(binary) == binary


@given(st.integers(-10**12, 10**12), st.integers(-10**12, 10**12))
def test_integer_comparison(a, b):
    equals = (a == b)
    encoded_equals = (qpdf._encode(a) == qpdf._encode(b))
    assert encoded_equals == equals

    lessthan = (a < b)
    encoded_lessthan = (qpdf._encode(a) < qpdf._encode(b))
    assert lessthan == encoded_lessthan


@given(st.integers(max_value=9223372036854775807), st.integers(max_value=9223372036854775807))
def test_crosstype_comparison(a, b):
    equals = (a == b)
    encoded_equals = (a == qpdf._encode(b))
    assert encoded_equals == equals

    lessthan = (a < b)
    encoded_lessthan = (qpdf._encode(a) < b)
    assert lessthan == encoded_lessthan


@given(st.integers(-10**12, 10**12), st.integers(0, 12))
def test_decimal_involution(num, radix):
    strnum = str(num)
    if radix > len(strnum):
        strnum = strnum[:radix] + '.' + strnum[radix:]

    d = Decimal(strnum)

    assert qpdf.Object.Real(d).decode() == d


@given(st.floats())
def test_decimal_from_float(f):
    d = Decimal(f)
    if isfinite(f) and d.is_finite():
        py_d = qpdf.Object.Real(d)
        assert isclose(py_d.decode(), d), (d, f.hex())
    else:
        with pytest.raises(ValueError, message=repr(f)):
            qpdf.Object.Real(f)
        with pytest.raises(ValueError, message=repr(d)):
            qpdf.Object.Real(d)
            
        