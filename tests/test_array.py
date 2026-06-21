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
        with pytest.raises(TypeError, match="cannot count object of type name"):
            n.count(1)
        with pytest.raises(TypeError, match="cannot index object of type name"):
            n.index(1)
        with pytest.raises(TypeError, match="cannot remove object of type name"):
            n.remove(1)

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

    def test_slice_setitem(self):
        a = Array([0, 1, 2, 3])
        a[1:3] = [8, 9]
        assert list(a) == [0, 8, 9, 3]

        a[1:2] = [10, 11, 12]  # grow
        assert list(a) == [0, 10, 11, 12, 9, 3]

        a[1:4] = [99]  # shrink
        assert list(a) == [0, 99, 9, 3]

        b = Array([0, 1, 2, 3, 4])
        b[::2] = [10, 20, 30]  # extended, one-to-one
        assert list(b) == [10, 1, 20, 3, 30]

        with pytest.raises(ValueError, match="attempt to assign sequence of size 2"):
            b[::2] = [1, 2]

        c = Array([1, 2, 3])
        c[:] = Array([7, 8, 9])  # assign from another pikepdf.Array
        assert list(c) == [7, 8, 9]

    def test_array_setitem_positive(self):
        arr = Array([10, 20, 30])
        arr[1] = 40
        assert arr[1] == 40

    def test_array_setitem_negative(self):
        arr = Array([10, 20, 30])
        arr[-1] = 99
        assert arr[2] == 99

    def test_array_setitem_out_of_range(self):
        arr = Array([1, 2])
        with pytest.raises(IndexError, match="array index out of range"):
            arr[5] = 10
        with pytest.raises(IndexError, match="array index out of range"):
            arr[-5] = 10

    def test_setitem_on_non_array(self):
        d = Dictionary(Foo=1)
        with pytest.raises(TypeError, match="not an Array"):
            d[0] = 2

    def test_array_slice_errors(self):
        arr = Array([1, 2, 3])
        with pytest.raises(ValueError, match="slice step"):
            _ = arr[::0]
        with pytest.raises(ValueError, match="slice step"):
            del arr[::0]
        with pytest.raises(ValueError, match="slice step"):
            arr[::0] = Array([1, 2])

    def test_error_consistency(self):
        a = Array(range(5))
        lst = list(range(5))
        msg_list = msg_pike = ""
        try:
            lst[1:3] = 42
        except TypeError as e_list:
            msg_list = str(e_list)
        try:
            a[1:3] = 42
        except TypeError as e_pike:
            msg_pike = str(e_pike)
        assert "can only assign an iterable" in msg_pike or msg_list == msg_pike

    def test_generator_error_propagates(self):
        a = Array([1, 2, 3])

        def exploding_generator():
            yield 1
            raise RuntimeError("Boom")

        with pytest.raises(RuntimeError, match="Boom"):
            a[0:1] = exploding_generator()

    def test_copy(self):
        a = Array([1, 2])
        b = a.copy()
        assert a == b
        assert a is not b

    def test_array_copy(self):
        inner = [1, 2]
        a = Array([inner, 3])
        b = a.copy()
        assert a == b
        a[0].append(3)
        assert 3 not in b[0]

    def test_dictionary_copy(self):
        d = Dictionary(Foo=Array([1, 2]))
        d2 = d.copy()
        assert d == d2
        d.Foo.append(3)
        assert 3 not in d2.Foo

    def test_slice_setitem_on_non_array(self):
        d = Dictionary(Foo=1)
        with pytest.raises(TypeError, match="not an Array: cannot set slice"):
            d[0:1] = [1, 2]


class TestArrayTypeErrors:
    """Type error handling for Array operations."""

    def test_string_containment_ambiguity(self):
        with pytest.raises(TypeError, match="ambiguity"):
            "a" in Array([String("a")])
