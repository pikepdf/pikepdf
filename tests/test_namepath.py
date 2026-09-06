# SPDX-FileCopyrightText: 2025 James R. Barlow
# SPDX-License-Identifier: CC0-1.0

"""Tests for NamePath - nested dictionary/array access."""

from __future__ import annotations

import pytest

import pikepdf
from pikepdf import Array, Dictionary, Name, NamePath, String


class TestNamePathConstruction:
    """Test various ways to construct a NamePath."""

    def test_shorthand_single(self):
        """Test NamePath.Foo creates a path with one component."""
        path = NamePath.Resources
        assert repr(path) == "NamePath.Resources"
        assert len(path) == 1

    def test_shorthand_chain(self):
        """Test NamePath.A.B.C creates a multi-component path."""
        path = NamePath.Resources.Font.F1
        assert repr(path) == "NamePath.Resources.Font.F1"
        assert len(path) == 3

    def test_call_single(self):
        """Test NamePath('/A') call form."""
        path = NamePath('/Resources')
        assert repr(path) == "NamePath.Resources"
        assert len(path) == 1

    def test_call_multiple(self):
        """Test NamePath('/A', '/B') call form."""
        path = NamePath('/Resources', '/Font')
        assert repr(path) == "NamePath.Resources.Font"
        assert len(path) == 2

    def test_call_with_name(self):
        """Test NamePath(Name.A, Name.B) using Name objects."""
        path = NamePath(Name.Resources, Name.Font)
        assert repr(path) == "NamePath.Resources.Font"
        assert len(path) == 2

    def test_chained_call(self):
        """Test NamePath('/A')('/B') chained construction."""
        path = NamePath('/A')('/B')
        assert repr(path) == "NamePath.A.B"
        assert len(path) == 2

    def test_mixed_shorthand_and_call(self):
        """Test mixing NamePath.A('/B') forms."""
        path = NamePath.A('/B').C
        assert repr(path) == "NamePath.A.B.C"
        assert len(path) == 3

    def test_getitem_name(self):
        """Test NamePath['/A'] syntax for dict access."""
        path = NamePath['/Resources']
        assert repr(path) == "NamePath.Resources"
        assert len(path) == 1

        path = NamePath[Name.Resources]
        assert repr(path) == "NamePath.Resources"
        assert len(path) == 1

    def test_empty_path(self):
        """Test NamePath() creates an empty path."""
        path = NamePath()
        assert repr(path) == "NamePath"
        assert len(path) == 0
        assert not path  # bool(empty path) is False

    def test_non_empty_path_is_truthy(self):
        """Test non-empty paths are truthy."""
        path = NamePath.A
        assert path  # bool(non-empty path) is True

    def test_array_index(self):
        """Test NamePath.A[0] syntax for array access."""
        path = NamePath.Kids[0]
        assert repr(path) == "NamePath.Kids[0]"
        assert len(path) == 2

    def test_array_index_chain(self):
        """Test NamePath.A[0].B[1] mixed dict/array path."""
        path = NamePath.Pages.Kids[0].MediaBox
        assert repr(path) == "NamePath.Pages.Kids[0].MediaBox"
        assert len(path) == 4

    def test_negative_index(self):
        """Test negative indices are stored as-is."""
        path = NamePath.Kids[-1]
        assert repr(path) == "NamePath.Kids[-1]"


class TestNamePathGetItem:
    """Test Object.__getitem__ with NamePath."""

    def test_simple_get(self):
        """Test accessing nested dict with shorthand syntax."""
        pdf = pikepdf.new()
        pdf.Root.Resources = Dictionary(Font=Dictionary(F1=Name.Helvetica))
        assert pdf.Root[NamePath.Resources.Font.F1] == Name.Helvetica

    def test_canonical_get(self):
        """Test accessing nested dict with canonical syntax."""
        pdf = pikepdf.new()
        pdf.Root.Info = Dictionary(Title=String("Hello"))
        result = pdf.Root[NamePath('/Info', '/Title')]
        assert str(result) == "Hello"

    def test_array_index_get(self):
        """Test accessing array elements."""
        pdf = pikepdf.new()
        pdf.Root.Items = Array([1, 2, 3])
        assert int(pdf.Root[NamePath.Items[1]]) == 2

    def test_mixed_dict_array(self):
        """Test mixed dict/array traversal."""
        pdf = pikepdf.new()
        pdf.Root.Pages = Dictionary(Kids=Array([Dictionary(MediaBox=[0, 0, 612, 792])]))
        result = pdf.Root[NamePath.Pages.Kids[0].MediaBox]
        assert int(result[2]) == 612

    def test_empty_path_returns_self(self):
        """Test obj[NamePath()] returns obj itself."""
        pdf = pikepdf.new()
        result = pdf.Root[NamePath()]
        # Should be the same object
        assert result.objgen == pdf.Root.objgen

    def test_negative_index(self):
        """Test negative array indices work."""
        pdf = pikepdf.new()
        pdf.Root.Items = Array([1, 2, 3])
        assert int(pdf.Root[NamePath.Items[-1]]) == 3

    def test_stream_dict_traversal(self):
        """Test traversing through a stream's dictionary."""
        pdf = pikepdf.new()
        stream = pikepdf.Stream(pdf, b"test data", Filter=Name.FlateDecode)
        pdf.Root.MyStream = stream
        result = pdf.Root[NamePath.MyStream.Filter]
        assert result == Name.FlateDecode


class TestNamePathSetItem:
    """Test Object.__setitem__ with NamePath."""

    def test_simple_set(self):
        """Test setting a nested value."""
        pdf = pikepdf.new()
        pdf.Root.Info = Dictionary()
        pdf.Root[NamePath.Info.Title] = String("Test")
        assert str(pdf.Root.Info.Title) == "Test"

    def test_set_via_pyobject(self):
        """Test setting with Python native value (goes through encode)."""
        pdf = pikepdf.new()
        pdf.Root.Info = Dictionary()
        pdf.Root[NamePath.Info.Count] = 42
        assert int(pdf.Root.Info.Count) == 42

    def test_set_array_element(self):
        """Test setting an array element via NamePath."""
        pdf = pikepdf.new()
        pdf.Root.Items = Array([1, 2, 3])
        pdf.Root[NamePath.Items[1]] = 99
        assert int(pdf.Root.Items[1]) == 99

    def test_set_empty_path_error(self):
        """Test that setting with empty path raises error."""
        pdf = pikepdf.new()
        with pytest.raises(ValueError, match="Cannot assign to empty NamePath"):
            pdf.Root[NamePath()] = 42

    def test_set_empty_path_error_object_value(self):
        """Empty path with a pikepdf Object value (separate C++ overload)."""
        pdf = pikepdf.new()
        with pytest.raises(ValueError, match="Cannot assign to empty NamePath"):
            pdf.Root[NamePath()] = String("x")

    def test_set_int_index_non_array_pyvalue(self):
        pdf = pikepdf.new()
        pdf.Root.A = Dictionary()
        with pytest.raises(TypeError, match="non-Array"):
            pdf.Root[NamePath.A[0]] = 42

    def test_set_int_index_non_array_object_value(self):
        pdf = pikepdf.new()
        pdf.Root.A = Dictionary()
        with pytest.raises(TypeError, match="non-Array"):
            pdf.Root[NamePath.A[0]] = String("x")

    def test_set_int_index_out_of_range_pyvalue(self):
        pdf = pikepdf.new()
        pdf.Root.Items = Array([1, 2, 3])
        with pytest.raises(IndexError, match="out of range"):
            pdf.Root[NamePath.Items[10]] = 42

    def test_set_int_index_out_of_range_object_value(self):
        pdf = pikepdf.new()
        pdf.Root.Items = Array([1, 2, 3])
        with pytest.raises(IndexError, match="out of range"):
            pdf.Root[NamePath.Items[10]] = String("x")

    def test_set_int_index_negative_pyvalue(self):
        pdf = pikepdf.new()
        pdf.Root.Items = Array([1, 2, 3])
        pdf.Root[NamePath.Items[-1]] = 99
        assert int(pdf.Root.Items[2]) == 99

    def test_set_int_index_negative_object_value(self):
        pdf = pikepdf.new()
        pdf.Root.Items = Array([1, 2, 3])
        pdf.Root[NamePath.Items[-1]] = String("x")
        assert str(pdf.Root.Items[2]) == "x"


class TestNamePathGet:
    """Test Object.get() with NamePath and default values."""

    def test_get_existing(self):
        """Test get() returns value when path exists."""
        pdf = pikepdf.new()
        pdf.Root.A = Dictionary(B=Dictionary(C=42))
        result = pdf.Root.get(NamePath.A.B.C, "default")
        assert int(result) == 42

    def test_get_missing_returns_default(self):
        """Test get() returns default when path doesn't exist."""
        pdf = pikepdf.new()
        result = pdf.Root.get(NamePath.Missing.Path, "default")
        assert result == "default"

    def test_get_missing_returns_none_by_default(self):
        """Test get() returns None when path doesn't exist and no default."""
        pdf = pikepdf.new()
        result = pdf.Root.get(NamePath.Missing.Path)
        assert result is None

    def test_get_empty_path_returns_self(self):
        """Test get() with empty path returns self."""
        pdf = pikepdf.new()
        result = pdf.Root.get(NamePath())
        assert result.objgen == pdf.Root.objgen

    def test_get_type_mismatch_returns_default(self):
        """Test get() returns default when encountering wrong type."""
        pdf = pikepdf.new()
        pdf.Root.A = 42  # A is an integer, not a dict
        result = pdf.Root.get(NamePath.A.B, "default")
        assert result == "default"

    def test_get_index_out_of_range_returns_default(self):
        """Test get() returns default when array index is out of range."""
        pdf = pikepdf.new()
        pdf.Root.Items = Array([1, 2, 3])
        result = pdf.Root.get(NamePath.Items[10], "default")
        assert result == "default"


class TestNamePathErrors:
    """Test error handling and messages."""

    def test_key_not_found_error(self):
        """Test KeyError when key doesn't exist."""
        pdf = pikepdf.new()
        pdf.Root.A = Dictionary(B=Dictionary())
        with pytest.raises(KeyError, match="traversed NamePath.A.B"):
            pdf.Root[NamePath.A.B.C]

    def test_type_error_dict_expected(self):
        """Test TypeError when dict expected but got something else."""
        pdf = pikepdf.new()
        pdf.Root.A = 42  # Not a dict
        with pytest.raises(TypeError, match="Expected Dictionary or Stream"):
            pdf.Root[NamePath.A.B]

    def test_type_error_array_expected(self):
        """Test TypeError when array expected but got something else."""
        pdf = pikepdf.new()
        pdf.Root.A = Dictionary()  # Not an array
        with pytest.raises(TypeError, match="Expected Array"):
            pdf.Root[NamePath.A[0]]

    def test_index_out_of_range(self):
        """Test IndexError when array index is out of range."""
        pdf = pikepdf.new()
        pdf.Root.Items = Array([1, 2, 3])
        with pytest.raises(IndexError, match="out of range"):
            pdf.Root[NamePath.Items[10]]

    def test_set_missing_parent_error(self):
        """Test error when trying to set value in non-existent parent."""
        pdf = pikepdf.new()
        # /Info doesn't exist, so we can't set /Info/Title
        with pytest.raises(KeyError):
            pdf.Root[NamePath.Info.Title] = String("Test")


class TestNamePathRepr:
    """Test __repr__ formatting."""

    def test_repr_name_only(self):
        """Test repr with only name components."""
        path = NamePath.A.B.C
        assert repr(path) == "NamePath.A.B.C"

    def test_repr_with_indices(self):
        """Test repr with mixed names and indices."""
        path = NamePath.A[0].B[1].C
        assert repr(path) == "NamePath.A[0].B[1].C"

    def test_repr_empty(self):
        """Test repr of empty path."""
        path = NamePath()
        assert repr(path) == "NamePath"

    def test_repr_index_only(self):
        """Test repr starting with index (unusual but valid)."""
        path = NamePath()[0]
        assert repr(path) == "NamePath[0]"


class TestNamePathEdgeCases:
    """Test edge cases and unusual usage patterns."""

    def test_class_itself_not_usable_as_path(self):
        """Test that NamePath class itself can't be used as a path.

        obj[NamePath] should fail because NamePath is a class, not an instance.
        """
        pdf = pikepdf.new()
        # The metaclass doesn't make the class itself indexable as a path
        # This should raise an error (nanobind won't recognize the class)
        with pytest.raises(TypeError):
            pdf.Root[NamePath]  # noqa: B018 (pointless expression)

    def test_deeply_nested(self):
        """Test very deep nesting works correctly."""
        pdf = pikepdf.new()
        pdf.Root.A = Dictionary(
            B=Dictionary(C=Dictionary(D=Dictionary(E=Dictionary(F=42))))
        )
        result = pdf.Root[NamePath.A.B.C.D.E.F]
        assert int(result) == 42

    def test_name_with_slash_prefix_handled(self):
        """Test that names with / prefix work in canonical form."""
        path1 = NamePath('/Resources')
        path2 = NamePath.Resources
        assert repr(path1) == repr(path2)

    def test_name_without_slash_auto_prefixed(self):
        """Test that names without / are auto-prefixed."""
        # In canonical form, strings are expected to start with /
        # but we handle both for convenience
        path = NamePath('Resources')  # No leading /
        assert repr(path) == "NamePath.Resources"

    def test_constructor_with_int(self):
        """Test NamePath(0) constructor with int argument (line 73 of namepath.cpp)."""
        path = NamePath(0)
        assert repr(path) == "NamePath[0]"
        assert len(path) == 1

    def test_call_with_int(self):
        """Test path(0) call syntax with int (line 104 of namepath.cpp)."""
        path = NamePath.Items(0)
        assert repr(path) == "NamePath.Items[0]"
        assert len(path) == 2

    def test_call_with_name_object(self):
        """Test path(Name.X) call syntax with Name (lines 109-110 of namepath.cpp)."""
        path = NamePath.Resources(Name.Font)
        assert repr(path) == "NamePath.Resources.Font"
        assert len(path) == 2

    def test_constructor_with_mixed_args(self):
        """Test NamePath('/A', 0, Name.B) with mixed argument types."""
        path = NamePath('/Resources', 0, Name.Font)
        assert repr(path) == "NamePath.Resources[0].Font"
        assert len(path) == 3


class TestNamePathContains:
    """Test `path in obj` membership testing."""

    def test_contains_nested_key(self):
        pdf = pikepdf.new()
        pdf.Root.A = Dictionary(B=Dictionary(C=42))
        assert NamePath.A.B.C in pdf.Root
        assert NamePath.A.B in pdf.Root

    def test_contains_missing_key(self):
        pdf = pikepdf.new()
        pdf.Root.A = Dictionary(B=Dictionary(C=42))
        assert NamePath.A.B.D not in pdf.Root
        assert NamePath.Nonexistent not in pdf.Root

    def test_contains_wrong_intermediate_type(self):
        pdf = pikepdf.new()
        pdf.Root.A = Dictionary(B=42)
        assert NamePath.A.B.C not in pdf.Root

    def test_contains_index(self):
        pdf = pikepdf.new()
        pdf.Root.A = Array([1, 2, 3])
        assert NamePath.A[0] in pdf.Root
        assert NamePath.A[2] in pdf.Root
        assert NamePath.A[-1] in pdf.Root
        assert NamePath.A[3] not in pdf.Root

    def test_contains_index_on_dict(self):
        pdf = pikepdf.new()
        pdf.Root.A = Dictionary(B=42)
        assert NamePath.A[0] not in pdf.Root

    def test_contains_empty_path(self):
        pdf = pikepdf.new()
        assert NamePath() in pdf.Root

    def test_contains_on_array_root(self):
        arr = Array([Dictionary(A=1)])
        assert NamePath[0].A in arr
        assert NamePath[0].B not in arr


class TestNamePathDelete:
    """Test `del obj[path]`."""

    def test_del_nested_key(self):
        pdf = pikepdf.new()
        pdf.Root.A = Dictionary(B=Dictionary(C=42, D=43))
        del pdf.Root[NamePath.A.B.C]
        assert Name.C not in pdf.Root.A.B
        assert Name.D in pdf.Root.A.B

    def test_del_top_level_key(self):
        pdf = pikepdf.new()
        pdf.Root.A = Dictionary(B=1)
        del pdf.Root[NamePath.A]
        assert Name.A not in pdf.Root

    def test_del_array_index(self):
        pdf = pikepdf.new()
        pdf.Root.A = Array([1, 2, 3])
        del pdf.Root[NamePath.A[1]]
        assert [int(x) for x in pdf.Root.A] == [1, 3]

    def test_del_array_negative_index(self):
        pdf = pikepdf.new()
        pdf.Root.A = Array([1, 2, 3])
        del pdf.Root[NamePath.A[-1]]
        assert [int(x) for x in pdf.Root.A] == [1, 2]

    def test_del_missing_key_raises_keyerror(self):
        pdf = pikepdf.new()
        pdf.Root.A = Dictionary(B=Dictionary(C=42))
        with pytest.raises(KeyError):
            del pdf.Root[NamePath.A.B.Missing]

    def test_del_missing_intermediate_raises_keyerror(self):
        pdf = pikepdf.new()
        pdf.Root.A = Dictionary(B=Dictionary(C=42))
        with pytest.raises(KeyError):
            del pdf.Root[NamePath.A.Nope.C]

    def test_del_index_out_of_range_raises_indexerror(self):
        pdf = pikepdf.new()
        pdf.Root.A = Array([1, 2, 3])
        with pytest.raises(IndexError):
            del pdf.Root[NamePath.A[10]]

    def test_del_index_on_dict_raises_typeerror(self):
        pdf = pikepdf.new()
        pdf.Root.A = Dictionary(B=42)
        with pytest.raises(TypeError):
            del pdf.Root[NamePath.A[0]]

    def test_del_key_on_array_raises(self):
        pdf = pikepdf.new()
        pdf.Root.A = Array([1, 2, 3])
        with pytest.raises((TypeError, ValueError)):
            del pdf.Root[NamePath.A.B]

    def test_del_empty_path_raises_valueerror(self):
        pdf = pikepdf.new()
        with pytest.raises(ValueError, match="empty NamePath"):
            del pdf.Root[NamePath()]


class TestNamePathIteration:
    """Test iteration over path components."""

    def test_iter_components(self):
        assert list(NamePath.A.B[0]) == ['/A', '/B', 0]

    def test_iter_empty(self):
        assert tuple(NamePath()) == ()

    def test_iter_names_have_slash(self):
        assert list(NamePath('/Weird-Name')) == ['/Weird-Name']

    def test_unpack(self):
        a, b = NamePath.A[3]
        assert a == '/A'
        assert b == 3

    def test_in_list_of_paths(self):
        p1 = NamePath.A.B
        p2 = NamePath.C
        assert NamePath.A.B in [p1, p2]
        assert NamePath.D not in [p1, p2]


class TestNamePathEquality:
    """Test __eq__ and __hash__."""

    def test_equal_paths(self):
        assert NamePath.A.B == NamePath.A.B
        assert NamePath('/A', '/B') == NamePath.A.B

    def test_unequal_paths(self):
        assert NamePath.A.B != NamePath.A.C
        assert NamePath.A != NamePath.A.B
        assert NamePath() != NamePath.A

    def test_empty_equal(self):
        assert NamePath() == NamePath()

    def test_str_component_not_equal_int_component(self):
        assert NamePath('/1') != NamePath[1]

    def test_not_equal_other_type(self):
        assert NamePath.A != '/A'
        assert NamePath.A != 1
        assert not (NamePath.A == '/A')

    def test_hash_equal(self):
        assert hash(NamePath.A.B) == hash(NamePath('/A', '/B'))
        assert hash(NamePath()) == hash(NamePath())

    def test_hash_distinguishes_str_and_int(self):
        assert hash(NamePath('/1')) != hash(NamePath[1])

    def test_set_membership(self):
        s = {NamePath.A.B, NamePath.C}
        assert NamePath.A.B in s
        assert NamePath.D not in s
        assert len({NamePath.A, NamePath.A}) == 1

    def test_dict_key(self):
        d = {NamePath.A.B: 'value'}
        assert d[NamePath('/A', '/B')] == 'value'


class TestNamePathIsinstance:
    """Test isinstance/issubclass against the NamePath facade."""

    def test_isinstance_constructed(self):
        assert isinstance(NamePath('/A'), pikepdf.NamePath)

    def test_isinstance_shorthand(self):
        assert isinstance(NamePath.A.B, pikepdf.NamePath)

    def test_isinstance_empty(self):
        assert isinstance(NamePath(), pikepdf.NamePath)

    def test_isinstance_other(self):
        assert not isinstance('/A', pikepdf.NamePath)
        assert not isinstance(Name.A, pikepdf.NamePath)
        assert not isinstance(None, pikepdf.NamePath)

    def test_issubclass(self):
        assert issubclass(pikepdf._core._NamePath, pikepdf.NamePath)
        assert issubclass(type(NamePath.A), pikepdf.NamePath)
        assert issubclass(pikepdf.NamePath, pikepdf.NamePath)

    def test_not_issubclass(self):
        assert not issubclass(str, pikepdf.NamePath)
