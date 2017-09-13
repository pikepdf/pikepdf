import pytest
from pikepdf import _qpdf as qpdf

from hypothesis import given, strategies as st, example


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