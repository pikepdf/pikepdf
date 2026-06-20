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
        with pytest.raises(TypeError, match="cannot reverse object of type name"):
            n.reverse()

    def test_count(self):
        a = Array([1, 2, 2, 3, Name.Foo])
        assert a.count(2) == 2
        assert a.count(Name.Foo) == 1
        assert a.count(42) == 0

    def test_index(self):
        a = Array([Name.A, Name.B, Name.C])
        assert a.index(Name.B) == 1
        with pytest.raises(ValueError, match="item not in array"):
            a.index(Name.Z)

    def test_remove(self):
        a = Array([1, 2, 2, 3])
        a.remove(2)
        assert a == [1, 2, 3]
        with pytest.raises(ValueError, match="item not in array"):
            a.remove(42)

    def test_search_failures(self):
        a = Array([1, 2, 3])
        with pytest.raises(ValueError, match="item not in array"):
            a.remove(99)
        with pytest.raises(ValueError, match="item not in array"):
            a.index(99)

    def test_getitem_robustness(self):
        a = Array([10, 11, 12, 13, 14])
        assert list(a[1:4]) == [11, 12, 13], "Basic slice read failed"
        assert list(a[::2]) == [10, 12, 14], "Stride slice read failed"
        assert list(a[::-1]) == [14, 13, 12, 11, 10], "Negative stride read failed"
        d = Dictionary(Foo=a)
        assert list(d.Foo[0:1]) == [10]
        with pytest.raises(TypeError, match="not an Array: cannot slice"):
            _ = d[1:4]

    def test_broken_slice_index(self):
        a = Array([1, 2, 3])

        class BrokenIndex:
            def __index__(self):
                raise MemoryError("bad index")

        with pytest.raises(MemoryError):
            _ = a[BrokenIndex() :]

    def test_slice_del_edge_cases(self):
        a = Array(range(10))
        del a[1:4]
        assert list(a) == [0, 4, 5, 6, 7, 8, 9]

        a = Array(range(10))
        del a[::2]
        assert list(a) == [1, 3, 5, 7, 9]

        a = Array(range(10))
        del a[::-2]
        assert list(a) == [0, 2, 4, 6, 8]

    def test_slice_deletion_robustness(self):
        a = Array([0, 1, 2, 3, 4, 5, 6])
        del a[1:6:2]
        assert list(a) == [0, 2, 4, 6], "Positive stride deletion failed"

        b = Array([0, 1, 2, 3, 4, 5, 6])
        del b[5:0:-2]
        assert list(b) == [0, 2, 4, 6], "Negative stride deletion failed"

        c = Array([0, 1, 2, 3, 4, 5, 6])
        del c[::-1]
        assert len(c) == 0, "Full reverse deletion failed"

        d = Array([0, 1, 2, 3])
        del d[2:]
        assert list(d) == [0, 1], "End-capped slice deletion failed"

    def test_dictionary_del_still_works(self):
        d = pikepdf.Dictionary(Foo=1, Bar=2)
        del d.Foo
        assert "/Foo" not in d
        assert "/Bar" in d
        del d["/Bar"]
        assert len(d) == 0
