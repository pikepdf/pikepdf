from decimal import Decimal, InvalidOperation
from math import isclose, isfinite
import sys

import pikepdf
from pikepdf import _qpdf as qpdf
from pikepdf import (Object, String, Array, Name,
    Dictionary, Operator, PdfError)
from hypothesis import given, example, assume
from hypothesis.strategies import (integers, binary, lists, floats,
    characters, recursive, booleans)
import pytest


# pylint: disable=eval-used,unnecessary-lambda

encode = qpdf._encode
decode = qpdf._decode
roundtrip = qpdf._roundtrip


def decode_encode(obj):
    return decode(encode(obj))


@given(characters(min_codepoint=0x20, max_codepoint=0x7f))
@example('')
def test_ascii_involution(ascii_):
    b = ascii_.encode('ascii')
    assert decode_encode(b) == b


@given(characters(min_codepoint=0x0, max_codepoint=0xfef0,
                  blacklist_categories=('Cs',)))
@example('')
def test_unicode_involution(s):
    assert str(encode(s)) == s


@given(binary(min_size=0, max_size=300))
def test_binary_involution(binary_):
    assert bytes(decode_encode(binary_)) == binary_


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
    assert roundtrip(d) == d


@given(floats())
def test_decimal_from_float(f):
    d = Decimal(f)
    if isfinite(f) and d.is_finite():
        try:
            # PDF is limited to ~5 sig figs
            decstr = str(d.quantize(Decimal('1.000000')))
        except InvalidOperation:
            return  # PDF doesn't support exponential notation
        try:
            py_d = Object.parse(decstr)
        except RuntimeError as e:
            if 'overflow' in str(e) or 'underflow' in str(e):
                py_d = Object.parse(str(f))

        assert isclose(py_d, d, abs_tol=1e-5), (d, f.hex())
    else:
        with pytest.raises(PdfError, message=repr(f)):
            Object.parse(str(d))


@given(lists(integers(-10, 10), min_size=0, max_size=10))
def test_list(array):
    a = pikepdf.Array(array)
    assert decode_encode(a) == a


@given(lists(lists(integers(1,10), min_size=1, max_size=5),min_size=1,max_size=5))
def test_nested_list(array):
    a = pikepdf.Array(array)
    assert decode_encode(a) == a


@given(recursive(integers(1,10) | booleans(), lambda children: lists(children), max_leaves=20))
def test_nested_list2(array):
    assume(isinstance(array, list))
    a = pikepdf.Array(array)
    assert decode_encode(a) == a


def test_stack_depth():
    a = [42]
    for _ in range(100):
        a = [a]
    rlimit = sys.getrecursionlimit()
    try:
        sys.setrecursionlimit(100)
        with pytest.raises(RecursionError, message="recursion"):
            assert decode_encode(a) == a
        with pytest.raises(RecursionError, message="recursion"):
            encode(a) == encode(a)  # pylint: disable=expression-not-assigned
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
    assert len(Array([3])) == 1


def test_name_equality():
    # Who needs transitivity?
    # While this is less than ideal ('/Foo' != b'/Foo') it allows for slightly
    # sloppy tests like if colorspace == '/Indexed' without requiring
    # Name('/Indexed') everywhere
    assert Name('/Foo') == '/Foo'
    assert Name('/Foo') == b'/Foo'


class TestHashViolation:

    def check(self, a, b):
        assert a == b, "invalid test case"
        assert hash(a) == hash(b), "hash violation"

    def test_unequal_but_similar(self):
        assert Name('/Foo') != String('/Foo')

    def test_numbers(self):
        self.check(Object.parse('1.0'), 1)
        self.check(Object.parse('42'), 42)

    def test_bool_comparison(self):
        self.check(Object.parse('0.0'), False)
        self.check(True, 1)

    def test_string(self):
        utf16 = b'\xfe\xff' + 'hello'.encode('utf-16be')
        self.check(String(utf16), String('hello'))


def test_not_constructible():
    with pytest.raises(TypeError, message="constructor"):
        Object()


class TestRepr:

    def test_repr_dict(self):
        d = Dictionary({
            '/Boolean': True,
            '/Integer': 42,
            '/Real': Decimal('42.42'),
            '/String': String('hi'),
            '/Array': Array([1, 2, 3.14]),
            '/Operator': Operator('q'),
            '/Dictionary': Dictionary({'/Color': 'Red'})
        })
        expected = """\
            pikepdf.Dictionary({
                "/Array": [ 1, 2, Decimal('3.140000') ],
                "/Boolean": True,
                "/Dictionary": {
                    "/Color": "Red"
                },
                "/Integer": 42,
                "/Operator": pikepdf.Operator("q"),
                "/Real": Decimal('42.42'),
                "/String": "hi"
            })
        """

        def strip_all_whitespace(s):
            return ''.join(s.split())

        assert strip_all_whitespace(repr(d)) == strip_all_whitespace(expected)
        assert eval(repr(d)) == d

    def test_repr_scalar(self):
        scalars = [
            False,
            666,
            Decimal('3.14'),
            String('scalar'),
            Name('/Bob'),
            Operator('Q')
        ]
        for s in scalars:
            assert eval(repr(s)) == s

    def test_repr_indirect(self, resources):
        graph = pikepdf.open(resources / 'graph.pdf')
        repr_page0 = repr(graph.pages[0])
        assert repr_page0[0] == '<', 'should not be constructible'


def test_utf16_error():
    with pytest.raises(UnicodeEncodeError):
        str(encode('\ud801'))
