# SPDX-FileCopyrightText: 2026 James R. Barlow
# SPDX-License-Identifier: CC0-1.0

"""Walking object graphs that share or repeat objects.

A PDF's objects form a graph, not a tree: objects are shared, and they may
refer back to their ancestors. A walk that only limits its depth visits a
shared object once for each path to it, which is exponential in the worst
case. These tests use graphs small enough to build instantly but with far too
many paths to enumerate.
"""

from __future__ import annotations

from io import BytesIO

import pytest

import pikepdf
from pikepdf import Array, Dictionary, Name, ObjectSet, Pdf, String

# A walk that enumerates paths does not finish, so fail instead of hanging.
# The thread method is needed to interrupt a loop in C++.
pytestmark = pytest.mark.timeout(60, method='thread')


def _reopen(pdf: Pdf) -> Pdf:
    bio = BytesIO()
    pdf.save(bio)
    bio.seek(0)
    return Pdf.open(bio)


def _diamonds(pdf: Pdf, levels: int = 60) -> Dictionary:
    """Return a chain of dictionaries that each refer twice to the next.

    There are 2**levels paths from the returned object to the leaf.
    """
    node = pdf.make_indirect(Dictionary(Leaf=1))
    for _ in range(levels):
        node = pdf.make_indirect(Dictionary(L=node, R=node))
    return node


class TestEquality:
    def test_shared_children_in_two_documents(self):
        pdf = pikepdf.new()
        pdf.Root.Diamond = _diamonds(pdf)
        a = _reopen(pdf)
        b = _reopen(pdf)
        assert a.Root.Diamond == b.Root.Diamond

    def test_shared_children_in_one_document(self):
        pdf = pikepdf.new()
        a = _diamonds(pdf)
        b = _diamonds(pdf)
        assert a == b

    def test_shared_children_unequal(self):
        pdf = pikepdf.new()
        a = _diamonds(pdf)
        b = _diamonds(pdf)
        # Change the leaf of one graph only
        node = b
        while Name.L in node:
            node = node.L
        node.Leaf = 2
        assert a != b

    def test_shared_direct_children(self):
        def nested() -> Array:
            value = Array([1])
            for _ in range(60):
                value = Array([value, value])
            return value

        assert nested() == nested()

    def test_cycle_through_shared_children(self):
        def build(pdf: Pdf) -> Dictionary:
            top = _diamonds(pdf, 30)
            node = top
            while Name.L in node:
                node = node.L
            node.Top = top
            return top

        pdf = pikepdf.new()
        assert build(pdf) == build(pdf)


class TestObjectSet:
    def test_add_reports_first_visit(self):
        pdf = pikepdf.new()
        obj = pdf.make_indirect(Dictionary(A=1))
        seen = ObjectSet()
        assert seen.add(obj) is True
        assert seen.add(obj) is False
        assert len(seen) == 1

    def test_contains(self):
        pdf = pikepdf.new()
        obj = pdf.make_indirect(Dictionary(A=1))
        other = pdf.make_indirect(Dictionary(A=1))
        seen = ObjectSet()
        assert obj not in seen
        seen.add(obj)
        assert obj in seen
        assert other not in seen  # equal, but a different object

    def test_same_object_through_different_references(self):
        pdf = pikepdf.new()
        obj = pdf.make_indirect(Dictionary(A=1))
        pdf.Root.One = obj
        pdf.Root.Two = obj
        seen = ObjectSet()
        assert seen.add(pdf.Root.One)
        assert not seen.add(pdf.Root.Two)
        assert not seen.add(pdf.get_object(obj.objgen))

    def test_same_objgen_in_different_documents(self):
        pdf = pikepdf.new()
        pdf.Root.Thing = pdf.make_indirect(Dictionary(A=1))
        a = _reopen(pdf)
        b = _reopen(pdf)
        assert a.Root.Thing.objgen == b.Root.Thing.objgen
        seen = ObjectSet()
        assert seen.add(a.Root.Thing)
        assert seen.add(b.Root.Thing)
        assert len(seen) == 2

    def test_direct_objects_tracked_by_identity(self):
        pdf = pikepdf.new()
        pdf.Root.One = Dictionary(A=1)
        pdf.Root.Two = Dictionary(A=1)
        seen = ObjectSet()
        assert seen.add(pdf.Root.One)
        assert not seen.add(pdf.Root.One)
        assert seen.add(pdf.Root.Two)

    def test_initial_objects(self):
        pdf = pikepdf.new()
        a = pdf.make_indirect(Dictionary())
        b = pdf.make_indirect(Dictionary())
        seen = ObjectSet([a, b, a])
        assert len(seen) == 2
        assert a in seen and b in seen

    def test_pages_and_helpers(self):
        pdf = pikepdf.new()
        pdf.add_blank_page()
        page = pdf.pages[0]
        seen = ObjectSet()
        assert seen.add(page)
        assert not seen.add(page.obj)
        assert page in seen

    def test_discard_and_clear(self):
        pdf = pikepdf.new()
        a = pdf.make_indirect(Dictionary())
        seen = ObjectSet([a])
        seen.discard(a)
        seen.discard(a)  # absent: no error
        assert a not in seen
        seen.add(a)
        seen.clear()
        assert len(seen) == 0
        assert not seen

    def test_rejects_other_types_among_initial_objects(self):
        pdf = pikepdf.new()
        with pytest.raises(TypeError):
            ObjectSet([pdf.Root, 42])

    def test_rejects_other_types(self):
        seen = ObjectSet()
        with pytest.raises(TypeError):
            seen.add(42)
        with pytest.raises(TypeError):
            seen.add('/Name')
        assert 42 not in seen

    def test_repr(self):
        assert repr(ObjectSet()) == '<pikepdf.ObjectSet of 0 objects>'

    def test_not_hashable(self):
        with pytest.raises(TypeError):
            hash(ObjectSet())

    def test_walk_cyclic_graph(self):
        # The pattern the class exists for
        pdf = pikepdf.new()
        top = _diamonds(pdf, 40)
        node = top
        while Name.L in node:
            node = node.L
        node.Top = top

        seen = ObjectSet()
        pending = [top]
        while pending:
            node = pending.pop()
            if not isinstance(node, Dictionary) or not seen.add(node):
                continue
            pending.extend(node.values())
        assert len(seen) == 41


def _action(pdf: Pdf, **kwargs) -> Dictionary:
    return pdf.make_indirect(
        Dictionary(Type=Name.Action, S=Name.GoTo, D=String('dest'), **kwargs)
    )


def _page_with_action(pdf: Pdf, action: Dictionary) -> None:
    pdf.add_blank_page()
    annot = pdf.make_indirect(
        Dictionary(Type=Name.Annot, Subtype=Name.Link, Rect=[0, 0, 1, 1], A=action)
    )
    pdf.pages[0].obj.Annots = Array([annot])


class TestActionChains:
    def test_add_pages_from_shared_next_actions(self):
        src = pikepdf.new()
        action = _action(src)
        for _ in range(45):
            action = _action(src, Next=Array([action, action]))
        _page_with_action(src, action)

        dst = pikepdf.new()
        result = dst.add_pages_from(src)
        assert result.pages_added == 1

    def test_add_pages_from_cyclic_next_actions(self):
        src = pikepdf.new()
        last = _action(src)
        action = last
        for _ in range(3):
            action = _action(src, Next=Array([action, action]))
        last.Next = action
        _page_with_action(src, action)

        dst = pikepdf.new()
        result = dst.add_pages_from(src)
        assert result.pages_added == 1

    def test_add_pages_from_migrates_dest_in_next_chain(self):
        src = pikepdf.new()
        src.add_blank_page()
        tail = src.make_indirect(
            Dictionary(Type=Name.Action, S=Name.GoTo, D=String('tail'))
        )
        head = src.make_indirect(
            Dictionary(Type=Name.Action, S=Name.GoTo, D=String('head'), Next=tail)
        )
        annot = src.make_indirect(
            Dictionary(Type=Name.Annot, Subtype=Name.Link, Rect=[0, 0, 1, 1], A=head)
        )
        src.pages[0].obj.Annots = Array([annot])
        tree = pikepdf.NameTree.new(src)
        for name in ('head', 'tail'):
            tree[name] = Array([src.pages[0].obj, Name.Fit])
        src.Root.Names = Dictionary(Dests=tree.obj)

        dst = pikepdf.new()
        result = dst.add_pages_from(src)
        assert result.named_dests_added == 2


class TestOutlines:
    def test_direct_outline_items_are_all_read(self):
        # Direct objects all report objgen (0, 0), so a visited set of objgens
        # mistakes the second direct item for a repeat of the first.
        pdf = pikepdf.new()
        pdf.add_blank_page()
        c = Dictionary(Title='c')
        b = Dictionary(Title='b', Next=c)
        a = Dictionary(Title='a', Next=b)
        pdf.Root.Outlines = pdf.make_indirect(
            Dictionary(Type=Name.Outlines, First=a, Last=c, Count=3)
        )
        with pdf.open_outline() as outline:
            assert [item.title for item in outline.root] == ['a', 'b', 'c']
        # Saving links each item to its siblings, which direct objects cannot do
        reopened = _reopen(pdf)
        first = reopened.Root.Outlines.First
        assert first.is_indirect
        assert [
            str(first.Title),
            str(first.Next.Title),
            str(first.Next.Next.Title),
        ] == [
            'a',
            'b',
            'c',
        ]
        assert first.Next.Prev.objgen == first.objgen

    def test_cyclic_siblings(self):
        pdf = pikepdf.new()
        pdf.add_blank_page()
        a = pdf.make_indirect(Dictionary(Title='a'))
        b = pdf.make_indirect(Dictionary(Title='b', Next=a))
        a.Next = b
        pdf.Root.Outlines = pdf.make_indirect(
            Dictionary(Type=Name.Outlines, First=a, Last=b, Count=2)
        )
        with pdf.open_outline() as outline:
            assert [item.title for item in outline.root] == ['a', 'b']

    def test_strict_reports_malformed_links(self):
        pdf = pikepdf.new()
        pdf.add_blank_page()
        a = pdf.make_indirect(Dictionary(Title='a', Next=Array([1])))
        pdf.Root.Outlines = pdf.make_indirect(
            Dictionary(Type=Name.Outlines, First=a, Last=a, Count=1)
        )
        with pytest.raises(pikepdf.OutlineStructureError, match='non-dictionary'):
            with pdf.open_outline(strict=True) as outline:
                list(outline.root)

        b = pdf.make_indirect(Dictionary(Title='b'))
        a.Next = b
        b.Next = a
        with pytest.raises(pikepdf.OutlineStructureError, match='reoccurred'):
            with pdf.open_outline(strict=True) as outline:
                list(outline.root)


class TestInternalWalks:
    def test_reachable_objects(self):
        pdf = pikepdf.new()
        top = _diamonds(pdf, 40)
        node = top
        while Name.L in node:
            node = node.L
        node.Top = top  # a cycle
        node.Number = pdf.make_indirect(42)
        node.Text = pdf.make_indirect(String('text'))
        node.Inline = Dictionary(Deeper=pdf.make_indirect(Array([1, 2])))

        found = pikepdf._core._reachable_objects(pdf, [top, top])
        assert all(obj.is_indirect for obj in found)
        # 41 dictionaries, the string and the array, but not the integer
        assert len(found) == 43
        assert found[0].objgen == top.objgen
        assert len({obj.objgen for obj in found}) == len(found)

    def test_action_chain_order(self):
        pdf = pikepdf.new()
        c = Dictionary(S=Name.GoTo, D=String('c'))
        b = pdf.make_indirect(Dictionary(S=Name.GoTo, D=String('b'), Next=c))
        d = pdf.make_indirect(Dictionary(S=Name.GoTo, D=String('d')))
        a = pdf.make_indirect(
            Dictionary(S=Name.GoTo, D=String('a'), Next=Array([b, 42, d, b]))
        )
        d.Next = a
        chain = pikepdf._core._action_chain(a)
        assert [str(action.D) for action in chain] == ['a', 'b', 'c', 'd']

    def test_inherited_page_attribute(self):
        pdf = pikepdf.new()
        pdf.add_blank_page()
        page = pdf.pages[0]
        pdf.Root.Pages.Resources = Dictionary(Marker=Name.Yes)
        del page.obj.Resources
        assert page._get_inherited('/Resources').Marker == Name.Yes
        assert page._get_inherited('/Rotate') is None
        # A page tree whose root is its own parent
        pdf.Root.Pages.Parent = pdf.Root.Pages
        assert page._get_inherited('/Rotate') is None


class TestSameObject:
    def test_references_to_one_indirect_object(self):
        pdf = pikepdf.new()
        obj = pdf.make_indirect(Dictionary(A=1))
        pdf.Root.One = obj
        pdf.Root.Two = obj
        assert pdf.Root.One.is_same_object_as(pdf.Root.Two)
        assert pdf.Root.One.is_same_object_as(pdf.get_object(obj.objgen))

    def test_equal_objects_are_not_the_same(self):
        pdf = pikepdf.new()
        a = pdf.make_indirect(Dictionary(A=1))
        b = pdf.make_indirect(Dictionary(A=1))
        assert a == b
        assert not a.is_same_object_as(b)

    def test_direct_objects(self):
        pdf = pikepdf.new()
        pdf.Root.One = Dictionary(A=1)
        pdf.Root.Two = Dictionary(A=1)
        assert pdf.Root.One.objgen == pdf.Root.Two.objgen == (0, 0)
        assert pdf.Root.One.is_same_object_as(pdf.Root.One)
        assert not pdf.Root.One.is_same_object_as(pdf.Root.Two)

    def test_same_objgen_in_different_documents(self):
        pdf = pikepdf.new()
        pdf.Root.Thing = pdf.make_indirect(Dictionary(A=1))
        a = _reopen(pdf)
        b = _reopen(pdf)
        assert a.Root.Thing.objgen == b.Root.Thing.objgen
        assert not a.Root.Thing.is_same_object_as(b.Root.Thing)

    def test_helpers(self):
        pdf = pikepdf.new()
        pdf.add_blank_page()
        page = pdf.pages[0]
        assert page.obj.is_same_object_as(page)
        assert page.obj.is_same_object_as(pdf.pages[0])

    def test_other_types_are_never_the_same(self):
        pdf = pikepdf.new()
        assert not pdf.Root.is_same_object_as(42)
        assert not pdf.Root.is_same_object_as(None)
        assert not pdf.Root.is_same_object_as({'/Type': Name.Catalog})

    def test_object_passed_to_replace_object(self):
        pdf = pikepdf.new()
        old = pdf.make_indirect(Dictionary(A=1))
        pdf.Root.Thing = old
        new = Dictionary(B=2)
        pdf._replace_object(old.objgen, new)
        assert pdf.Root.Thing.B == 2
        assert old.is_same_object_as(pdf.Root.Thing)
        assert new.is_same_object_as(pdf.Root.Thing)
        assert new in ObjectSet([pdf.Root.Thing])

    def test_swapped_objects_keep_their_numbers(self):
        pdf = pikepdf.new()
        a = pdf.make_indirect(Dictionary(Is=Name.A))
        b = pdf.make_indirect(Dictionary(Is=Name.B))
        pdf.Root.A = a
        pdf._swap_objects(a.objgen, b.objgen)
        assert a.Is == Name.B
        assert a.is_same_object_as(pdf.Root.A)
        assert not a.is_same_object_as(b)

    def test_shallow_copy_is_a_different_object(self):
        import copy

        pdf = pikepdf.new()
        original = pdf.make_indirect(Dictionary(A=1))
        assert not original.is_same_object_as(copy.copy(original))
