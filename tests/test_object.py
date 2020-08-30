import json
import sys
from copy import copy
from decimal import Decimal, InvalidOperation
from math import isclose, isfinite
from zlib import compress

import pytest
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
from pikepdf import _qpdf as qpdf

# pylint: disable=eval-used, redefined-outer-name

encode = qpdf._encode
roundtrip = qpdf._roundtrip


def test_none():
    assert encode(None) is None


def test_booleans():
    assert encode(True) == True
    assert encode(False) == False


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


@given(integers(-(10 ** 12), 10 ** 12), integers(0, 12))
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


@given(lists(integers(-10, 10), min_size=0, max_size=10))
def test_list(array):
    a = pikepdf.Array(array)
    assert a == array


@given(lists(lists(integers(1, 10), min_size=1, max_size=5), min_size=1, max_size=5))
def test_nested_list(array):
    a = pikepdf.Array(array)
    assert a == array


@given(
    recursive(
        integers(1, 10) | booleans(),
        lambda children: lists(children),  # pylint: disable=unnecessary-lambda
        max_leaves=20,
    )
)
def test_nested_list2(array):
    assume(isinstance(array, list))
    a = pikepdf.Array(array)
    assert a == array


def test_list_apis():
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
            encode(a) == encode(a)  # pylint: disable=expression-not-assigned
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


def test_len_array():
    assert len(Array([])) == 0
    assert len(Array()) == 0
    assert len(Array([3])) == 1


def test_wrap_array():
    assert Name('/Foo').wrap_in_array() == Array([Name('/Foo')])
    assert Array([42]).wrap_in_array() == Array([42])


def test_name_equality():
    # Who needs transitivity? :P
    # While this is less than ideal ('/Foo' != b'/Foo') it allows for slightly
    # sloppy tests like if colorspace == '/Indexed' without requiring
    # Name('/Indexed') everywhere
    assert Name('/Foo') == '/Foo'
    assert Name('/Foo') == b'/Foo'
    assert Name.Foo == Name('/Foo')


def test_no_len():
    with pytest.raises(TypeError):
        len(Name.Foo)
        len(String('abc'))


def test_unslashed_name():
    with pytest.raises(ValueError, match='must begin with'):
        Name('Monty') not in []  # pylint: disable=expression-not-assigned


def test_empty_name():
    with pytest.raises(ValueError):
        Name('')
    with pytest.raises(ValueError):
        Name('/')


def test_forbidden_name_usage():
    with pytest.raises(TypeError):
        Name.Monty = Name.Python
    with pytest.raises(TypeError):
        Name['/Monty']  # pylint: disable=pointless-statement


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


class TestRepr:
    def test_repr_dict(self):
        d = Dictionary(
            {
                '/Boolean': True,
                '/Integer': 42,
                '/Real': Decimal('42.42'),
                '/String': String('hi'),
                '/Array': Array([1, 2, 3.14]),
                '/Operator': Operator('q'),
                '/Dictionary': Dictionary({'/Color': 'Red'}),
            }
        )
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
            Operator('Q'),
        ]
        for s in scalars:
            assert eval(repr(s)) == s

    def test_repr_indirect(self, resources):
        graph = pikepdf.open(resources / 'graph.pdf')
        repr_page0 = repr(graph.pages[0])
        assert repr_page0[0] == '<', 'should not be constructible'


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
        d = pikepdf.Dictionary(A='a')
        with pytest.raises(NotImplementedError):
            str(d)

    def test_attr(self):
        d = pikepdf.Dictionary(A='a')
        with pytest.raises(AttributeError):
            d.invalidname  # pylint: disable=pointless-statement

    def test_get(self):
        d = pikepdf.Dictionary(A='a')
        assert d.get(Name.A) == 'a'
        assert d.get(Name.Resources, 42) == 42

    def test_nonpage(self):
        d = pikepdf.Dictionary(A='a')
        with pytest.raises(TypeError):
            d.images  # pylint: disable=pointless-statement
        with pytest.raises(TypeError):
            d.page_contents_add(b'', True)

    def test_bad_name(self):
        with pytest.raises(ValueError, match=r"must begin with '/'"):
            pikepdf.Dictionary({'/Slash': 'dot', 'unslash': 'error'})


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
        "/Array": [1, 2, 3.140000],
        "/Boolean": True,
        "/Dictionary": {"/Color": "Red"},
        "/Integer": 42,
        "/Real": 42.42,
        "/String": "hi",
    }


@pytest.fixture
def stream_object():
    pdf = pikepdf.new()
    return Stream(pdf, b'')


@pytest.fixture
def sandwich(resources):
    return Pdf.open(resources / 'sandwich.pdf')


class TestStreamReadWrite:
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


@pytest.mark.parametrize(
    'obj', [Array([1]), Dictionary({'/A': 'b'}), Operator('q'), String('s')]
)
def test_object_isinstance(obj):
    assert isinstance(obj, (Array, Dictionary, Operator, String, Stream))
    assert isinstance(obj, type(obj))
    assert isinstance(obj, Object)


def test_stream_isinstance():
    pdf = pikepdf.new()
    stream = Stream(pdf, b'xyz')
    assert isinstance(stream, Stream)
    assert isinstance(stream, Object)


def test_object_classes():
    classes = [Array, Dictionary, Operator, String, Stream]
    for cls in classes:
        assert issubclass(cls, Object)


def test_operator_create():
    Operator('q')
    assert Operator('q') == Operator('q')
    assert Operator('q') != Operator('Q')


@pytest.fixture(scope="function")
def abcxyz_stream():
    pdf = pikepdf.new()
    data = b'abcxyz'
    stream = Stream(pdf, data)
    return stream


def test_stream_as_dict(abcxyz_stream):
    stream = abcxyz_stream
    assert Name.Length in stream
    stream.TestAttrAccess = True
    stream['/TestKeyAccess'] = True
    stream[Name.TestKeyNameAccess] = True
    assert len(stream.keys()) == 4  # Streams always have a /Length

    assert all((v == len(stream.read_bytes()) or v == True) for k, v in stream.items())

    assert stream.stream_dict.TestAttrAccess

    assert stream.get(Name.MissingName, 3.14) == 3.14

    assert {k for k in stream} == {
        '/TestKeyAccess',
        '/TestAttrAccess',
        '/Length',
        '/TestKeyNameAccess',
    }


def test_stream_length_modify(abcxyz_stream):
    stream = abcxyz_stream

    with pytest.raises(KeyError):
        stream.Length = 42
    with pytest.raises(KeyError):
        del stream.Length


def test_len_stream(abcxyz_stream):
    with pytest.raises(TypeError):
        len(abcxyz_stream)  # pylint: disable=pointless-statement
    assert len(abcxyz_stream.stream_dict) == 1
