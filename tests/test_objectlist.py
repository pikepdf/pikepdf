# SPDX-FileCopyrightText: 2022 James R. Barlow
# SPDX-License-Identifier: CC0-1.0

from __future__ import annotations

import sys

import pytest

import pikepdf


@pytest.fixture
def pal(resources):
    with pikepdf.open(resources / 'pal.pdf') as pdf:
        yield pdf


@pytest.mark.xfail(
    sys.platform == 'win32',
    reason="MSVC doesn't compile bind_vector<QPDFObjectHandle> properly",
)
def test_objectlist_repr(pal):
    cs = pikepdf.parse_content_stream(pal.pages[0].Contents)
    assert isinstance(cs[1][0], pikepdf._core._ObjectList)
    ol = cs[1][0]
    assert (
        "[Decimal('144.0000'), 0, 0, Decimal('144.0000'), Decimal('0.0000'), Decimal('0.0000')]"
        in repr(ol)
    )


@pytest.fixture
def numbers():
    """An _ObjectList whose elements are numeric, i.e. unwrapped to Python ints."""
    return pikepdf.ContentStreamInstruction([1, 2, 3], pikepdf.Operator('rg')).operands


@pytest.fixture
def names():
    """An _ObjectList whose elements stay pikepdf.Object."""
    return pikepdf.ContentStreamInstruction(
        [pikepdf.Name.Foo, pikepdf.Name.Bar], pikepdf.Operator('gs')
    ).operands


def test_objectlist_eq_native(numbers):
    assert numbers == [1, 2, 3]
    assert numbers == (1, 2, 3)
    assert not (numbers == [1, 2])
    assert not (numbers == [1, 2, 4])
    assert numbers != [1, 2, 4]
    assert not (numbers != [1, 2, 3])


def test_objectlist_eq_objects(names):
    assert names == [pikepdf.Name.Foo, pikepdf.Name.Bar]
    assert names != [pikepdf.Name.Bar, pikepdf.Name.Foo]


def test_objectlist_eq_self(numbers, names):
    assert numbers == numbers
    assert names == names
    assert numbers != names


def test_objectlist_eq_other_type(numbers):
    assert not (numbers == 'foo')
    assert not (numbers == 42)
    assert numbers != 'foo'
    assert not (numbers == [object()])


def test_objectlist_no_implicit_conversion_warning(numbers, capfd):
    numbers == [1, 2, 3]
    numbers == 'foo'
    numbers.count(1)
    list(numbers)
    assert 'implicit conversion' not in capfd.readouterr().err


def test_objectlist_contains(numbers, names):
    assert 1 in numbers
    assert 4 not in numbers
    assert pikepdf.Name.Foo in names
    assert pikepdf.Name.Baz not in names
    assert object() not in numbers


def test_objectlist_count(numbers, names):
    assert numbers.count(1) == 1
    assert numbers.count(9) == 0
    assert names.count(pikepdf.Name.Foo) == 1
    assert names.count(object()) == 0


def test_objectlist_remove(numbers, names):
    numbers.remove(2)
    assert numbers == [1, 3]
    with pytest.raises(ValueError):
        numbers.remove(9)
    names.remove(pikepdf.Name.Foo)
    assert names == [pikepdf.Name.Bar]


def test_objectlist_append_insert(numbers):
    numbers.append(4)
    assert numbers == [1, 2, 3, 4]
    numbers.insert(0, 0)
    assert numbers == [0, 1, 2, 3, 4]
    numbers.append(pikepdf.Name.Foo)
    assert numbers[-1] == pikepdf.Name.Foo
    with pytest.raises(RuntimeError):
        numbers.append(object())


def test_objectlist_extend(numbers, names):
    numbers.extend([4, 5])
    assert numbers == [1, 2, 3, 4, 5]
    numbers.extend(names)
    assert numbers == [1, 2, 3, 4, 5, pikepdf.Name.Foo, pikepdf.Name.Bar]


def test_objectlist_setitem(numbers):
    numbers[0] = 9
    assert numbers == [9, 2, 3]
    numbers[-1] = pikepdf.Name.Foo
    assert numbers == [9, 2, pikepdf.Name.Foo]
    numbers[0:2] = [7, 8]
    assert numbers == [7, 8, pikepdf.Name.Foo]
    with pytest.raises(RuntimeError):
        numbers[0] = object()


def test_objectlist_still_converts_to_cpp(numbers):
    """A mutated _ObjectList remains usable as input to bindings that take one."""
    numbers.extend([4, 5, 6])
    assert pikepdf.Matrix(numbers) == pikepdf.Matrix(1, 2, 3, 4, 5, 6)
    csi = pikepdf.ContentStreamInstruction(numbers, pikepdf.Operator('cm'))
    assert csi.operands == numbers


def test_objectlist_real_roundtrip(resources):
    """Rebuilding an instruction from its own operands preserves real numbers."""
    with pikepdf.open(resources / 'pal.pdf') as pdf:
        original = pikepdf.parse_content_stream(pdf.pages[0].Contents)
        rebuilt = [
            pikepdf.ContentStreamInstruction(instruction.operands, instruction.operator)
            for instruction in original
            if isinstance(instruction, pikepdf.ContentStreamInstruction)
        ]
        assert pikepdf.unparse_content_stream(
            rebuilt
        ) == pikepdf.unparse_content_stream(original)
