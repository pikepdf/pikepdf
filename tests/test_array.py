# SPDX-FileCopyrightText: 2026 James R. Barlow
# SPDX-FileCopyrightText: 2026 qooxzuub
# SPDX-License-Identifier: CC0-1.0
from __future__ import annotations

import pytest

import pikepdf
from pikepdf import Array, Dictionary, Name, String


class TestArrayMethods:
    def test_clear(self):
        a = Array([1, 2, 3])
        a.clear()
        assert len(a) == 0
        assert a == []

    def test_reverse(self):
        a = Array([1, 2, 3])
        a.reverse()
        assert a == [3, 2, 1]

    def test_reverse_empty_and_single(self):
        for items in ([], [1], [1, 2]):
            a = Array(items)
            a.reverse()
            assert list(a) == list(reversed(items))

    def test_insert(self):
        a = Array([1, 3])
        a.insert(1, 2)
        assert a == [1, 2, 3]
        a.insert(100, 4)  # Clamp to end
        assert a[-1] == 4
        a.insert(-100, 0)  # Clamp to start
        assert a[0] == 0

    def test_pop(self):
        a = Array([10, 20, 30])
        assert a.pop() == 30
        assert a == [10, 20]
        assert a.pop(0) == 10
        with pytest.raises(IndexError):
            a.pop(50)

    def test_sort_not_implemented(self):
        a = Array([3, 2, 1])
        with pytest.raises(ValueError, match="cannot get key '/sort'"):
            a.sort()

    def test_ensure_array_dict_error_messages(self):
        d = Dictionary(Foo=1)
        with pytest.raises(TypeError, match=r"not an Array: cannot clear"):
            d.clear()
        with pytest.raises(TypeError, match=r"not an Array: cannot pop"):
            d.pop()

    def test_ensure_array_name_error_messages(self):
        n = Name("/NotAnArray")
        with pytest.raises(TypeError, match="cannot clear object of type name"):
            n.clear()
        with pytest.raises(TypeError, match="cannot pop object of type name"):
            n.pop()
        with pytest.raises(TypeError, match="cannot insert object of type name"):
            n.insert(0, 1)
