# SPDX-FileCopyrightText: 2026 James R. Barlow
# SPDX-License-Identifier: CC0-1.0

"""Direct tests of the C++ object-construction facades (pikepdf._core.*).

These exercise the C++ implementations independently of the pikepdf.objects
shim so each migration step is verifiable on its own.
"""

from __future__ import annotations

import pytest

import pikepdf
from pikepdf import _core


class TestCppName:
    def test_attr_construction(self):
        n = _core.Name.Resources
        assert isinstance(n, _core.Object)
        assert repr(n) == 'pikepdf.Name("/Resources")'

    def test_call_construction(self):
        assert repr(_core.Name('/Resources')) == 'pikepdf.Name("/Resources")'

    def test_bytes_rejected(self):
        with pytest.raises(TypeError):
            _core.Name(b'/Resources')

    def test_no_slash_rejected(self):
        with pytest.raises(ValueError):
            _core.Name('Resources')

    def test_single_slash_rejected(self):
        with pytest.raises(ValueError):
            _core.Name('/')

    def test_name_identity(self):
        n = _core.Name('/X')
        assert _core.Name(n) is n

    def test_isinstance(self):
        assert isinstance(_core.Name.Foo, _core.Name)
        assert isinstance(_core.Name.Foo, _core.Object)

    def test_not_subclass_of_object(self):
        assert not issubclass(_core.Name, _core.Object)

    def test_subscript_rejected(self):
        with pytest.raises(TypeError):
            _core.Name['Foo']

    def test_setattr_rejected(self):
        with pytest.raises(AttributeError):
            _core.Name.Foo = 1

    def test_metaclass_name(self):
        assert type(_core.Name).__name__ == '_NameObjectMeta'

    def test_non_string_object_rejected(self):
        with pytest.raises(TypeError):
            _core.Name(_core.String('x'))  # a pikepdf Object that is not a Name

    def test_random(self):
        r = _core.Name.random()
        assert isinstance(r, _core.Object)
        assert str(r).startswith('/')
        r2 = _core.Name.random(prefix='Im')
        assert str(r2).startswith('/Im')
        assert _core.Name.random() != _core.Name.random()


class TestCppOtherFacades:
    def test_operator(self):
        op = _core.Operator('Do')
        assert isinstance(op, _core.Operator)

    def test_string_bytes(self):
        assert repr(_core.String(b'abc')) == 'pikepdf.String("abc")'

    def test_string_str(self):
        assert repr(_core.String('abc')) == 'pikepdf.String("abc")'

    def test_string_bytearray_rejected(self):
        with pytest.raises(TypeError):
            _core.String(bytearray(b'abc'))

    def test_string_object_rejected(self):
        with pytest.raises(TypeError):
            _core.String(_core.Name.Foo)  # a pikepdf Object, not str/bytes

    def test_array_from_list(self):
        a = _core.Array([1, 2, 3])
        assert isinstance(a, _core.Array)
        assert len(a) == 3

    def test_array_str_rejected(self):
        with pytest.raises(TypeError):
            _core.Array('abc')
        with pytest.raises(TypeError):
            _core.Array(b'abc')

    def test_array_none_is_empty(self):
        assert len(_core.Array(None)) == 0
        assert len(_core.Array()) == 0

    def test_array_from_rectangle(self):
        rect = pikepdf.Rectangle(0, 0, 1, 1)
        assert _core.Array(rect) == rect.as_array()

    def test_array_copy(self):
        a = _core.Array([1, 2])
        b = _core.Array(a)
        assert b == a and b is not a

    def test_dictionary_kwargs(self):
        d = _core.Dictionary(One=1, Two=2)
        assert d.One == 1 and d.Two == 2

    def test_dictionary_mapping(self):
        d = _core.Dictionary({'/One': 1})
        assert d.One == 1

    def test_dictionary_mixing_rejected(self):
        with pytest.raises(ValueError):
            _core.Dictionary({'/One': 1}, Two=2)

    def test_dictionary_bad_key_rejected(self):
        with pytest.raises(KeyError):
            _core.Dictionary({'One': 1})

    def test_dictionary_copy(self):
        d = _core.Dictionary(One=1)
        d2 = _core.Dictionary(d)
        assert d2 == d and d2 is not d

    def test_stream(self):
        pdf = pikepdf.Pdf.new()
        s = _core.Stream(pdf, b'data', Key=1)
        assert bytes(s.read_bytes()) == b'data'
        assert s.stream_dict.Key == 1

    def test_stream_requires_data(self):
        pdf = pikepdf.Pdf.new()
        with pytest.raises(TypeError):
            _core.Stream(pdf, None)

    def test_array_non_iterable_rejected(self):
        with pytest.raises(TypeError):
            _core.Array(5)

    def test_dictionary_non_mapping_rejected(self):
        # Mirrors the legacy pikepdf.Dictionary facade, which iterated
        # d.keys() and thus raised AttributeError for non-mapping inputs.
        with pytest.raises(AttributeError):
            _core.Dictionary(5)

    def test_string_unicode(self):
        s = _core.String('é')  # é
        assert isinstance(s, _core.String)

    def test_stream_with_dict_arg(self):
        pdf = pikepdf.Pdf.new()
        s = _core.Stream(pdf, b'data', {'/Key': 5})
        assert s.stream_dict.Key == 5


class TestCppScalars:
    def test_integer_implicit_is_native(self):
        assert pikepdf.get_object_conversion_mode() == 'implicit'
        assert type(_core.Integer(5)) is int
        assert _core.Integer(5) == 5

    def test_integer_explicit_is_object(self):
        with pikepdf.explicit_conversion():
            v = _core.Integer(5)
            assert isinstance(v, _core.Object)
            assert isinstance(v, _core.Integer)

    def test_boolean_implicit_is_native(self):
        assert type(_core.Boolean(True)) is bool
        assert _core.Boolean(True) is True

    def test_boolean_explicit_is_object(self):
        with pikepdf.explicit_conversion():
            assert isinstance(_core.Boolean(True), _core.Boolean)

    def test_real_implicit_is_decimal(self):
        from decimal import Decimal

        assert isinstance(_core.Real(1.5), Decimal)

    def test_real_explicit_is_object(self):
        with pikepdf.explicit_conversion():
            assert isinstance(_core.Real(1.5), _core.Real)

    def test_real_from_decimal(self):
        from decimal import Decimal

        with pikepdf.explicit_conversion():
            r = _core.Real(Decimal('1.25'))
            assert isinstance(r, _core.Real)

    def test_integer_bad_input_typeerror(self):
        with pytest.raises(TypeError):
            _core.Integer('foo')

    def test_boolean_bad_input_typeerror(self):
        with pytest.raises(TypeError):
            _core.Boolean(1)

    def test_real_places(self):
        with pikepdf.explicit_conversion():
            r = _core.Real(1.23456789, places=3)
            assert isinstance(r, _core.Real)
            assert float(r) == pytest.approx(1.235, abs=0.001)

    def test_real_from_int(self):
        with pikepdf.explicit_conversion():
            r = _core.Real(5)
            assert isinstance(r, _core.Real)
            assert float(r) == 5.0

    def test_integer_passthrough_equal(self):
        with pikepdf.explicit_conversion():
            i = _core.Integer(5)
            assert _core.Integer(i) == 5
            assert isinstance(_core.Integer(i), _core.Integer)


class TestCppNamePath:
    def test_attr(self):
        assert repr(_core.NamePath.Resources) == 'NamePath.Resources'

    def test_chain(self):
        assert repr(_core.NamePath.A.B.C) == 'NamePath.A.B.C'

    def test_call_one(self):
        assert repr(_core.NamePath('/Resources')) == 'NamePath.Resources'

    def test_call_many(self):
        assert repr(_core.NamePath('/A', '/B')) == 'NamePath.A.B'

    def test_call_with_names(self):
        assert repr(_core.NamePath(_core.Name.A, _core.Name.B)) == 'NamePath.A.B'

    def test_empty(self):
        assert repr(_core.NamePath()) == 'NamePath'

    def test_subscript_str(self):
        assert repr(_core.NamePath['/Resources']) == 'NamePath.Resources'

    def test_subscript_name(self):
        assert repr(_core.NamePath[_core.Name.Resources]) == 'NamePath.Resources'

    def test_index(self):
        assert repr(_core.NamePath.Kids[0]) == 'NamePath.Kids[0]'

    def test_metaclass_name(self):
        assert type(_core.NamePath).__name__ == '_NamePathMeta'

    def test_underscore_attr_raises(self):
        with pytest.raises(AttributeError):
            _core.NamePath._foo

    def test_float_key_rejected(self):
        with pytest.raises(TypeError):
            _core.NamePath[1.5]

    def test_bad_call_arg_rejected(self):
        with pytest.raises(TypeError):
            _core.NamePath(1.5)

    def test_mixed_chain(self):
        assert repr(_core.NamePath.A('/B').C) == 'NamePath.A.B.C'

    def test_chained_subscript_call_form(self):
        assert repr(_core.NamePath['/A']('/B').C[0]) == 'NamePath.A.B.C[0]'
