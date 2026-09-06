# SPDX-FileCopyrightText: 2022 James R. Barlow
# SPDX-License-Identifier: CC0-1.0

"""Tests for explicit scalar types (Integer, Boolean, Real)."""

from __future__ import annotations

import locale
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

    @pytest.mark.abi3_smoke
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

    @pytest.mark.abi3_smoke
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
            assert d.Name.as_int(0) == 0  # positionally too

    def test_as_int_default_ignored_when_type_matches(self):
        with pikepdf.explicit_conversion():
            d = Dictionary(Count=42)
            assert d.Count.as_int(0) == 42
            assert d.Count.as_int(default=0) == 42


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

    def test_as_decimal_preserves_precision(self):
        with pikepdf.explicit_conversion():
            d = Dictionary(Value=Real('0.1234567890123456789'))
            assert d.Value.as_decimal() == Decimal('0.1234567890123456789')

    def test_as_decimal_default_is_returned_unconverted(self):
        with pikepdf.explicit_conversion():
            d = Dictionary(Value=5)
            sentinel = object()
            assert d.Value.as_decimal(sentinel) is sentinel


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


class TestArithmeticErrorCases:
    """Tests for arithmetic error cases and edge conditions."""

    def test_arithmetic_on_non_numeric_raises(self):
        """Test that arithmetic on non-numeric types raises TypeError."""
        with pikepdf.explicit_conversion():
            d = Dictionary(Name=Name.Foo)
            with pytest.raises(TypeError, match="not an integer"):
                d.Name + 1
            with pytest.raises(TypeError, match="not an integer"):
                1 + d.Name
            with pytest.raises(TypeError, match="not numeric"):
                d.Name + 1.5
            with pytest.raises(TypeError, match="not numeric"):
                1.5 + d.Name

    def test_sub_on_non_numeric_raises(self):
        with pikepdf.explicit_conversion():
            d = Dictionary(Name=Name.Foo)
            with pytest.raises(TypeError, match="not an integer"):
                d.Name - 1
            with pytest.raises(TypeError, match="not an integer"):
                1 - d.Name
            with pytest.raises(TypeError, match="not numeric"):
                d.Name - 1.5
            with pytest.raises(TypeError, match="not numeric"):
                1.5 - d.Name

    def test_mul_on_non_numeric_raises(self):
        with pikepdf.explicit_conversion():
            d = Dictionary(Name=Name.Foo)
            with pytest.raises(TypeError, match="not an integer"):
                d.Name * 2
            with pytest.raises(TypeError, match="not an integer"):
                2 * d.Name
            with pytest.raises(TypeError, match="not numeric"):
                d.Name * 2.5
            with pytest.raises(TypeError, match="not numeric"):
                2.5 * d.Name

    def test_truediv_on_non_numeric_raises(self):
        with pikepdf.explicit_conversion():
            d = Dictionary(Name=Name.Foo)
            with pytest.raises(TypeError, match="not numeric"):
                d.Name / 2
            with pytest.raises(TypeError, match="not numeric"):
                2 / d.Name
            with pytest.raises(TypeError, match="not numeric"):
                d.Name / 2.5
            with pytest.raises(TypeError, match="not numeric"):
                2.5 / d.Name

    def test_floordiv_on_non_numeric_raises(self):
        with pikepdf.explicit_conversion():
            d = Dictionary(Name=Name.Foo)
            with pytest.raises(TypeError, match="not an integer"):
                d.Name // 2
            with pytest.raises(TypeError, match="not an integer"):
                2 // d.Name
            with pytest.raises(TypeError, match="not numeric"):
                d.Name // 2.5
            with pytest.raises(TypeError, match="not numeric"):
                2.5 // d.Name

    def test_mod_on_non_numeric_raises(self):
        with pikepdf.explicit_conversion():
            d = Dictionary(Name=Name.Foo)
            with pytest.raises(TypeError, match="not an integer"):
                d.Name % 2
            with pytest.raises(TypeError, match="not an integer"):
                2 % d.Name
            with pytest.raises(TypeError, match="not numeric"):
                d.Name % 2.5
            with pytest.raises(TypeError, match="not numeric"):
                2.5 % d.Name

    def test_neg_on_non_numeric_raises(self):
        with pikepdf.explicit_conversion():
            d = Dictionary(Name=Name.Foo)
            with pytest.raises(TypeError, match="not numeric"):
                -d.Name

    def test_pos_on_non_numeric_raises(self):
        with pikepdf.explicit_conversion():
            d = Dictionary(Name=Name.Foo)
            with pytest.raises(TypeError, match="not numeric"):
                +d.Name

    def test_abs_on_non_numeric_raises(self):
        with pikepdf.explicit_conversion():
            d = Dictionary(Name=Name.Foo)
            with pytest.raises(TypeError, match="not numeric"):
                abs(d.Name)


class TestNotImplementedFallback:
    """Tests for NotImplemented return with unsupported operand types.

    When operations involve types that aren't int or float (like Decimal),
    the C++ code returns NotImplemented to let Python try the other operand's
    methods. These tests verify that code path is hit (even though the overall
    operation may still fail if the other type can't handle it).
    """

    def test_integer_add_unsupported_type_raises(self):
        """Integer + Decimal returns NotImplemented, leading to TypeError."""
        with pikepdf.explicit_conversion():
            d = Dictionary(Value=10)
            # NotImplemented is returned, but Decimal doesn't handle Object
            with pytest.raises(TypeError):
                d.Value + Decimal('5')

    def test_integer_radd_unsupported_type_raises(self):
        """Decimal + Integer triggers __radd__ returning NotImplemented."""
        with pikepdf.explicit_conversion():
            d = Dictionary(Value=10)
            with pytest.raises(TypeError):
                Decimal('5') + d.Value

    def test_integer_sub_unsupported_type_raises(self):
        with pikepdf.explicit_conversion():
            d = Dictionary(Value=10)
            with pytest.raises(TypeError):
                d.Value - Decimal('5')

    def test_integer_mul_unsupported_type_raises(self):
        with pikepdf.explicit_conversion():
            d = Dictionary(Value=10)
            with pytest.raises(TypeError):
                d.Value * Decimal('5')

    def test_integer_truediv_unsupported_type_raises(self):
        with pikepdf.explicit_conversion():
            d = Dictionary(Value=10)
            with pytest.raises(TypeError):
                d.Value / Decimal('5')

    def test_integer_floordiv_unsupported_type_raises(self):
        with pikepdf.explicit_conversion():
            d = Dictionary(Value=10)
            with pytest.raises(TypeError):
                d.Value // Decimal('5')

    def test_integer_mod_unsupported_type_raises(self):
        with pikepdf.explicit_conversion():
            d = Dictionary(Value=10)
            with pytest.raises(TypeError):
                d.Value % Decimal('5')

    def test_real_add_unsupported_type_raises(self):
        with pikepdf.explicit_conversion():
            d = Dictionary(Value=Real(2.5))
            with pytest.raises(TypeError):
                d.Value + Decimal('5')

    def test_real_sub_unsupported_type_raises(self):
        with pikepdf.explicit_conversion():
            d = Dictionary(Value=Real(2.5))
            with pytest.raises(TypeError):
                d.Value - Decimal('5')

    def test_real_mul_unsupported_type_raises(self):
        with pikepdf.explicit_conversion():
            d = Dictionary(Value=Real(2.5))
            with pytest.raises(TypeError):
                d.Value * Decimal('5')

    def test_real_truediv_unsupported_type_raises(self):
        with pikepdf.explicit_conversion():
            d = Dictionary(Value=Real(2.5))
            with pytest.raises(TypeError):
                d.Value / Decimal('5')

    def test_real_floordiv_unsupported_type_raises(self):
        with pikepdf.explicit_conversion():
            d = Dictionary(Value=Real(2.5))
            with pytest.raises(TypeError):
                d.Value // Decimal('5')

    def test_real_mod_unsupported_type_raises(self):
        with pikepdf.explicit_conversion():
            d = Dictionary(Value=Real(2.5))
            with pytest.raises(TypeError):
                d.Value % Decimal('5')


class TestArithmeticOnNonNumericWithUnsupportedOther:
    """Non-numeric Object combined with non-int/non-float other (e.g. Decimal).

    Exercises the type_error path in the py::object overloads of arithmetic
    operators that fires when the Object itself is not numeric.
    """

    @pytest.mark.parametrize(
        "op",
        [
            lambda a, b: a + b,
            lambda a, b: a - b,
            lambda a, b: a * b,
            lambda a, b: a / b,
            lambda a, b: a // b,
            lambda a, b: a % b,
        ],
    )
    def test_name_op_decimal_raises(self, op):
        with pikepdf.explicit_conversion():
            d = Dictionary(Name=Name.Foo)
            with pytest.raises(TypeError, match="not numeric"):
                op(d.Name, Decimal('5'))

    @pytest.mark.parametrize(
        "op",
        [
            lambda a, b: a + b,
            lambda a, b: a - b,
            lambda a, b: a * b,
            lambda a, b: a / b,
            lambda a, b: a // b,
            lambda a, b: a % b,
        ],
    )
    def test_decimal_op_name_raises(self, op):
        with pikepdf.explicit_conversion():
            d = Dictionary(Name=Name.Foo)
            with pytest.raises(TypeError, match="not numeric"):
                op(Decimal('5'), d.Name)


class TestRealReverseArithmetic:
    """Tests for Real reverse arithmetic operations."""

    def test_real_rsub(self):
        with pikepdf.explicit_conversion():
            d = Dictionary(Value=Real(3.5))
            result = 10.0 - d.Value
            assert abs(result - 6.5) < 0.0001

    def test_real_rmul(self):
        with pikepdf.explicit_conversion():
            d = Dictionary(Value=Real(2.5))
            result = 4.0 * d.Value
            assert abs(result - 10.0) < 0.0001

    def test_real_rtruediv(self):
        with pikepdf.explicit_conversion():
            d = Dictionary(Value=Real(2.5))
            result = 10.0 / d.Value
            assert abs(result - 4.0) < 0.0001

    def test_real_rfloordiv(self):
        with pikepdf.explicit_conversion():
            d = Dictionary(Value=Real(3.0))
            result = 10.0 // d.Value
            assert result == 3.0

    def test_real_rmod(self):
        with pikepdf.explicit_conversion():
            d = Dictionary(Value=Real(3.0))
            result = 10.0 % d.Value
            assert abs(result - 1.0) < 0.0001

    def test_real_floordiv(self):
        with pikepdf.explicit_conversion():
            d = Dictionary(Value=Real(10.0))
            result = d.Value // 3.0
            assert result == 3.0

    def test_real_mod(self):
        with pikepdf.explicit_conversion():
            d = Dictionary(Value=Real(10.0))
            result = d.Value % 3.0
            assert abs(result - 1.0) < 0.0001


class TestUnaryOperators:
    """Tests for unary operators."""

    def test_integer_pos(self):
        with pikepdf.explicit_conversion():
            d = Dictionary(Value=42)
            result = +d.Value
            assert result == 42
            assert type(result) is int

    def test_integer_pos_negative(self):
        with pikepdf.explicit_conversion():
            d = Dictionary(Value=-42)
            result = +d.Value
            assert result == -42

    def test_real_pos(self):
        with pikepdf.explicit_conversion():
            d = Dictionary(Value=Real(3.5))
            result = +d.Value
            assert abs(result - 3.5) < 0.0001
            assert type(result) is float

    def test_real_pos_negative(self):
        with pikepdf.explicit_conversion():
            d = Dictionary(Value=Real(-3.5))
            result = +d.Value
            assert abs(result + 3.5) < 0.0001


class TestDivisionByZero:
    """Tests for division by zero edge cases."""

    def test_truediv_by_zero_float(self):
        with pikepdf.explicit_conversion():
            d = Dictionary(Value=10)
            with pytest.raises(ValueError, match="division by zero"):
                d.Value / 0.0

    def test_truediv_by_zero_int(self):
        with pikepdf.explicit_conversion():
            d = Dictionary(Value=10)
            with pytest.raises(ValueError, match="division by zero"):
                d.Value / 0

    def test_rtruediv_by_zero_integer(self):
        with pikepdf.explicit_conversion():
            d = Dictionary(Value=0)
            with pytest.raises(ValueError, match="division by zero"):
                10.0 / d.Value

    def test_rtruediv_by_zero_integer_int_operand(self):
        with pikepdf.explicit_conversion():
            d = Dictionary(Value=0)
            with pytest.raises(ValueError, match="division by zero"):
                10 / d.Value

    def test_floordiv_by_zero_float(self):
        with pikepdf.explicit_conversion():
            d = Dictionary(Value=10)
            with pytest.raises(ValueError, match="division by zero"):
                d.Value // 0.0

    def test_rfloordiv_by_zero_integer(self):
        with pikepdf.explicit_conversion():
            d = Dictionary(Value=0)
            with pytest.raises(ValueError, match="division by zero"):
                10 // d.Value

    def test_rfloordiv_by_zero_float(self):
        with pikepdf.explicit_conversion():
            d = Dictionary(Value=0)
            with pytest.raises(ValueError, match="division by zero"):
                10.0 // d.Value

    def test_mod_by_zero_float(self):
        with pikepdf.explicit_conversion():
            d = Dictionary(Value=10)
            with pytest.raises(ValueError, match="modulo by zero"):
                d.Value % 0.0

    def test_rmod_by_zero_integer(self):
        with pikepdf.explicit_conversion():
            d = Dictionary(Value=0)
            with pytest.raises(ValueError, match="modulo by zero"):
                10 % d.Value

    def test_rmod_by_zero_float(self):
        with pikepdf.explicit_conversion():
            d = Dictionary(Value=0)
            with pytest.raises(ValueError, match="modulo by zero"):
                10.0 % d.Value

    def test_real_truediv_by_zero(self):
        with pikepdf.explicit_conversion():
            d = Dictionary(Value=Real(10.0))
            with pytest.raises(ValueError, match="division by zero"):
                d.Value / 0.0

    def test_real_rtruediv_by_zero(self):
        with pikepdf.explicit_conversion():
            d = Dictionary(Value=Real(0.0))
            with pytest.raises(ValueError, match="division by zero"):
                10.0 / d.Value

    def test_real_floordiv_by_zero(self):
        with pikepdf.explicit_conversion():
            d = Dictionary(Value=Real(10.0))
            with pytest.raises(ValueError, match="division by zero"):
                d.Value // 0.0

    def test_real_rfloordiv_by_zero(self):
        with pikepdf.explicit_conversion():
            d = Dictionary(Value=Real(0.0))
            with pytest.raises(ValueError, match="division by zero"):
                10.0 // d.Value

    def test_real_mod_by_zero(self):
        with pikepdf.explicit_conversion():
            d = Dictionary(Value=Real(10.0))
            with pytest.raises(ValueError, match="modulo by zero"):
                d.Value % 0.0

    def test_real_rmod_by_zero(self):
        with pikepdf.explicit_conversion():
            d = Dictionary(Value=Real(0.0))
            with pytest.raises(ValueError, match="modulo by zero"):
                10.0 % d.Value


class TestIntIntConversions:
    """Tests for __int__ and __index__ methods."""

    def test_int_on_non_integer_raises(self):
        with pikepdf.explicit_conversion():
            d = Dictionary(Value=Real(3.14))
            with pytest.raises(TypeError, match="not an integer"):
                int(d.Value)

    def test_index_on_non_integer_raises(self):
        with pikepdf.explicit_conversion():
            d = Dictionary(Value=Real(3.14))
            items = [1, 2, 3]
            with pytest.raises(TypeError, match="not an integer"):
                items[d.Value]

    def test_float_on_non_numeric_raises(self):
        with pikepdf.explicit_conversion():
            d = Dictionary(Name=Name.Foo)
            with pytest.raises(TypeError, match="not numeric"):
                float(d.Name)


class TestRealTruedivWithInt:
    """Tests for Real true division with integer operands."""

    def test_real_truediv_int(self):
        with pikepdf.explicit_conversion():
            d = Dictionary(Value=Real(10.0))
            result = d.Value / 4
            assert abs(result - 2.5) < 0.0001

    def test_real_rtruediv_int(self):
        with pikepdf.explicit_conversion():
            d = Dictionary(Value=Real(4.0))
            result = 10 / d.Value
            assert abs(result - 2.5) < 0.0001


@pytest.fixture
def restore_global_mode():
    """Restore the global conversion mode after a test changes it."""
    old = 'explicit' if pikepdf._core._get_explicit_conversion_mode() else 'implicit'
    try:
        yield
    finally:
        pikepdf.set_object_conversion_mode(old)


class TestImplicitConversionContext:
    """Tests for the implicit_conversion() context manager."""

    def test_implicit_inside_explicit(self):
        with pikepdf.explicit_conversion():
            d = Dictionary(Value=42)
            assert isinstance(d.Value, Integer)
            with pikepdf.implicit_conversion():
                assert isinstance(d.Value, int)
                assert not isinstance(d.Value, Integer)
            assert isinstance(d.Value, Integer)

    def test_explicit_inside_implicit(self):
        with pikepdf.implicit_conversion():
            d = Dictionary(Value=42)
            assert isinstance(d.Value, int)
            with pikepdf.explicit_conversion():
                assert isinstance(d.Value, Integer)
            assert isinstance(d.Value, int)

    def test_implicit_overrides_global(self, restore_global_mode):
        pikepdf.set_object_conversion_mode('explicit')
        d = Dictionary(Value=42)
        assert isinstance(d.Value, Integer)
        with pikepdf.implicit_conversion():
            assert isinstance(d.Value, int)
            assert pikepdf.get_object_conversion_mode() == 'implicit'
        assert isinstance(d.Value, Integer)

    def test_deeply_nested(self):
        with pikepdf.explicit_conversion():
            with pikepdf.implicit_conversion():
                with pikepdf.explicit_conversion():
                    assert pikepdf.get_object_conversion_mode() == 'explicit'
                assert pikepdf.get_object_conversion_mode() == 'implicit'
            assert pikepdf.get_object_conversion_mode() == 'explicit'

    def test_out_of_order_exit_does_not_corrupt_stack(self):
        # Exiting an outer context manager before an inner one must not leave
        # the thread-local stack in a state that leaks into later code.
        cm1 = pikepdf.explicit_conversion()
        cm2 = pikepdf.implicit_conversion()
        cm1.__enter__()
        cm2.__enter__()
        cm1.__exit__(None, None, None)
        assert pikepdf.get_object_conversion_mode() == 'implicit'
        cm2.__exit__(None, None, None)
        assert pikepdf.get_object_conversion_mode() == 'implicit'


class TestPerPdfConversionMode:
    """Tests for the per-Pdf conversion mode."""

    def test_new_default_is_none(self):
        pdf = pikepdf.Pdf.new()
        assert pdf.conversion_mode is None

    def test_new_with_mode(self):
        pdf = pikepdf.Pdf.new(conversion_mode='explicit')
        assert pdf.conversion_mode == 'explicit'
        pdf.Root.Test = 42
        assert isinstance(pdf.Root.Test, Integer)

    def test_open_with_mode(self, resources):
        pdf = pikepdf.open(
            resources / 'pal-1bit-trivial.pdf', conversion_mode='explicit'
        )
        assert pdf.conversion_mode == 'explicit'
        assert isinstance(pdf.pages[0].obj.MediaBox[2], Integer | Real)

    def test_open_default_is_none(self, resources):
        pdf = pikepdf.open(resources / 'pal-1bit-trivial.pdf')
        assert pdf.conversion_mode is None

    def test_property_set_get(self):
        pdf = pikepdf.Pdf.new()
        pdf.Root.Test = 42
        assert isinstance(pdf.Root.Test, int)
        pdf.conversion_mode = 'explicit'
        assert pdf.conversion_mode == 'explicit'
        assert isinstance(pdf.Root.Test, Integer)
        pdf.conversion_mode = 'implicit'
        assert pdf.conversion_mode == 'implicit'
        assert isinstance(pdf.Root.Test, int)
        pdf.conversion_mode = None
        assert pdf.conversion_mode is None

    def test_property_invalid_value(self):
        pdf = pikepdf.Pdf.new()
        with pytest.raises(ValueError):
            pdf.conversion_mode = 'sometimes'
        with pytest.raises(ValueError):
            pdf.conversion_mode = 42

    def test_new_invalid_value(self):
        with pytest.raises(ValueError):
            pikepdf.Pdf.new(conversion_mode='sometimes')

    def test_open_invalid_value(self, resources):
        with pytest.raises(ValueError):
            pikepdf.open(
                resources / 'pal-1bit-trivial.pdf', conversion_mode='sometimes'
            )

    def test_set_object_conversion_mode_validates(self, restore_global_mode):
        with pytest.raises(ValueError):
            pikepdf.set_object_conversion_mode('sometimes')

    def test_pdf_implicit_overrides_global_explicit(self, restore_global_mode):
        pikepdf.set_object_conversion_mode('explicit')
        pdf = pikepdf.Pdf.new(conversion_mode='implicit')
        pdf.Root.Test = 42
        assert isinstance(pdf.Root.Test, int)
        assert pikepdf.get_object_conversion_mode(pdf) == 'implicit'
        assert pikepdf.get_object_conversion_mode() == 'explicit'

    def test_context_beats_pdf(self):
        pdf = pikepdf.Pdf.new(conversion_mode='explicit')
        pdf.Root.Test = 42
        assert isinstance(pdf.Root.Test, Integer)
        with pikepdf.implicit_conversion():
            assert isinstance(pdf.Root.Test, int)
            assert pikepdf.get_object_conversion_mode(pdf) == 'implicit'

    def test_unowned_object_uses_global(self, restore_global_mode):
        pdf = pikepdf.Pdf.new(conversion_mode='explicit')
        assert pdf is not None
        d = Dictionary(Value=42)  # unowned
        assert isinstance(d.Value, int)
        pikepdf.set_object_conversion_mode('explicit')
        assert isinstance(d.Value, Integer)

    def test_repr_honours_pdf_mode(self):
        pdf = pikepdf.Pdf.new(conversion_mode='explicit')
        pdf.Root.Test = 42
        pdf.Root.Flag = True
        assert 'pikepdf.Integer(42)' in repr(pdf.Root.Test)
        assert 'pikepdf.Boolean(True)' in repr(pdf.Root.Flag)
        pdf.conversion_mode = 'implicit'
        assert repr(pdf.Root.Test) == '42'

    def test_pdf_mode_visible_from_other_thread(self):
        import threading

        pdf = pikepdf.Pdf.new(conversion_mode='explicit')
        pdf.Root.Test = 42
        results = {}

        def worker():
            results['pdf_mode'] = isinstance(pdf.Root.Test, Integer)
            results['unowned'] = isinstance(Dictionary(Value=1).Value, Integer)

        with pikepdf.explicit_conversion():
            t = threading.Thread(target=worker)
            t.start()
            t.join()

        # per-Pdf explicit mode travels across threads
        assert results['pdf_mode'] is True
        # but the context manager in the main thread does not
        assert results['unowned'] is False

    def test_get_object_conversion_mode_with_pdf(self, restore_global_mode):
        pdf = pikepdf.Pdf.new()
        assert pikepdf.get_object_conversion_mode(pdf) == 'implicit'
        pikepdf.set_object_conversion_mode('explicit')
        assert pikepdf.get_object_conversion_mode(pdf) == 'explicit'
        pdf.conversion_mode = 'implicit'
        assert pikepdf.get_object_conversion_mode(pdf) == 'implicit'


class TestOwnerAdoption:
    """Direct objects inserted into a Pdf are adopted by that Pdf.

    Adoption is what makes Pdf.conversion_mode apply to objects created in the
    current session; qpdf only associates parsed objects with a document.
    """

    @pytest.fixture
    def pdf(self):
        return pikepdf.Pdf.new(conversion_mode='explicit')

    def test_scalar_adopted(self, pdf):
        pdf.Root.Test = 42
        assert isinstance(pdf.Root.Test, Integer)
        assert pdf.Root.get_raw('/Test').is_owned_by(pdf)

    def test_nested_dictionary_adopted(self, pdf):
        pdf.Root.D = Dictionary(A=1, L=[1, 2.5, True])
        assert isinstance(pdf.Root.D.A, Integer)
        assert isinstance(pdf.Root.D.L[1], Real)
        assert isinstance(pdf.Root.D.L[2], Boolean)
        assert pdf.Root.get_raw('/D').is_owned_by(pdf)
        assert pdf.Root.D.get_raw('/A').is_owned_by(pdf)
        assert pdf.Root.D.L.get_raw(pikepdf.NamePath()[1]).is_owned_by(pdf)

    def test_array_append_adopted(self, pdf):
        pdf.Root.Arr = pikepdf.Array([1])
        pdf.Root.Arr.append(2)
        assert isinstance(pdf.Root.Arr[0], Integer)
        assert isinstance(pdf.Root.Arr[1], Integer)
        assert pdf.Root.Arr.get_raw(pikepdf.NamePath()[1]).is_owned_by(pdf)

    def test_make_indirect_adopts_children(self, pdf):
        obj = pdf.make_indirect(Dictionary(A=1))
        assert obj.is_owned_by(pdf)
        assert obj.get_raw('/A').is_owned_by(pdf)
        assert isinstance(obj.A, Integer)

    def test_stream_dict_adopted(self, pdf):
        stream = pikepdf.Stream(pdf, b'x', Width=3)
        assert isinstance(stream.Width, Integer)
        assert stream.stream_dict.get_raw('/Width').is_owned_by(pdf)

    def test_unowned_objects_unaffected(self, pdf):
        # Touching the explicit-mode Pdf must not leak its mode to objects
        # that belong to no document.
        pdf.Root.Test = 42
        assert isinstance(pdf.Root.Test, Integer)
        assert type(pikepdf.Integer(5)) is int  # noqa: E721
        assert type(Dictionary(Q=7).Q) is int  # noqa: E721

    def test_scalars_are_adopted_by_copy(self, pdf):
        # A Name or String held in a module-level constant may be inserted into
        # any number of documents: adoption copies scalars, so the caller's
        # object stays unowned.
        name = Name.Foo
        string = pikepdf.String('x')
        with pikepdf.explicit_conversion():
            integer = Integer(5)

        other = pikepdf.Pdf.new()
        for doc in (pdf, other):
            doc.Root.X = name
            doc.Root.Y = string
            doc.Root.Z = integer

        assert not name.is_owned_by(pdf)
        assert not name.is_owned_by(other)
        assert not string.is_owned_by(pdf)
        assert not integer.is_owned_by(pdf)
        for doc in (pdf, other):
            assert doc.Root.get_raw('/X').is_owned_by(doc)
            assert doc.Root.get_raw('/Y').is_owned_by(doc)
            assert doc.Root.get_raw('/Z').is_owned_by(doc)

    def test_container_child_scalar_replaced_by_copy(self, pdf):
        name = Name.Foo
        d = Dictionary(N=name)
        pdf.Root.D = d
        # The child was replaced by an adopted copy...
        assert d.get_raw('/N').is_owned_by(pdf)
        assert not name.is_owned_by(pdf)
        # ...but the container itself is still the caller's object.
        assert pdf.Root.D.same_owner_as(d)
        d.More = 7
        assert isinstance(pdf.Root.D.More, Integer)
        assert pdf.Root.D.More == 7

    def test_adopted_object_is_foreign_elsewhere(self, pdf):
        d = Dictionary(A=1)
        pdf.Root.D = d
        other = pikepdf.Pdf.new()
        with pytest.raises(pikepdf.ForeignObjectError):
            other.Root.D = d

    def test_adoption_does_not_claim_foreign_objects(self, pdf, resources):
        src = pikepdf.open(resources / 'pal-1bit-trivial.pdf')
        with pytest.raises(pikepdf.ForeignObjectError):
            pdf.Root.Page = src.Root.Pages
        assert not src.Root.Pages.is_owned_by(pdf)


class TestBoolOfScalars:
    """bool() of a scalar Object reports its value, not an internal error."""

    def test_bool_integer(self):
        with pikepdf.explicit_conversion():
            assert bool(Integer(0)) is False
            assert bool(Integer(3)) is True
            assert bool(Integer(-1)) is True

    def test_bool_real(self):
        with pikepdf.explicit_conversion():
            assert bool(Real('0.0')) is False
            assert bool(Real('0.5')) is True
            assert bool(Real('-0.5')) is True

    def test_bool_via_get_raw(self):
        d = Dictionary(Zero=0, Three=3, RealZero=Real('0.000'))
        assert bool(d.get_raw('/Zero')) is False
        assert bool(d.get_raw('/Three')) is True
        assert bool(d.get_raw('/RealZero')) is False

    def test_bool_unchanged_for_other_types(self):
        assert bool(Dictionary()) is False
        assert bool(Dictionary(A=1)) is True
        assert bool(pikepdf.Array()) is False
        assert bool(pikepdf.String('')) is False
        assert bool(pikepdf.String('x')) is True
        assert bool(Name.Foo) is True


@pytest.fixture
def coercibles():
    """A dictionary of the values in the coercion truth table."""
    return Dictionary(
        Int42=42,
        Real39=Real('3.9'),
        BoolTrue=True,
        Int1=1,
        Str7=pikepdf.String('7'),
        StrExp=pikepdf.String('1e-5'),
        StrAbc=pikepdf.String('abc'),
        StrPadded=pikepdf.String('  12 '),
        StrHex=pikepdf.String('0x10'),
        StrInf=pikepdf.String('inf'),
    )


SENTINEL = object()

# key -> (no coerce, coerce) expected results; SENTINEL means "default returned"
AS_INT_TABLE = {
    '/Int42': (42, 42),
    '/Real39': (SENTINEL, 3),
    '/BoolTrue': (SENTINEL, SENTINEL),
    '/Int1': (1, 1),
    '/Str7': (SENTINEL, 7),
    '/StrExp': (SENTINEL, 0),
    '/StrAbc': (SENTINEL, SENTINEL),
    '/StrHex': (SENTINEL, SENTINEL),
    '/StrInf': (SENTINEL, SENTINEL),
    '/StrPadded': (SENTINEL, 12),
}

AS_BOOL_TABLE = {
    '/Int42': (SENTINEL, True),
    '/Real39': (SENTINEL, True),
    '/BoolTrue': (True, True),
    '/Int1': (SENTINEL, True),
    '/Str7': (SENTINEL, SENTINEL),
    '/StrExp': (SENTINEL, SENTINEL),
    '/StrAbc': (SENTINEL, SENTINEL),
    '/StrHex': (SENTINEL, SENTINEL),
    '/StrInf': (SENTINEL, SENTINEL),
    '/StrPadded': (SENTINEL, SENTINEL),
}

AS_FLOAT_TABLE = {
    '/Int42': (42.0, 42.0),
    '/Real39': (3.9, 3.9),
    '/BoolTrue': (SENTINEL, SENTINEL),
    '/Int1': (1.0, 1.0),
    '/Str7': (SENTINEL, 7.0),
    '/StrExp': (SENTINEL, 1e-5),
    '/StrAbc': (SENTINEL, SENTINEL),
    '/StrHex': (SENTINEL, SENTINEL),
    '/StrInf': (SENTINEL, SENTINEL),
    '/StrPadded': (SENTINEL, 12.0),
}

AS_DECIMAL_TABLE = {
    '/Int42': (SENTINEL, Decimal(42)),
    '/Real39': (Decimal('3.9'), Decimal('3.9')),
    '/BoolTrue': (SENTINEL, SENTINEL),
    '/Int1': (SENTINEL, Decimal(1)),
    '/Str7': (SENTINEL, Decimal('7')),
    '/StrExp': (SENTINEL, Decimal('1e-5')),
    '/StrAbc': (SENTINEL, SENTINEL),
    '/StrHex': (SENTINEL, SENTINEL),
    '/StrInf': (SENTINEL, SENTINEL),
    '/StrPadded': (SENTINEL, Decimal('12')),
}


class TestCoercionTruthTable:
    """The coercion behaviour of as_int/as_bool/as_float/as_decimal."""

    @staticmethod
    def _check(coercibles, accessor, table):
        marker = object()
        for key, (plain, coerced) in table.items():
            obj = coercibles.get_raw(key)
            for coerce, expected in ((False, plain), (True, coerced)):
                result = getattr(obj, accessor)(marker, coerce=coerce)
                if expected is SENTINEL:
                    assert result is marker, (accessor, key, coerce)
                else:
                    assert result == expected, (accessor, key, coerce)
                    assert type(result) is type(expected), (accessor, key, coerce)
                # The no-default overload raises instead of returning default
                if expected is SENTINEL:
                    with pytest.raises(TypeError):
                        getattr(obj, accessor)(coerce=coerce)
                else:
                    assert getattr(obj, accessor)(coerce=coerce) == expected

    def test_as_int(self, coercibles):
        self._check(coercibles, 'as_int', AS_INT_TABLE)

    def test_as_bool(self, coercibles):
        self._check(coercibles, 'as_bool', AS_BOOL_TABLE)

    def test_as_float(self, coercibles):
        self._check(coercibles, 'as_float', AS_FLOAT_TABLE)

    def test_as_decimal(self, coercibles):
        self._check(coercibles, 'as_decimal', AS_DECIMAL_TABLE)

    def test_coerce_is_keyword_only(self, coercibles):
        obj = coercibles.get_raw('/Real39')
        with pytest.raises(TypeError):
            obj.as_int(None, True)  # type: ignore[call-arg]

    def test_default_coerce_is_false(self, coercibles):
        obj = coercibles.get_raw('/Real39')
        assert obj.as_int(None) is None
        with pytest.raises(TypeError):
            obj.as_int()

    def test_as_bool_zero_is_false(self):
        d = Dictionary(Zero=0, RealZero=Real('0.0'), Neg=-3)
        assert d.get_raw('/Zero').as_bool(coerce=True) is False
        assert d.get_raw('/RealZero').as_bool(coerce=True) is False
        assert d.get_raw('/Neg').as_bool(coerce=True) is True

    def test_as_int_truncates_toward_zero(self):
        d = Dictionary(A=Real('3.9'), B=Real('-3.9'))
        assert d.get_raw('/A').as_int(coerce=True) == 3
        assert d.get_raw('/B').as_int(coerce=True) == -3

    def test_as_decimal_preserves_digits(self):
        d = Dictionary(A=pikepdf.String('1.100'))
        assert str(d.get_raw('/A').as_decimal(coerce=True)) == '1.100'

    def test_overflow_from_string(self):
        d = Dictionary(A=pikepdf.String('99999999999999999999'))
        with pytest.raises(OverflowError):
            d.get_raw('/A').as_int(coerce=True)
        # With a default supplied, an out-of-range value is a value the caller
        # cannot use, so the default is returned instead of raising.
        assert d.get_raw('/A').as_int(None, coerce=True) is None
        assert d.get_raw('/A').as_int(0, coerce=True) == 0

    def test_overflow_with_default_from_get_int(self):
        d = Dictionary(S=pikepdf.String('99999999999999999999'))
        assert d.get_int('/S', 0, coerce=True) == 0

    def test_overflow_from_real(self):
        d = Dictionary(A=Real('1e30'))
        with pytest.raises(OverflowError):
            d.get_raw('/A').as_int(coerce=True)

    def test_no_coercion_of_names_and_nulls(self):
        # A null stored in a dictionary is indistinguishable from an absent
        # key, so hold both values in an array.
        d = pikepdf.Object.parse(b'<< /Arr [ /Foo null ] >>')
        for index in (0, 1):
            obj = d.get_raw(pikepdf.NamePath('/Arr')[index])
            for accessor in ('as_int', 'as_bool', 'as_float', 'as_decimal'):
                assert getattr(obj, accessor)(None, coerce=True) is None

    def test_type_error_messages(self, coercibles):
        with pytest.raises(TypeError, match='Expected integer, got string'):
            coercibles.get_raw('/Str7').as_int()
        with pytest.raises(TypeError, match='Expected boolean, got integer'):
            coercibles.get_raw('/Int42').as_bool()
        with pytest.raises(TypeError, match='Expected numeric, got string'):
            coercibles.get_raw('/Str7').as_float()
        with pytest.raises(TypeError, match='Expected real, got integer'):
            coercibles.get_raw('/Int42').as_decimal()


class TestAsDictAsList:
    def test_as_dict_ok(self):
        assert dict(Dictionary(A=1).as_dict()) == {'/A': 1}

    def test_as_list_ok(self):
        assert list(pikepdf.Array([1, 2]).as_list()) == [1, 2]

    def test_as_dict_type_error(self):
        with pytest.raises(TypeError, match='Expected dictionary, got array'):
            pikepdf.Array([1]).as_dict()

    def test_as_list_type_error(self):
        with pytest.raises(TypeError, match='Expected array, got dictionary'):
            Dictionary(A=1).as_list()

    def test_as_dict_stream_type_error(self):
        pdf = pikepdf.Pdf.new()
        stream = pikepdf.Stream(pdf, b'abc')
        with pytest.raises(TypeError, match='Expected dictionary, got stream'):
            stream.as_dict()
        assert stream.as_dict(None) is None

    def test_as_dict_default(self):
        marker = object()
        assert pikepdf.Array([1]).as_dict(marker) is marker
        assert dict(Dictionary(A=1).as_dict(marker)) == {'/A': 1}

    def test_as_list_default(self):
        marker = object()
        assert Dictionary(A=1).as_list(marker) is marker
        assert list(pikepdf.Array([1]).as_list(marker)) == [1]

    def test_scalar_type_errors(self):
        with pikepdf.explicit_conversion():
            i = Integer(1)
        with pytest.raises(TypeError, match='Expected array, got integer'):
            i.as_list()
        with pytest.raises(TypeError, match='Expected dictionary, got integer'):
            i.as_dict()


class TestLocaleIndependence:
    """Number parsing must not depend on LC_NUMERIC."""

    def test_parse_under_comma_decimal_locale(self):
        candidates = ['de_DE.UTF-8', 'de_DE', 'fr_FR.UTF-8', 'fr_FR']
        saved = locale.setlocale(locale.LC_NUMERIC)
        for candidate in candidates:
            try:
                locale.setlocale(locale.LC_NUMERIC, candidate)
                break
            except locale.Error:
                continue
        else:
            pytest.skip('no comma-decimal locale available')
        try:
            # Sanity check: this locale really does use ',' as separator.
            assert locale.localeconv()['decimal_point'] == ','
            with pikepdf.explicit_conversion():
                assert pikepdf.String('3.5').as_float(coerce=True) == 3.5
                assert pikepdf.String('3.5').as_decimal(coerce=True) == Decimal('3.5')
                assert bool(Real('0.5')) is True
                assert bool(Real('0.0')) is False
        finally:
            locale.setlocale(locale.LC_NUMERIC, saved)


class TestRealValidation:
    """Real objects holding non-numeric tokens are rejected consistently."""

    def test_as_decimal_rejects_nan_token(self):
        with pikepdf.explicit_conversion():
            nan = Real('nan')
            assert nan.as_decimal(default=None) is None
            with pytest.raises(TypeError):
                nan.as_decimal()
            assert nan.as_float(default=None) is None

    def test_as_decimal_rejects_inf_token(self):
        with pikepdf.explicit_conversion():
            inf = Real('inf')
            assert inf.as_decimal(default=None) is None
            assert inf.as_float(default=None) is None


class TestOrderingComparisons:
    """Integer and Real support <, <=, >, >= against numbers and each other."""

    def test_integer_vs_int(self):
        with pikepdf.explicit_conversion():
            i = Integer(5)
            assert i < 6
            assert i <= 5
            assert i > 4
            assert i >= 5
            assert not (i < 5)
            assert not (i > 5)

    def test_reflected_int_vs_integer(self):
        with pikepdf.explicit_conversion():
            i = Integer(5)
            assert 4 < i
            assert 5 <= i
            assert 6 > i
            assert 5 >= i

    def test_integer_vs_float_and_decimal(self):
        with pikepdf.explicit_conversion():
            i = Integer(5)
            assert i < 5.5
            assert i > Decimal('4.5')
            assert 5.5 > i
            assert Decimal('4.5') < i

    def test_real_vs_numbers(self):
        with pikepdf.explicit_conversion():
            r = Real('3.5')
            assert r < 4
            assert r > 3
            assert r <= 3.5
            assert r >= 3.5
            assert r < Decimal('3.51')
            assert r > Decimal('3.49')
            assert 3 < r
            assert 4.0 > r
            assert Decimal('3.5') <= r

    def test_real_is_compared_exactly(self):
        # Decimal semantics: no binary float rounding of the token text.
        with pikepdf.explicit_conversion():
            r = Real('0.1')
            assert r == Decimal('0.1')
            assert not (r < Decimal('0.1'))
            assert not (r > Decimal('0.1'))

    def test_integer_vs_integer_and_real(self):
        with pikepdf.explicit_conversion():
            assert Integer(1) < Integer(2)
            assert Integer(2) >= Integer(2)
            assert Integer(3) < Real('3.5')
            assert Real('3.5') > Integer(3)
            assert Real('1.25') < Real('1.5')
            assert Real('1.5') >= Real('1.5')

    def test_bool_operand(self):
        # bool is an int subclass in Python, so it compares as 0/1.
        with pikepdf.explicit_conversion():
            assert Integer(0) >= False
            assert Integer(2) > True
            assert Real('0.5') > False

    def test_sorting_and_min_max(self):
        with pikepdf.explicit_conversion():
            values = [Integer(3), Real('1.5'), Integer(-1), Real('2.25')]
            assert [float(v) for v in sorted(values)] == [-1.0, 1.5, 2.25, 3.0]
            assert min(values) == -1
            assert max(values) == 3

    def test_via_get_raw_in_implicit_mode(self):
        d = Dictionary(A=1, B=Real('2.5'))
        assert d.get_raw('/A') < d.get_raw('/B')
        assert d.get_raw('/B') > 2

    def test_mediabox_style_use(self, resources):
        with pikepdf.open(resources / 'graph.pdf', conversion_mode='explicit') as pdf:
            box = pdf.pages[0].MediaBox
            assert box[0] < box[2]
            assert box[1] < box[3]
            assert box[2] > 0

    @pytest.mark.parametrize('op', ['<', '<=', '>', '>='])
    def test_non_numeric_object_raises_typeerror(self, op):
        with pikepdf.explicit_conversion():
            for obj in (Name.Foo, pikepdf.String('x'), Dictionary(), Boolean(True)):
                with pytest.raises(TypeError):
                    eval(f'obj {op} 1', {'obj': obj})
                with pytest.raises(TypeError):
                    eval(f'1 {op} obj', {'obj': obj})

    @pytest.mark.parametrize('op', ['<', '<=', '>', '>='])
    def test_unsupported_other_operand_raises_typeerror(self, op):
        with pikepdf.explicit_conversion():
            for other in ('1', None, [1], Name.Foo):
                with pytest.raises(TypeError):
                    eval(f'obj {op} other', {'obj': Integer(1), 'other': other})
                with pytest.raises(TypeError):
                    eval(f'obj {op} other', {'obj': Real('1.5'), 'other': other})

    def test_unparseable_real_raises_typeerror(self):
        with pikepdf.explicit_conversion():
            for r in (Real('nan'), Real('inf')):
                assert isinstance(r, Real)
                with pytest.raises(TypeError, match='not a valid number'):
                    _ = r < 2
                with pytest.raises(TypeError, match='not a valid number'):
                    _ = 2 >= r

    def test_equality_unchanged(self):
        with pikepdf.explicit_conversion():
            assert Integer(5) == 5
            assert Integer(5) != 6
            assert Real('1.5') == 1.5
