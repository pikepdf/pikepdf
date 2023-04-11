# SPDX-FileCopyrightText: 2022 James R. Barlow
# SPDX-License-Identifier: CC0-1.0

from __future__ import annotations

import json
import sys
from copy import copy
from decimal import Decimal, InvalidOperation
from math import isclose, isfinite
from zlib import compress

import pytest
from conftest import skip_if_pypy
from hypothesis import assume, example, given
from hypothesis.strategies import (
    binary,
    booleans,
    characters,
    floats,
    integers,
    lists,
    recursive,
)

import pikepdf
from pikepdf import (
    Array,
    Dictionary,
    Name,
    Object,
    Operator,
    Pdf,
    PdfError,
    Stream,
    String,
)
from pikepdf import _core as core
from pikepdf.models import parse_content_stream

# pylint: disable=eval-used, redefined-outer-name

encode = core._encode


def test_none():
    assert encode(None) is None


def test_booleans():
    assert encode(True) == True  # noqa: E712
    assert encode(False) == False  # noqa: E712


@given(characters(min_codepoint=0x20, max_codepoint=0x7F))
@example('')
def test_ascii_involution(ascii_):
    b = ascii_.encode('ascii')
    assert encode(b) == b


@given(
    characters(min_codepoint=0x0, max_codepoint=0xFEF0, blacklist_categories=('Cs',))
)
@example('')
def test_unicode_involution(s):
    assert str(encode(s)) == s


@given(characters(whitelist_categories=('Cs',)))
def test_unicode_fails(s):
    with pytest.raises(UnicodeEncodeError):
        encode(s)


@given(binary(min_size=0, max_size=300))
def test_binary_involution(binary_):
    assert bytes(encode(binary_)) == binary_


int64s = integers(min_value=-9223372036854775807, max_value=9223372036854775807)


@given(int64s, int64s)
def test_integer_comparison(a, b):
    equals = a == b
    encoded_equals = encode(a) == encode(b)
    assert encoded_equals == equals

    lessthan = a < b
    encoded_lessthan = encode(a) < encode(b)
    assert lessthan == encoded_lessthan


@given(integers(-(10**12), 10**12), integers(0, 12))
def test_decimal_involution(num, radix):
    strnum = str(num)
    if radix > len(strnum):
        strnum = strnum[:radix] + '.' + strnum[radix:]

    d = Decimal(strnum)
    assert encode(d) == d


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
        with pytest.raises(PdfError):
            Object.parse(str(d))


def test_qpdf_real_to_decimal():
    assert isclose(core._new_real(1.2345, 4), Decimal('1.2345'), abs_tol=1e-5)
    assert isclose(core._new_real('2.3456'), Decimal('2.3456'), abs_tol=1e-5)


@skip_if_pypy
def test_stack_depth():
    a = [42]
    for _ in range(100):
        a = [a]
    rlimit = sys.getrecursionlimit()
    try:
        sys.setrecursionlimit(100)
        with pytest.raises(RecursionError):
            assert encode(a) == a
        with pytest.raises(RecursionError):
            assert encode(a) == encode(a)  # pylint: disable=expression-not-assigned
        with pytest.raises(RecursionError):
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

    assert Name('/xyz') == b'/xyz'
    with pytest.raises(TypeError, match='should be str'):
        Name(b'/bytes')


class TestArray:
    def test_len_array(self):
        assert len(Array([])) == 0
        assert len(Array()) == 0
        assert len(Array([3])) == 1

    def test_wrap_array(self):
        assert Name('/Foo').wrap_in_array() == Array([Name('/Foo')])
        assert Array([42]).wrap_in_array() == Array([42])

    @given(lists(integers(-10, 10), min_size=0, max_size=10))
    def test_list(self, array):
        a = pikepdf.Array(array)
        assert a == array

    @given(
        lists(lists(integers(1, 10), min_size=1, max_size=5), min_size=1, max_size=5)
    )
    def test_nested_list(self, array):
        a = pikepdf.Array(array)
        assert a == array

    @given(
        recursive(
            integers(1, 10) | booleans(),
            lambda children: lists(children),  # pylint: disable=unnecessary-lambda
            max_leaves=20,
        )
    )
    def test_nested_list2(self, array):
        assume(isinstance(array, list))
        a = pikepdf.Array(array)
        assert a == array

    def test_array_of_array(self):
        a = Array([1, 2])
        a2 = Array(a)
        assert a == a2
        assert a is not a2

    def test_array_of_primitives_eq(self):
        a = Array([True, False, 0, 1, 42, 42.42])
        b = Array([True, False, 0, 1, 42, 42.42])
        assert a == b
        c = Array([1.0, 0.0, 0.0, 1.0, 42.0, 42.42])
        assert a == c

    def test_list_apis(self):
        a = pikepdf.Array([1, 2, 3])
        a[1] = None
        assert a[1] is None
        assert len(a) == 3
        del a[1]
        assert len(a) == 2
        a[-1] = Name('/Foo')
        with pytest.raises(IndexError):
            a[-5555] = Name.Foo
        assert a == pikepdf.Array([1, Name.Foo])
        a.append(4)
        assert a == pikepdf.Array([1, Name.Foo, 4])
        a.extend([42, 666])
        assert a == pikepdf.Array([1, Name.Foo, 4, 42, 666])
        with pytest.raises(
            ValueError, match='pikepdf.Object is not a Dictionary or Stream'
        ):
            del a.ImaginaryKey
        with pytest.raises(TypeError, match=r"items\(\) not available"):
            a.items()

    def test_array_contains(self):
        a = pikepdf.Array([Name.One, Name.Two])
        assert Name.One in a
        assert Name.Two in a
        assert Name.N not in a

        a = pikepdf.Array([1, 2, 3])
        assert 1 in a
        assert 3 in a
        assert 42 not in a

        with pytest.raises(TypeError):
            assert 'forty two' not in a
        with pytest.raises(TypeError):
            assert b'forty two' not in a
        assert pikepdf.String('forty two') not in a

        a = pikepdf.Array(['1234', b'\x80\x81\x82'])
        assert pikepdf.String('1234') in a
        assert pikepdf.String(b'\x80\x81\x82') in a

    def test_is_rect(self):
        assert pikepdf.Array([0, 1, 2, 3]).is_rectangle
        assert not pikepdf.Array(['a', '2', 3, 4]).is_rectangle


def test_no_len():
    with pytest.raises(TypeError):
        len(Name.Foo)
        len(String('abc'))


class TestName:
    def test_name_equality(self):
        # Who needs transitivity? :P
        # While this is less than ideal ('/Foo' != b'/Foo') it allows for slightly
        # sloppy tests like if colorspace == '/Indexed' without requiring
        # Name('/Indexed') everywhere
        assert Name('/Foo') == '/Foo'
        assert Name('/Foo') == b'/Foo'
        assert Name.Foo == Name('/Foo')

    def test_unslashed_name(self):
        with pytest.raises(ValueError, match='must begin with'):
            assert Name('Monty') not in []  # pylint: disable=expression-not-assigned

    def test_empty_name(self):
        with pytest.raises(ValueError):
            Name('')
        with pytest.raises(ValueError):
            Name('/')

    def test_forbidden_name_usage(self):
        with pytest.raises(AttributeError, match="may not be set on pikepdf.Name"):
            Name.Monty = Name.Python
        with pytest.raises(TypeError, match="not subscriptable"):
            Name['/Monty']  # pylint: disable=pointless-statement
        if sys.implementation.name == 'pypy':
            pytest.xfail(reason="pypy seems to do setattr differently")
        with pytest.raises(AttributeError, match="has no attribute"):
            monty = Name.Monty
            monty.Attribute = 42

    def test_bytes_of_name(self):
        assert bytes(Name.ABC) == b'/ABC'

    def test_name_from_name(self):
        foo = Name('/Foo')
        assert Name(foo) == foo


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

    def test_name(self):
        self.check(Name.This, Name('/This'))

    def test_operator(self):
        self.check(Operator('q'), Operator('q'))

    def test_array_not_hashable(self):
        with pytest.raises(TypeError):
            {Array([3]): None}  # pylint: disable=expression-not-assigned


def test_not_constructible():
    with pytest.raises(TypeError, match="constructor"):
        Object()


def test_operator_inline(resources):
    with pikepdf.open(resources / 'image-mono-inline.pdf') as pdf:
        instructions = parse_content_stream(pdf.pages[0], operators='BI ID EI')
        assert len(instructions) == 1
        _operands, operator = instructions[0]
        assert operator == pikepdf.Operator("INLINE IMAGE")


def test_utf16_error():
    with pytest.raises((UnicodeEncodeError, RuntimeError)):
        str(encode('\ud801'))


class TestDictionary:
    def test_contains(self):
        d = Dictionary({'/Monty': 'Python', '/Flying': 'Circus'})
        assert Name.Flying in d
        assert Name('/Monty') in d
        assert Name.Brian not in d

    def test_none(self):
        d = pikepdf.Dictionary({'/One': 1, '/Two': 2})
        with pytest.raises(ValueError):
            d['/Two'] = None

    def test_init(self):
        d1 = pikepdf.Dictionary({'/Animal': 'Dog'})
        d2 = pikepdf.Dictionary(Animal='Dog')
        assert d1 == d2

    def test_kwargs(self):
        d = pikepdf.Dictionary(A='a', B='b', C='c')
        assert '/B' in d
        assert 'B' in dir(d)

    def test_iter(self):
        d = pikepdf.Dictionary(A='a')
        for k in d:
            assert k == '/A'
            assert d[k] == 'a'

    def test_items(self):
        d = pikepdf.Dictionary(A='a')
        for _k in d.items():
            pass

    def test_str(self):
        d = pikepdf.Dictionary(ABCD='abcd')
        assert 'ABCD' in str(d)

    def test_attr(self):
        d = pikepdf.Dictionary(A='a')
        with pytest.raises(AttributeError):
            d.invalidname  # pylint: disable=pointless-statement

    def test_get(self):
        d = pikepdf.Dictionary(A='a')
        assert d.get(Name.A) == 'a'
        assert d.get(Name.Resources, 42) == 42

    def test_bad_name_init(self):
        with pytest.raises(KeyError, match=r"must begin with '/'"):
            pikepdf.Dictionary({'/Slash': 'dot', 'unslash': 'error'})
        with pytest.raises(KeyError, match=r"must begin with '/'"):
            pikepdf.Dictionary({'/': 'slash'})

    def test_bad_name_set(self):
        d = pikepdf.Dictionary()
        d['/Slash'] = 'dot'
        with pytest.raises(KeyError, match=r"must begin with '/'"):
            d['unslash'] = 'error'
        with pytest.raises(KeyError, match=r"may not be '/'"):
            d['/'] = 'error'

    def test_del_missing_key(self):
        d = pikepdf.Dictionary(A='a')
        with pytest.raises(KeyError):
            del d.B

    def test_int_access(self):
        d = pikepdf.Dictionary()
        with pytest.raises(TypeError, match="not an array"):
            d[0] = 3

    def test_wrong_contains_type(self):
        d = pikepdf.Dictionary()
        with pytest.raises(TypeError, match="can only contain Names"):
            assert pikepdf.Array([3]) not in d

    def test_dict_bad_params(self):
        with pytest.raises(ValueError):
            Dictionary({'/Foo': 1}, Bar=2)

    def test_dict_of_dict(self):
        d = Dictionary(One=1, Two=2)
        d2 = Dictionary(d)
        assert d == d2
        assert d is not d2


def test_not_convertible():
    class PurePythonObj:
        def __repr__(self):
            return 'PurePythonObj()'

    c = PurePythonObj()
    with pytest.raises(RuntimeError):
        encode(c)
    with pytest.raises(RuntimeError):
        pikepdf.Array([1, 2, c])

    d = pikepdf.Dictionary()
    with pytest.raises(RuntimeError):
        d.SomeKey = c

    assert d != c


def test_json():
    d = Dictionary(
        {
            '/Boolean': True,
            '/Integer': 42,
            '/Real': Decimal('42.42'),
            '/String': String('hi'),
            '/Array': Array([1, 2, 3.14]),
            '/Dictionary': Dictionary({'/Color': 'Red'}),
        }
    )
    json_bytes = d.to_json(False)
    as_dict = json.loads(json_bytes)
    assert as_dict == {
        "/Array": [1, 2, 3.14],
        "/Boolean": True,
        "/Dictionary": {"/Color": "u:Red"},
        "/Integer": 42,
        "/Real": 42.42,
        "/String": "u:hi",
    }


class TestStream:
    @pytest.fixture(scope="function")
    def abcxyz_stream(self):
        with pikepdf.new() as pdf:
            data = b'abcxyz'
            stream = Stream(pdf, data)
            yield stream

    def test_stream_isinstance(self):
        pdf = pikepdf.new()
        stream = Stream(pdf, b'xyz')
        assert isinstance(stream, Stream)
        assert isinstance(stream, Object)

    def test_stream_as_dict(self, abcxyz_stream):
        stream = abcxyz_stream
        assert Name.Length in stream
        stream.TestAttrAccess = True
        stream['/TestKeyAccess'] = True
        stream[Name.TestKeyNameAccess] = True
        assert len(stream.keys()) == 4  # Streams always have a /Length

        assert all(
            (v == len(stream.read_bytes()) or v == True)  # noqa: E712
            for k, v in stream.items()
        )

        assert stream.stream_dict.TestAttrAccess

        assert stream.get(Name.MissingName, 3.14) == 3.14

        assert {k for k in stream} == {
            '/TestKeyAccess',
            '/TestAttrAccess',
            '/Length',
            '/TestKeyNameAccess',
        }

    def test_stream_length_modify(self, abcxyz_stream):
        stream = abcxyz_stream

        with pytest.raises(KeyError):
            stream.Length = 42
        with pytest.raises(KeyError):
            del stream.Length

    def test_len_stream(self, abcxyz_stream):
        with pytest.raises(TypeError):
            len(abcxyz_stream)  # pylint: disable=pointless-statement
        assert len(abcxyz_stream.stream_dict) == 1

    def test_stream_dict_oneshot(self):
        pdf = pikepdf.new()
        stream1 = Stream(pdf, b'12345', One=1, Two=2)
        stream2 = Stream(pdf, b'67890', {'/Three': 3, '/Four': 4})
        stream3 = pdf.make_stream(b'abcdef', One=1, Two=2)

        assert stream1.One == 1
        assert stream1.read_bytes() == b'12345'
        assert stream2.Three == 3
        assert stream3.One == 1

    def test_stream_bad_params(self):
        p = pikepdf.new()
        with pytest.raises(TypeError, match='data'):
            Stream(p)

    def test_stream_no_dangling_stream_on_failure(self):
        p = pikepdf.new()
        num_objects = len(p.objects)
        with pytest.raises(AttributeError):
            Stream(p, b'3.14159', ['Not a mapping object'])
        assert len(p.objects) == num_objects, "A dangling object was created"

    def test_identical_streams_equal(self):
        pdf = pikepdf.new()
        stream1 = Stream(pdf, b'12345', One=1, Two=2)
        stream2 = Stream(pdf, b'67890', {'/Three': 3, '/Four': 4})
        assert stream1 == stream1
        assert stream1 != stream2

    def test_stream_data_equal(self):
        pdf1 = pikepdf.new()
        stream1 = Stream(pdf1, b'abc')
        pdf2 = pikepdf.new()
        stream2 = Stream(pdf2, b'abc')
        stream21 = Stream(pdf2, b'abcdef')
        assert stream1 == stream2
        assert stream21 != stream2

        stream2.stream_dict.SomeData = 1
        assert stream2 != stream1

    def test_stream_refcount(self, refcount, outpdf):
        pdf = pikepdf.new()
        stream = Stream(pdf, b'blahblah')
        assert refcount(stream) == 2
        pdf.Root.SomeStream = stream
        assert refcount(stream) == 2
        del stream
        pdf.save(outpdf)
        with pikepdf.open(outpdf) as pdf2:
            assert pdf2.Root.SomeStream.read_bytes() == b'blahblah'


@pytest.fixture
def sandwich(resources):
    with Pdf.open(resources / 'sandwich.pdf') as pdf:
        yield pdf


class TestStreamReadWrite:
    @pytest.fixture
    def stream_object(self):
        with pikepdf.new() as pdf:
            yield Stream(pdf, b'abc123xyz')

    def test_basic(self, stream_object):
        stream_object.write(b'abc')
        assert stream_object.read_bytes() == b'abc'

    def test_compressed_readback(self, stream_object):
        stream_object.write(compress(b'def'), filter=Name.FlateDecode)
        assert stream_object.read_bytes() == b'def'

    def test_stacked_compression(self, stream_object):
        double_compressed = compress(compress(b'pointless'))
        stream_object.write(
            double_compressed, filter=[Name.FlateDecode, Name.FlateDecode]
        )
        assert stream_object.read_bytes() == b'pointless'
        assert stream_object.read_raw_bytes() == double_compressed

    def test_explicit_decodeparms(self, stream_object):
        double_compressed = compress(compress(b'pointless'))
        stream_object.write(
            double_compressed,
            filter=[Name.FlateDecode, Name.FlateDecode],
            decode_parms=[None, None],
        )
        assert stream_object.read_bytes() == b'pointless'
        assert stream_object.read_raw_bytes() == double_compressed

    def test_no_kwargs(self, stream_object):
        with pytest.raises(TypeError):
            stream_object.write(compress(b'x'), [Name.FlateDecode])

    def test_ccitt(self, stream_object):
        ccitt = b'\x00'  # Not valid data, just for testing decode_parms
        stream_object.write(
            ccitt,
            filter=Name.CCITTFaxDecode,
            decode_parms=Dictionary(K=-1, Columns=8, Length=1),
        )

    def test_stream_bytes(self, stream_object):
        stream_object.write(b'pi')
        assert bytes(stream_object) == b'pi'

    def test_invalid_filter(self, stream_object):
        with pytest.raises(TypeError, match="filter must be"):
            stream_object.write(b'foo', filter=[42])

    def test_invalid_decodeparms(self, stream_object):
        with pytest.raises(TypeError, match="decode_parms must be"):
            stream_object.write(
                compress(b'foo'), filter=Name.FlateDecode, decode_parms=[42]
            )

    def test_filter_decodeparms_mismatch(self, stream_object):
        with pytest.raises(ValueError, match=r"filter.*and decode_parms"):
            stream_object.write(
                compress(b'foo'),
                filter=[Name.FlateDecode],
                decode_parms=[Dictionary(), Dictionary()],
            )

    def test_raw_stream_buffer(self, stream_object):
        raw_buffer = stream_object.get_raw_stream_buffer()
        assert bytes(raw_buffer) == b'abc123xyz'


def test_copy():
    d = Dictionary(
        {
            '/Boolean': True,
            '/Integer': 42,
            '/Real': Decimal('42.42'),
            '/String': String('hi'),
            '/Array': Array([1, 2, 3.14]),
            '/Dictionary': Dictionary({'/Color': 'Red'}),
        }
    )
    d2 = copy(d)
    assert d2 == d
    assert d2 is not d
    assert d2['/Dictionary'] == d['/Dictionary']


def test_object_iteration(sandwich):
    expected = len(sandwich.objects)
    loops = 0
    for obj in sandwich.objects:
        loops += 1
        if isinstance(obj, Dictionary):
            assert len(obj.keys()) >= 1
    assert expected == loops


def test_object_not_iterable():
    with pytest.raises(TypeError, match="__iter__ not available"):
        iter(pikepdf.Name.A)


@pytest.mark.parametrize(
    'obj', [Array([1]), Dictionary({'/A': 'b'}), Operator('q'), String('s')]
)
def test_object_isinstance(obj):
    assert isinstance(obj, (Array, Dictionary, Operator, String, Stream))
    assert isinstance(obj, type(obj))
    assert isinstance(obj, Object)


def test_object_classes():
    classes = [Array, Dictionary, Operator, String, Stream]
    for cls in classes:
        assert issubclass(cls, Object)


class TestOperator:
    def test_operator_create(self):
        Operator('q')
        assert Operator('q') == Operator('q')
        assert Operator('q') != Operator('Q')

    def test_operator_str(self):
        assert str(Operator('Do')) == 'Do'

    def test_operator_bytes(self):
        assert bytes(Operator('cm')) == b'cm'

    def test_operator_contains_misuse(self):
        with pytest.raises(
            ValueError, match="pikepdf.Object is not a Dictionary or Stream"
        ):
            _unused = 'nope' in Operator('Do')

    def test_operator_setitem_misuse(self):
        with pytest.raises(
            ValueError, match="pikepdf.Object is not a Dictionary or Stream"
        ):
            Operator('Do')['x'] = 42


def test_object_mapping(sandwich):
    object_mapping = sandwich.pages[0].images
    assert '42' not in object_mapping
    assert '/R12' in object_mapping
    assert '/R12' in object_mapping.keys()


def test_replace_object(sandwich):
    d = Dictionary(Type=Name.Dummy)
    profile = sandwich.Root.OutputIntents[0].DestOutputProfile.objgen
    sandwich._replace_object(profile, d)
    assert sandwich.Root.OutputIntents[0].DestOutputProfile == d


def test_swap_object(resources):
    with Pdf.open(resources / 'fourpages.pdf') as pdf:
        pdf.pages[0].MarkPage0 = True
        pdf._swap_objects(pdf.pages[0].objgen, pdf.pages[1].objgen)
        assert pdf.pages[1].MarkPage0
        assert Name.MarkPage0 not in pdf.pages[0]
