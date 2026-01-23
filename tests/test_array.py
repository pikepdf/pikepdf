# SPDX-FileCopyrightText: 2026 James R. Barlow
# SPDX-FileCopyrightText: 2026 qooxzuub
# SPDX-License-Identifier: CC0-1.0

import pytest
import pikepdf
from pikepdf import Array, Name, Dictionary, Integer

class TestArrayMethods:
    def test_clear(self):
        a = Array([1, 2, 3])
        a.clear()
        assert len(a) == 0
        assert a == []

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

    def test_insert(self):
        a = Array([1, 3])
        a.insert(1, 2)
        assert a == [1, 2, 3]
        a.insert(100, 4)  # Clamp to end
        assert a[-1] == 4
        a.insert(-100, 0) # Clamp to start
        assert a[0] == 0

    def test_pop(self):
        a = Array([10, 20, 30])
        assert a.pop() == 30
        assert a == [10, 20]
        assert a.pop(0) == 10
        with pytest.raises(IndexError):
            a.pop(50)

    def test_remove(self):
        a = Array([1, 2, 2, 3])
        a.remove(2)
        assert a == [1, 2, 3]
        with pytest.raises(ValueError, match="item not in array"):
            a.remove(42)

    def test_reverse(self):
        a = Array([1, 2, 3])
        a.reverse()
        assert a == [3, 2, 1]

    def test_copy(self):
        # Generic test for the copy() method availability
        a = Array([1, 2])
        b = a.copy()
        assert a == b
        assert a is not b

    def test_array_copy(self):
        # Specific test for direct object behavior (snapshot behavior)
        inner = [1, 2]
        a = Array([inner, 3])
        b = a.copy()
        assert a == b
        # Mutating a direct object child in 'a' does not affect 'b'
        a[0].append(3)
        assert 3 not in b[0]

    def test_dictionary_copy(self):
        d = Dictionary(Foo=Array([1, 2]))
        d2 = d.copy()
        assert d == d2
        d.Foo.append(3)
        assert 3 not in d2.Foo

    def test_ensure_array_dict_error_messages(self):
        d = Dictionary(Foo=1)
        with pytest.raises(TypeError, match=r"not an Array: cannot clear"):
            d.clear()
        with pytest.raises(TypeError, match=r"not an Array: cannot pop"):
            d.pop()

    def test_sort_not_implemented(self):
        a = Array([3, 2, 1])
        # Verify it falls back to a key lookup error rather than an AttributeError
        with pytest.raises(ValueError, match="cannot get key '/sort'"):
            a.sort()

    def test_addition_operators(self):
        # Test __iadd__ (+=)
        a = Array([1])
        a += [2]
        assert a == [1, 2]
        assert isinstance(a, Array)

        # Test __add__ (+)
        b = Array([1])
        c = b + [2]
        assert c == [1, 2]
        assert c is not b # Different containers
        assert isinstance(c, Array)


    def test_add_overload_coexistence(self):
        # Test Array addition
        a = pikepdf.Array([1])
        assert a + [2] == [1, 2]

        # Test Integer addition
        i = pikepdf.Integer(10)
        assert i + 5 == 15

        # Test mixed failure
        # We expect the standard Python 'unsupported operand' error
        # because overloads returned NotImplemented.
        with pytest.raises(TypeError, match="unsupported operand type"):
            pikepdf.Name("/Foo") + [1]

    def test_ensure_array_name_error_messages(self):
        # Hits the ensure_array() helper with different action strings
        n = Name("/NotAnArray")
        with pytest.raises(TypeError, match="cannot clear object of type name"):
            n.clear()
        with pytest.raises(TypeError, match="cannot pop object of type name"):
            n.pop()
        with pytest.raises(TypeError, match="cannot insert object of type name"):
            n.insert(0, 1)

    def test_add_not_implemented_fallback(self):
        # Ensures __add__ returns NotImplemented for non-arrays
        # so Python can raise its own standard TypeError
        i = Integer(5)
        with pytest.raises(TypeError, match="unsupported operand type"):
            i + [1, 2, 3]

    def test_insert_clamping(self):
        # Hits the index normalization logic in insert()
        a = Array([1, 2])
        a.insert(-100, 0)  # Should clamp to 0
        assert a[0] == 0
        a.insert(100, 3)   # Should clamp to nitems
        assert a[-1] == 3
        assert len(a) == 4

    def test_pop_default_and_bounds(self):
        # Hits default index=-1 and list_range_check
        a = Array([10, 20, 30])
        assert a.pop() == 30
        assert a.pop(0) == 10
        with pytest.raises(IndexError):
            a.pop(50)

    def test_slice_del_edge_cases(self):
        # Standard slice
        a = Array(range(10))
        del a[1:4]
        assert list(a) == [0, 4, 5, 6, 7, 8, 9]

        # Extended slice (stride) - Reset 'a' to keep test clear
        a = Array(range(10))
        del a[::2]
        assert list(a) == [1, 3, 5, 7, 9]

        # Negative stride
        a = Array(range(10))
        del a[::-2]
        assert list(a) == [0, 2, 4, 6, 8]


    def test_slice_deletion_robustness(self):
        # Test positive stride: delete [1, 3, 5]
        a = Array([0, 1, 2, 3, 4, 5, 6])
        del a[1:6:2]
        assert list(a) == [0, 2, 4, 6], "Positive stride deletion failed"

        # Test negative stride: delete [5, 3, 1]
        b = Array([0, 1, 2, 3, 4, 5, 6])
        del b[5:0:-2]
        assert list(b) == [0, 2, 4, 6], "Negative stride deletion failed"

        # Test full reversal deletion: delete [6, 5, 4, 3, 2, 1, 0]
        c = Array([0, 1, 2, 3, 4, 5, 6])
        del c[::-1]
        assert len(c) == 0, "Full reverse deletion failed"

        # Test slice that hits the exact end
        d = Array([0, 1, 2, 3])
        del d[2:]
        assert list(d) == [0, 1], "End-capped slice deletion failed"

    def test_search_failures(self):
        # Hits the 'item not in array' value_error paths
        a = Array([1, 2, 3])
        with pytest.raises(ValueError, match="item not in array"):
            a.remove(99)
        with pytest.raises(ValueError, match="item not in array"):
            a.index(99)

    def test_reverse_empty_and_single(self):
        # Hits the loop logic for edge cases
        for items in ([], [1], [1, 2]):
            a = Array(items)
            a.reverse()
            assert list(a) == list(reversed(items))

    def test_copy_is_shallow(self):
        # Hits the copy() implementation
        a = Array([1, 2])
        b = a.copy()
        assert a == b
        assert a is not b  # Different handles

    def test_slice_del_syntax(self):
        a = Array(range(10))
        del a[1:4]
        assert list(a) == [0, 4, 5, 6, 7, 8, 9]

    def test_dictionary_del_still_works(self):
        d = pikepdf.Dictionary(Foo=1, Bar=2)
        del d.Foo
        assert "/Foo" not in d
        assert "/Bar" in d

        # Also check string-based deletion
        del d["/Bar"]
        assert len(d) == 0

    def test_slice_setitem(self):
        # Simple replacement (Same length)
        a = Array([0, 1, 2, 3])
        a[1:3] = [8, 9]
        assert list(a) == [0, 8, 9, 3]

        # Splicing: Grow (Replace 1 item with 3)
        # This hits the eraseItem loop followed by the insertItem loop
        a[1:2] = [10, 11, 12]
        assert list(a) == [0, 10, 11, 12, 9, 3]

        # Splicing: Shrink (Replace 3 items with 1)
        # This ensures the eraseItem loop correctly reduces the size
        a[1:4] = [99]
        assert list(a) == [0, 99, 9, 3]

        # Extended slice: One-to-one replacement
        # This hits the 'else' branch (step != 1) and setArrayItem
        b = Array([0, 1, 2, 3, 4])
        b[::2] = [10, 20, 30]
        assert list(b) == [10, 1, 20, 3, 30]

        # Extended slice: Error on length mismatch
        # Hits the Python-compliance ValueError branch
        with pytest.raises(ValueError, match="attempt to assign sequence of size 2"):
            b[::2] = [1, 2]

        # Type Interop: Assigning from another pikepdf.Array
        # Ensures objecthandle_encode works on pikepdf types during assignment
        c = Array([1, 2, 3])
        c[:] = Array([7, 8, 9])
        assert list(c) == [7, 8, 9]

    def test_getitem_robustness(self):
        # Standard slice read
        a = Array([10, 11, 12, 13, 14])
        assert list(a[1:4]) == [11, 12, 13], "Basic slice read failed"

        # Extended slice read (stride)
        assert list(a[::2]) == [10, 12, 14], "Stride slice read failed"

        # Negative stride read
        assert list(a[::-1]) == [14, 13, 12, 11, 10], "Negative stride read failed"

        # Interoperability with Dictionary
        # This ensures that while a[1:2] works, d["/Key"] still works
        # and d[slice] raises the correct error.
        d = Dictionary(Foo=a)
        assert list(d.Foo[0:1]) == [10]

        # confirm we hit the right guard
        with pytest.raises(TypeError, match="not an Array: cannot slice"):
            _ = d[1:4]

    def test_error_consistency(self):
        a = pikepdf.Array(range(5))
        l = list(range(5))

        try:
            l[1:3] = 42
        except TypeError as e_list:
            msg_list = str(e_list)

        try:
            a[1:3] = 42
        except TypeError as e_pike:
            msg_pike = str(e_pike)

        assert msg_list == msg_pike
