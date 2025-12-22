# SPDX-FileCopyrightText: 2022 James R. Barlow
# SPDX-License-Identifier: CC0-1.0

"""Tests for explicit scalar types (Integer, Boolean, Real)."""

from __future__ import annotations

from decimal import Decimal

import pytest

import pikepdf
from pikepdf import Boolean, Dictionary, Integer, Name, Real


class TestExplicitConversionMode:
    """Tests for the conversion mode API."""

    def test_default_mode_is_implicit(self):
        assert pikepdf.get_object_conversion_mode() == 'implicit'

    def test_set_mode(self):
        old = pikepdf.get_object_conversion_mode()
        try:
            pikepdf.set_object_conversion_mode('explicit')
            assert pikepdf.get_object_conversion_mode() == 'explicit'
            pikepdf.set_object_conversion_mode('implicit')
            assert pikepdf.get_object_conversion_mode() == 'implicit'
        finally:
            pikepdf.set_object_conversion_mode(old)

    def test_context_manager(self):
        assert pikepdf.get_object_conversion_mode() == 'implicit'
        with pikepdf.explicit_conversion():
            assert pikepdf.get_object_conversion_mode() == 'explicit'
        assert pikepdf.get_object_conversion_mode() == 'implicit'

    def test_context_manager_restores_on_exception(self):
        assert pikepdf.get_object_conversion_mode() == 'implicit'
        with pytest.raises(ValueError):
            with pikepdf.explicit_conversion():
                assert pikepdf.get_object_conversion_mode() == 'explicit'
                raise ValueError("test exception")
        assert pikepdf.get_object_conversion_mode() == 'implicit'


class TestImplicitMode:
    """Tests for implicit (legacy) conversion mode."""

    def test_integer_returns_int(self):
        d = Dictionary(Count=5)
        assert type(d.Count) is int
        assert d.Count == 5

    def test_boolean_returns_bool(self):
        d = Dictionary(Flag=True)
        assert type(d.Flag) is bool
        assert d.Flag is True

    def test_real_returns_decimal(self):
        d = Dictionary(Value=Real(1.5))
        assert type(d.Value) is Decimal
        assert d.Value == Decimal('1.5')


class TestExplicitMode:
    """Tests for explicit conversion mode."""

    def test_integer_returns_integer(self):
        with pikepdf.explicit_conversion():
            d = Dictionary(Count=5)
            assert isinstance(d.Count, Integer)
            assert int(d.Count) == 5

    def test_boolean_returns_boolean(self):
        with pikepdf.explicit_conversion():
            d = Dictionary(Flag=True)
            assert isinstance(d.Flag, Boolean)
            assert bool(d.Flag) is True

    def test_real_returns_real(self):
        with pikepdf.explicit_conversion():
            d = Dictionary(Value=Real(1.5))
            assert isinstance(d.Value, Real)
            assert float(d.Value) == 1.5


class TestIntegerType:
    """Tests for the Integer type."""

    def test_isinstance_integer(self):
        with pikepdf.explicit_conversion():
            d = Dictionary(Count=42)
            assert isinstance(d.Count, Integer)
            assert isinstance(d.Count, pikepdf.Object)

    # Note: numbers.Integral.register(Integer) doesn't work as expected
    # because the runtime type is actually Object, not Integer.
    # The isinstance(obj, Integer) check uses metaclass magic.
    # def test_isinstance_numbers_integral(self):
    #     with pikepdf.explicit_conversion():
    #         d = Dictionary(Count=42)
    #         assert isinstance(d.Count, numbers.Integral)

    def test_int_conversion(self):
        with pikepdf.explicit_conversion():
            d = Dictionary(Count=42)
            assert int(d.Count) == 42

    def test_index_for_list_access(self):
        with pikepdf.explicit_conversion():
            d = Dictionary(Index=2)
            items = ['a', 'b', 'c', 'd']
            assert items[d.Index] == 'c'

    def test_equality_with_int(self):
        with pikepdf.explicit_conversion():
            d = Dictionary(Count=5)
            assert d.Count == 5
            assert 5 == d.Count

    def test_repr(self):
        with pikepdf.explicit_conversion():
            d = Dictionary(Count=123)
            assert 'pikepdf.Integer(123)' in repr(d.Count)

    def test_arithmetic_add(self):
        with pikepdf.explicit_conversion():
            d = Dictionary(Value=10)
            result = d.Value + 5
            assert result == 15
            assert type(result) is int

    def test_arithmetic_radd(self):
        with pikepdf.explicit_conversion():
            d = Dictionary(Value=10)
            result = 5 + d.Value
            assert result == 15
            assert type(result) is int

    def test_arithmetic_sub(self):
        with pikepdf.explicit_conversion():
            d = Dictionary(Value=10)
            assert d.Value - 3 == 7
            assert 20 - d.Value == 10

    def test_arithmetic_mul(self):
        with pikepdf.explicit_conversion():
            d = Dictionary(Value=7)
            assert d.Value * 3 == 21
            assert 3 * d.Value == 21

    def test_arithmetic_floordiv(self):
        with pikepdf.explicit_conversion():
            d = Dictionary(Value=17)
            assert d.Value // 5 == 3
            assert 100 // d.Value == 5

    def test_arithmetic_mod(self):
        with pikepdf.explicit_conversion():
            d = Dictionary(Value=17)
            assert d.Value % 5 == 2
            assert 100 % d.Value == 15

    def test_arithmetic_neg(self):
        with pikepdf.explicit_conversion():
            d = Dictionary(Value=42)
            assert -d.Value == -42

    def test_arithmetic_abs(self):
        with pikepdf.explicit_conversion():
            d = Dictionary(Value=-42)
            assert abs(d.Value) == 42

    def test_division_by_zero(self):
        with pikepdf.explicit_conversion():
            d = Dictionary(Value=10)
            with pytest.raises(ValueError, match="division by zero"):
                d.Value // 0
            with pytest.raises(ValueError, match="modulo by zero"):
                d.Value % 0

    def test_float_arithmetic_add(self):
        with pikepdf.explicit_conversion():
            d = Dictionary(Value=10)
            result = d.Value + 2.5
            assert result == 12.5
            assert type(result) is float

    def test_float_arithmetic_radd(self):
        with pikepdf.explicit_conversion():
            d = Dictionary(Value=10)
            result = 2.5 + d.Value
            assert result == 12.5
            assert type(result) is float

    def test_float_arithmetic_sub(self):
        with pikepdf.explicit_conversion():
            d = Dictionary(Value=10)
            assert d.Value - 2.5 == 7.5
            assert 25.5 - d.Value == 15.5

    def test_float_arithmetic_mul(self):
        with pikepdf.explicit_conversion():
            d = Dictionary(Value=7)
            assert d.Value * 2.5 == 17.5
            assert 2.5 * d.Value == 17.5

    def test_truediv(self):
        with pikepdf.explicit_conversion():
            d = Dictionary(Value=10)
            result = d.Value / 4
            assert result == 2.5
            assert type(result) is float
            assert 25 / d.Value == 2.5

    def test_truediv_float(self):
        with pikepdf.explicit_conversion():
            d = Dictionary(Value=10)
            assert d.Value / 2.5 == 4.0
            assert 25.0 / d.Value == 2.5

    def test_float_floordiv(self):
        with pikepdf.explicit_conversion():
            d = Dictionary(Value=10)
            result = d.Value // 3.0
            assert result == 3.0
            assert type(result) is float

    def test_float_mod(self):
        with pikepdf.explicit_conversion():
            d = Dictionary(Value=10)
            result = d.Value % 3.5
            assert abs(result - 3.0) < 0.0001


class TestRealArithmetic:
    """Tests for Real arithmetic operations."""

    def test_real_add_float(self):
        with pikepdf.explicit_conversion():
            d = Dictionary(Value=Real(3.5))
            result = d.Value + 2.5
            assert abs(result - 6.0) < 0.0001
            assert type(result) is float

    def test_real_radd_float(self):
        with pikepdf.explicit_conversion():
            d = Dictionary(Value=Real(3.5))
            result = 2.5 + d.Value
            assert abs(result - 6.0) < 0.0001

    def test_real_sub_float(self):
        with pikepdf.explicit_conversion():
            d = Dictionary(Value=Real(10.5))
            assert abs(d.Value - 3.5 - 7.0) < 0.0001

    def test_real_mul_float(self):
        with pikepdf.explicit_conversion():
            d = Dictionary(Value=Real(3.5))
            assert abs(d.Value * 2.0 - 7.0) < 0.0001

    def test_real_truediv(self):
        with pikepdf.explicit_conversion():
            d = Dictionary(Value=Real(10.0))
            assert abs(d.Value / 4.0 - 2.5) < 0.0001

    def test_real_neg(self):
        with pikepdf.explicit_conversion():
            d = Dictionary(Value=Real(3.5))
            result = -d.Value
            assert abs(result + 3.5) < 0.0001
            assert type(result) is float

    def test_real_abs(self):
        with pikepdf.explicit_conversion():
            d = Dictionary(Value=Real(-3.5))
            result = abs(d.Value)
            assert abs(result - 3.5) < 0.0001


class TestBooleanType:
    """Tests for the Boolean type."""

    def test_isinstance_boolean(self):
        with pikepdf.explicit_conversion():
            d = Dictionary(Flag=True)
            assert isinstance(d.Flag, Boolean)

    def test_bool_conversion(self):
        with pikepdf.explicit_conversion():
            d = Dictionary(Flag=True, Other=False)
            assert bool(d.Flag) is True
            assert bool(d.Other) is False

    def test_repr(self):
        with pikepdf.explicit_conversion():
            d = Dictionary(Flag=True)
            assert 'pikepdf.Boolean(True)' in repr(d.Flag)


class TestRealType:
    """Tests for the Real type."""

    def test_isinstance_real(self):
        with pikepdf.explicit_conversion():
            d = Dictionary(Value=Real(3.14159))
            assert isinstance(d.Value, Real)

    # Note: numbers.Real.register(Real) doesn't work as expected
    # because the runtime type is actually Object, not Real.
    # The isinstance(obj, Real) check uses metaclass magic.
    # def test_isinstance_numbers_real(self):
    #     with pikepdf.explicit_conversion():
    #         d = Dictionary(Value=Real(3.14159))
    #         assert isinstance(d.Value, numbers.Real)

    def test_float_conversion(self):
        with pikepdf.explicit_conversion():
            d = Dictionary(Value=Real(3.14159))
            assert abs(float(d.Value) - 3.14159) < 0.0001

    def test_repr(self):
        with pikepdf.explicit_conversion():
            d = Dictionary(Value=Real(1.5))
            assert 'pikepdf.Real' in repr(d.Value)


class TestAsIntMethod:
    """Tests for the as_int() method."""

    def test_as_int_on_integer(self):
        with pikepdf.explicit_conversion():
            d = Dictionary(Count=42)
            assert d.Count.as_int() == 42
            assert type(d.Count.as_int()) is int

    def test_as_int_on_non_integer_raises(self):
        with pikepdf.explicit_conversion():
            d = Dictionary(Name=Name.Foo)
            with pytest.raises(TypeError, match="Expected integer"):
                d.Name.as_int()

    def test_as_int_with_default(self):
        with pikepdf.explicit_conversion():
            d = Dictionary(Name=Name.Foo)
            assert d.Name.as_int(default=0) == 0
            assert d.Name.as_int(default=None) is None


class TestAsBoolMethod:
    """Tests for the as_bool() method."""

    def test_as_bool_on_boolean(self):
        with pikepdf.explicit_conversion():
            d = Dictionary(Flag=True)
            assert d.Flag.as_bool() is True

    def test_as_bool_on_non_boolean_raises(self):
        with pikepdf.explicit_conversion():
            d = Dictionary(Count=5)
            with pytest.raises(TypeError, match="Expected boolean"):
                d.Count.as_bool()

    def test_as_bool_with_default(self):
        with pikepdf.explicit_conversion():
            d = Dictionary(Count=5)
            assert d.Count.as_bool(default=False) is False


class TestAsFloatMethod:
    """Tests for the as_float() method."""

    def test_as_float_on_real(self):
        with pikepdf.explicit_conversion():
            d = Dictionary(Value=Real(3.14))
            assert abs(d.Value.as_float() - 3.14) < 0.001

    def test_as_float_on_integer(self):
        with pikepdf.explicit_conversion():
            d = Dictionary(Value=5)
            assert d.Value.as_float() == 5.0

    def test_as_float_on_non_numeric_raises(self):
        with pikepdf.explicit_conversion():
            d = Dictionary(Name=Name.Foo)
            with pytest.raises(TypeError, match="Expected numeric"):
                d.Name.as_float()

    def test_as_float_with_default(self):
        with pikepdf.explicit_conversion():
            d = Dictionary(Name=Name.Foo)
            assert d.Name.as_float(default=0.0) == 0.0


class TestAsDecimalMethod:
    """Tests for the as_decimal() method."""

    def test_as_decimal_on_real(self):
        with pikepdf.explicit_conversion():
            d = Dictionary(Value=Real('3.14159'))
            result = d.Value.as_decimal()
            assert isinstance(result, Decimal)

    def test_as_decimal_on_integer_raises(self):
        with pikepdf.explicit_conversion():
            d = Dictionary(Value=5)
            with pytest.raises(TypeError, match="Expected real"):
                d.Value.as_decimal()

    def test_as_decimal_with_default(self):
        with pikepdf.explicit_conversion():
            d = Dictionary(Value=5)
            assert d.Value.as_decimal(default=Decimal('0')) == Decimal('0')


class TestIntegerConstruction:
    """Tests for constructing Integer objects."""

    def test_construct_integer(self):
        # Must use explicit mode for isinstance to work
        with pikepdf.explicit_conversion():
            i = Integer(42)
            assert isinstance(i, Integer)

    def test_integer_passthrough(self):
        with pikepdf.explicit_conversion():
            i1 = Integer(42)
            i2 = Integer(i1)
            # Should return the same object (immutable)
            assert i1 is i2


class TestBooleanConstruction:
    """Tests for constructing Boolean objects."""

    def test_construct_boolean(self):
        with pikepdf.explicit_conversion():
            b = Boolean(True)
            assert isinstance(b, Boolean)

    def test_boolean_passthrough(self):
        with pikepdf.explicit_conversion():
            b1 = Boolean(True)
            b2 = Boolean(b1)
            assert b1 is b2


class TestRealConstruction:
    """Tests for constructing Real objects."""

    def test_construct_real_from_float(self):
        with pikepdf.explicit_conversion():
            r = Real(3.14, 2)
            assert isinstance(r, Real)

    def test_construct_real_from_decimal(self):
        with pikepdf.explicit_conversion():
            r = Real(Decimal('3.14159'))
            assert isinstance(r, Real)

    def test_real_passthrough(self):
        with pikepdf.explicit_conversion():
            r1 = Real(3.14)
            r2 = Real(r1)
            assert r1 is r2
