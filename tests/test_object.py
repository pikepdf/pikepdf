from decimal import Decimal
from math import isclose, isfinite
import sys

from pikepdf import _qpdf as qpdf
from pikepdf import (Pdf, Object, Real, String, Array, Integer, Name, Boolean,
    Null)
from hypothesis import given, strategies as st, example
from hypothesis.strategies import (none, integers, binary, lists, floats,
    characters, recursive, booleans, builds, one_of)
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


@given(characters(min_codepoint=0x0, max_codepoint=0xfef0,
                  blacklist_categories=('Cs',)))
@example('')
def test_unicode_involution(s):
    assert str(encode(s)) == s


@given(binary(min_size=0, max_size=300))
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

    assert Real(d).decode() == d


@given(floats())
def test_decimal_from_float(f):
    d = Decimal(f)
    if isfinite(f) and d.is_finite():
        py_d = Real(d)
        assert isclose(py_d.decode(), d), (d, f.hex())
    else:
        with pytest.raises(ValueError, message=repr(f)):
            Real(f)
        with pytest.raises(ValueError, message=repr(d)):
            Real(d)


@given(lists(integers(-10, 10), min_size=0, max_size=10))
def test_list(array):
    assert decode_encode(array) == array


@given(lists(lists(integers(1,10), min_size=1, max_size=5),min_size=1,max_size=5))
def test_nested_list(array):
    assert decode_encode(array) == array


@given(recursive(none() | booleans(), lambda children: lists(children), max_leaves=20))
def test_nested_list2(array):
    assert decode_encode(array) == array


def test_stack_depth():
    a = [42]
    for n in range(100):
        a = [a]
    rlimit = sys.getrecursionlimit()
    try:
        sys.setrecursionlimit(100)
        with pytest.raises(RecursionError, message="recursion"):
            assert decode_encode(a) == a
        with pytest.raises(RecursionError, message="recursion"):
            encode(a) == encode(a)
        with pytest.raises(RecursionError, message="recursion"):
            repr(a)
    finally:
        sys.setrecursionlimit(rlimit)  # So other tests are not affected


def test_bytes():
    b = b'\x79\x78\x77\x76'
    qs = String(b)
    assert bytes(qs) == b

    s = 'é'
    qs = String(s)
    assert str(qs) == s


def test_len_array():
    assert len(Array([])) == 0
    assert len(Array([Integer(3)])) == 1


class TestHashViolation:

    def check(self, a, b):
        assert a == b, "invalid test case"
        assert hash(a) == hash(b), "hash violation"

    def test_unequal_but_similar(self):
        assert Name('/Foo') != String('/Foo')

    def test_numbers(self):
        self.check(Real('1.0'), Integer(1))
        self.check(Real('42'), Integer(42))

    def test_bool_comparison(self):
        self.check(Real('0.0'), Boolean(0))
        self.check(Boolean(1), Integer(1))

    def test_string(self):
        utf16 = b'\xfe\xff' + 'hello'.encode('utf-16be')
        self.check(String(utf16), String('hello'))


def test_not_constructible():
    with pytest.raises(TypeError, message="constructor"):
        Object()


def test_str_int():
    assert str(Integer(42)) == '42'
