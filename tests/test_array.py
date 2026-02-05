# SPDX-FileCopyrightText: 2026 James R. Barlow
# SPDX-FileCopyrightText: 2026 qooxzuub
# SPDX-License-Identifier: CC0-1.0
from __future__ import annotations

import pytest

import pikepdf
from pikepdf import Array, Dictionary, Integer, Name, String


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
        a.insert(-100, 0)  # Clamp to start
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
        assert c is not b  # Different containers
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
        a.insert(100, 3)  # Should clamp to nitems
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

        # python changed their message; accept either in the test in case we 'upgrade'
        assert "can only assign an iterable" in msg_pike or msg_list == msg_pike

    def test_array_add_iterable(self):
        pdf = pikepdf.new()
        arr = pikepdf.Array([1, 2])

        # Test with list
        res = arr + [3, 4]
        assert isinstance(res, pikepdf.Array)
        assert list(res) == [1, 2, 3, 4]

        # Test with generator (proves iterable support)
        res2 = arr + (x for x in range(3, 5))
        assert list(res2) == [1, 2, 3, 4]

        # Ensure original is unchanged (immutability of __add__)
        assert list(arr) == [1, 2]

    def test_array_add_coverage(self):
        arr = pikepdf.Array([1, 2])

        with pytest.raises(TypeError):
            arr + None

    def test_non_array_dispatch(self):
        # If 'h' is NOT an array (e.g., a pikepdf.Name),
        # it should return NotImplemented.
        name = pikepdf.Name("/Foo")

        # Manually calling __add__ lets us see the NotImplemented return value
        assert name.__add__([1, 2]) is NotImplemented

    def test_array_slice_errors(self):
        arr = pikepdf.Array([1, 2, 3])

        with pytest.raises(ValueError, match="slice step"):
            _ = arr[::0]

        with pytest.raises(ValueError, match="slice step"):
            del arr[::0]

        with pytest.raises(ValueError, match="slice step"):
            arr[::0] = pikepdf.Array([1, 2])

    def test_array_setitem_positive(self):
        arr = pikepdf.Array([10, 20, 30])
        # This hits: h.getArrayNItems(), the 'if (index < 0)' skip,
        # and h.setArrayItem(...)
        arr[1] = 40
        assert arr[1] == 40

    def test_array_setitem_negative(self):
        arr = pikepdf.Array([10, 20, 30])
        # This hits: 'if (index < 0)' branch -> 'index += n'
        arr[-1] = 99
        assert arr[2] == 99

    def test_array_setitem_out_of_range(self):
        arr = pikepdf.Array([1, 2])

        with pytest.raises(IndexError, match="array index out of range"):
            arr[5] = 10

        with pytest.raises(IndexError, match="array index out of range"):
            arr[-5] = 10

    def test_setitem_on_non_array(self):
        # Create a Dictionary, not an Array
        d = pikepdf.Dictionary(Foo=1)

        # Passing an integer '0' as key to a Dictionary
        with pytest.raises(TypeError, match="set index"):
            d[0] = 2

    def test_array_addition(self):
        pdf = pikepdf.new()
        a = pikepdf.Array([1, 2])
        b = pikepdf.Array([3, 4])

        c = a + b
        assert list(c) == [1, 2, 3, 4]

        d = a + [5, 6]
        assert list(d) == [1, 2, 5, 6]

    def test_copy(self):
        arr = pikepdf.Array([1, 2])
        arr_copy = arr.copy()
        assert arr == arr_copy
        assert arr is not arr_copy  # Ensure it's a different object


class TestDictionaryEdgeCases:
    """Edge cases for Dictionary operations."""

    def test_invalid_utf8_key_uses_surrogateescape(self):
        """Keys with invalid UTF-8 bytes are decoded using surrogateescape."""
        d = Dictionary(Valid=1)
        # \x80 is invalid as a standalone byte in UTF-8
        d[b"/Invalid\x80"] = 2

        keys = d.keys()
        assert "/Valid" in keys
        # The invalid byte \x80 becomes the surrogate \udc80
        assert any("\udc80" in k for k in keys)
        assert any("\udc80" in k for k in iter(d))

    def test_update_from_python_dict(self):
        """Dictionary.update() accepts a Python dict."""
        d = Dictionary(A=1)
        d.update({"/B": 2})
        assert d.B == 2

    def test_update_from_pikepdf_dictionary(self):
        """Dictionary.update() accepts another pikepdf Dictionary."""
        d1 = Dictionary(A=1)
        d2 = Dictionary(C=3)
        d1.update(d2)
        assert d1.C == 3

    def test_update_rejects_stream(self):
        """Dictionary.update() rejects Stream objects."""
        pdf = pikepdf.new()
        d = Dictionary(A=1)
        stream = pdf.make_stream(b"data", Foo=1)
        with pytest.raises(TypeError, match="cannot update from a Stream"):
            d.update(stream)

    def test_update_rejects_array(self):
        """Dictionary.update() rejects Array objects."""
        d = Dictionary(A=1)
        with pytest.raises(TypeError, match="update\\(\\) argument must be a dictionary"):
            d.update(Array([1, 2, 3]))

    def test_invalid_key_type_rejected(self):
        """Dictionary rejects non-string/bytes key types."""
        d = Dictionary(Valid=1)
        with pytest.raises(TypeError, match="Key must be str or bytes"):
            d[[]] = "value"

    def test_containment_with_incompatible_type(self):
        """'in' operator returns False for incompatible types in Dictionary."""
        d = Dictionary(A=1)
        assert 123 not in d

    def test_conversion_to_python_dict(self):
        """Dictionary can be converted to a Python dict."""
        d = Dictionary(A=1, B=2)
        result = dict(d)
        assert isinstance(result, dict)
        assert "/A" in result


class TestArrayAdditionEdgeCases:
    """Edge cases for Array addition with various iterable types."""

    def test_add_with_generator(self):
        """Array + generator creates new array from yielded values."""
        a = Array([1, 2, 3])
        gen = (x for x in [4, 5])
        result = a + gen
        assert list(result) == [1, 2, 3, 4, 5]

    def test_add_with_custom_iterable(self):
        """Array + custom iterable works via iteration protocol."""

        class MyIter:
            def __iter__(self):
                yield 4

        a = Array([1, 2, 3])
        assert (a + MyIter()) == [1, 2, 3, 4]


class TestArrayTypeErrors:
    """Type error handling for Array operations."""

    def test_string_containment_ambiguity(self):
        """Python str 'in' Array[String] raises due to ambiguous comparison."""
        # A Python str could match either as a Name or String, so we reject it
        with pytest.raises(TypeError, match="ambiguity"):
            "a" in Array([String("a")])


class TestSliceAssignmentEdgeCases:
    """Edge cases for slice assignment operations."""

    def test_generator_error_propagates(self):
        """Errors raised during slice assignment iteration propagate correctly."""
        a = Array([1, 2, 3])

        def exploding_generator():
            yield 1
            raise RuntimeError("Boom")

        with pytest.raises(RuntimeError, match="Boom"):
            a[0:1] = exploding_generator()

    def test_broken_slice_index(self):
        """Errors in __index__ during slice computation propagate correctly."""
        a = Array([1, 2, 3])

        class BrokenIndex:
            def __index__(self):
                raise MemoryError("bad index")

        with pytest.raises(MemoryError):
            _ = a[BrokenIndex() :]


class TestObjectCopy:
    """Copy behavior for various PDF object types."""

    def test_name_copy(self):
        """Name objects can be copied."""
        name = Name("/foo")
        assert name.copy() == name
