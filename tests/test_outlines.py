# SPDX-FileCopyrightText: 2022 James R. Barlow
# SPDX-License-Identifier: CC0-1.0

from __future__ import annotations

from itertools import repeat

import pytest
from hypothesis import example, given, settings
from hypothesis import strategies as st

from pikepdf import (
    Array,
    Destination,
    Dictionary,
    Name,
    NameTree,
    OutlineItem,
    OutlineItemFlag,
    OutlineStructureError,
    PageLocation,
    Pdf,
    String,
    make_page_destination,
)
from pikepdf.models.actions import GoToAction
from pikepdf.models.outlines import ALL_PAGE_LOCATION_KWARGS, PAGE_LOCATION_ARGS

# pylint: disable=redefined-outer-name


@pytest.fixture
def outlines_doc(resources):
    # Contains an outline with references
    with Pdf.open(resources / 'outlines.pdf') as pdf:
        yield pdf


def test_load_outlines(outlines_doc):
    root_obj = outlines_doc.Root.Outlines
    first_obj = root_obj.First
    second_obj = first_obj.Next
    third_obj = second_obj.Next

    with outlines_doc.open_outline() as outline:
        sec_one = outline.root[0]
        sec_two = outline.root[1]
        sec_three = outline.root[2]
        assert len(outline.root) == 3
    assert sec_one.title == 'One'
    assert sec_one.is_closed is True
    assert sec_one.obj == first_obj
    assert sec_two.title == 'Two'
    assert sec_two.is_closed is False
    assert sec_two.obj == second_obj
    assert sec_three.title == 'Three'
    assert sec_three.is_closed is True
    assert sec_three.obj == third_obj


def test_reproduce_outlines_structure(outlines_doc):
    root_obj = outlines_doc.Root.Outlines
    first_obj = root_obj.First
    first_obj_a = first_obj.First
    first_obj_b = first_obj_a.Next
    first_obj_b_i = first_obj_b.First
    first_obj_b_ii = first_obj_b_i.Next
    second_obj = first_obj.Next
    third_obj = second_obj.Next
    third_obj_a = third_obj.First
    third_obj_b = third_obj_a.Next

    with outlines_doc.open_outline() as outline:
        # Ensure outline is loaded
        list(outline.root)
        # Remove all references
        for obj in [
            root_obj,
            first_obj,
            first_obj_a,
            first_obj_b,
            first_obj_b_i,
            first_obj_b_ii,
            second_obj,
            third_obj,
            third_obj_a,
            third_obj_b,
        ]:
            for n in ['/First', '/Last', '/Prev', '/Next', '/Parent']:
                if n in obj:
                    del obj[n]

    # References should just be reproduced. Exhaustive check:
    for ref in [first_obj.Parent, second_obj.Parent, third_obj.Parent]:
        assert ref == root_obj
    for ref in [
        root_obj.First,
        second_obj.Prev,
        first_obj_a.Parent,
        first_obj_b.Parent,
    ]:
        assert ref == first_obj
    assert first_obj.First == first_obj_a
    assert first_obj_b.Prev == first_obj_a
    for ref in [
        first_obj.Last,
        first_obj_a.Next,
        first_obj_b_i.Parent,
        first_obj_b_ii.Parent,
    ]:
        assert ref == first_obj_b
    assert first_obj_b.First == first_obj_b_i
    assert first_obj_b_ii.Prev == first_obj_b_i
    assert first_obj_b.Last == first_obj_b_ii
    assert first_obj_b_i.Next == first_obj_b_ii
    assert first_obj.Next == second_obj
    for ref in [root_obj.Last, second_obj.Next, third_obj_a.Parent, third_obj_b.Parent]:
        assert ref == third_obj
    assert third_obj.First == third_obj_a
    assert third_obj_b.Prev == third_obj_a
    assert third_obj.Last == third_obj_b
    assert third_obj_a.Next == third_obj_b


def test_recursion_depth_zero(outlines_doc):
    # Only keeps root level
    with outlines_doc.open_outline(max_depth=0) as outline:
        # No more than the root level should be read
        for root_element in outline.root:
            assert len(root_element.children) == 0

        # Attach an item to the first root level element
        # that should be ignored when writing
        outline.root[0].children.append(OutlineItem('New', 0))

    root_obj = outlines_doc.Root.Outlines
    first_obj = root_obj.First
    second_obj = first_obj.Next
    third_obj = second_obj.Next
    for obj in [first_obj, second_obj, third_obj]:
        assert '/First' not in obj
        assert '/Last' not in obj


def test_recursion_depth_one(outlines_doc):
    # Only keeps first level from root
    with outlines_doc.open_outline(max_depth=1) as outline:
        # Only children of first level should be present
        for root_element, first_level_count in zip(outline.root, (2, 0, 2)):
            assert len(root_element.children) == first_level_count
            for sub_element in root_element.children:
                assert len(sub_element.children) == 0

        # Attach an item to the first sub level element
        # that should be ignored when writing
        outline.root[0].children[1].children.append(OutlineItem('New', 0))

    root_obj = outlines_doc.Root.Outlines
    first_obj = root_obj.First
    first_obj_a = first_obj.First
    first_obj_b = first_obj_a.Next
    second_obj = first_obj.Next
    third_obj = second_obj.Next
    third_obj_a = third_obj.First
    third_obj_b = third_obj_a.Next
    for obj in [first_obj_a, first_obj_b, third_obj_a, third_obj_b]:
        assert '/First' not in obj
        assert '/Last' not in obj


def test_reference_loop_on_level(outlines_doc):
    root_obj = outlines_doc.Root.Outlines
    first_obj = root_obj.First
    last_obj = root_obj.Last

    # Intentionally create a reference back to the first element:
    last_obj.Next = first_obj

    # Fails on reoccurring element
    with pytest.raises(OutlineStructureError):
        with outlines_doc.open_outline(strict=True) as outline:
            # Ensure outline is loaded
            list(outline.root)

    # Silently ignores invalid parts and fixes structure
    with outlines_doc.open_outline() as outline:
        list(outline.root)
    # Back-reference should now be removed
    assert '/Next' not in last_obj


def test_reference_loop_on_recursion_only_element(outlines_doc):
    root_obj = outlines_doc.Root.Outlines
    first_obj = root_obj.First
    first_obj_a = first_obj.First

    # Re-cycle a reference from the root level
    # and place it as the only sub-element
    first_obj_a.First = first_obj
    first_obj_a.Last = first_obj

    # Fails on reoccurring element
    with pytest.raises(OutlineStructureError):
        with outlines_doc.open_outline(strict=True) as outline:
            # Ensure outline is loaded
            list(outline.root)

    # Silently ignores invalid parts and fixes structure
    with outlines_doc.open_outline() as outline:
        list(outline.root)
    # Invalid structure should now be absent
    assert '/First' not in first_obj_a
    assert '/Last' not in first_obj_a


def test_reference_loop_on_recursion_last_element(outlines_doc):
    root_obj = outlines_doc.Root.Outlines
    first_obj = root_obj.First
    first_obj_a = first_obj.First
    first_obj_b = first_obj_a.Next
    first_obj_b_i = first_obj_b.First
    first_obj_b_ii = first_obj_b_i.Next

    # Re-cycle a reference from the root level
    # and attach it to a list of other elements
    first_obj_b_ii.Next = first_obj
    first_obj_b.Last = first_obj

    # Fails on reoccurring element
    with pytest.raises(OutlineStructureError):
        with outlines_doc.open_outline(strict=True) as outline:
            # Ensure outline is loaded
            list(outline.root)

    # Silently ignores invalid parts and fixes structure
    with outlines_doc.open_outline() as outline:
        list(outline.root)
    # Invalid references should now be removed
    assert '/Next' not in first_obj_b_ii
    assert first_obj_b.Last == first_obj_b_ii


def test_duplicated_object(outlines_doc):
    # Fails on reoccurring element
    with pytest.raises(OutlineStructureError):
        with outlines_doc.open_outline(strict=True) as outline:
            # Copy and object reference from one node to another
            obj_b_ii = outline.root[0].children[1].children[0].obj
            outline.root[2].children[0].obj = obj_b_ii

    # Silently creates a copy of the outline node
    with outlines_doc.open_outline() as outline:
        # Append duplicate object reference to existing outline
        obj_b_ii = outline.root[0].children[1].children[0].obj
        outline.root[2].children.append(OutlineItem.from_dictionary_object(obj_b_ii))

    # Should not fail at this point anymore
    with outlines_doc.open_outline(strict=True) as outline:
        assert len(outline.root[2].children) == 3
        assert (
            outline.root[2].children[2].title
            == outline.root[0].children[1].children[0].title
        )


def test_fix_references_swap_root(outlines_doc):
    root_obj = outlines_doc.Root.Outlines
    first_obj = root_obj.First
    second_obj = first_obj.Next
    third_obj = second_obj.Next

    # Swap first and last item
    with outlines_doc.open_outline() as outline:
        first_item = outline.root.pop(0)
        last_item = outline.root.pop()
        outline.root.insert(0, last_item)
        outline.root.append(first_item)

    assert root_obj.First == third_obj
    assert root_obj.Last == first_obj
    assert third_obj.Next == second_obj
    assert second_obj.Next == first_obj
    assert first_obj.Prev == second_obj
    assert second_obj.Prev == third_obj
    assert '/Prev' not in third_obj
    assert '/Next' not in first_obj


def test_fix_references_move_level(outlines_doc):
    root_obj = outlines_doc.Root.Outlines
    first_obj = root_obj.First
    first_b_obj = first_obj.Last
    third_obj = root_obj.Last

    with outlines_doc.open_outline() as outline:
        second_level = outline.root[0].children[1].children  # One B (I and II)
        sec_one_b_i, sec_one_b_ii = second_level
        # Move second level items to root
        outline.root.extend(second_level)
        second_level.clear()

    assert third_obj.Next == sec_one_b_i.obj
    assert sec_one_b_i.obj.Next == sec_one_b_ii.obj
    assert sec_one_b_i.obj.Prev == third_obj
    assert root_obj.Last == sec_one_b_ii.obj
    assert sec_one_b_i.obj.Parent == root_obj
    assert sec_one_b_ii.obj.Parent == root_obj
    assert first_b_obj.Count == 0
    assert '/First' not in first_b_obj
    assert '/Last' not in first_b_obj


def test_noop(outlines_doc):
    with outlines_doc.open_outline(strict=True):
        # Forget to attach it - should simply not modify.
        OutlineItem('New')


def test_empty_outline_omits_count_on_never_populated_pdf():
    pdf = Pdf.new()
    pdf.add_blank_page()
    with pdf.open_outline() as outline:
        # Force a load; never add anything.
        list(outline.root)
    assert Name.Count not in pdf.Root.Outlines


def test_clearing_all_items_removes_count(outlines_doc):
    with outlines_doc.open_outline() as outline:
        outline.root.clear()
    assert Name.Count not in outlines_doc.Root.Outlines


def test_append_items(outlines_doc):
    # Simple check that we can write new objects
    # without failing the object duplicate checks
    with outlines_doc.open_outline(strict=True) as outline:
        new_item = OutlineItem('Four')
        new_item.children.extend([OutlineItem('Four-A'), OutlineItem('Four-B')])
        outline.root.append(new_item)

    with outlines_doc.open_outline(strict=True):
        list(outline.root)


def test_create_from_scratch(outlines_doc):
    # Simple check that we can discard the existing outline
    # and create a new one.
    del outlines_doc.Root.Outlines
    with outlines_doc.open_outline(strict=True) as outline:
        new_item = OutlineItem('One')
        new_item.children.extend([OutlineItem('One-A'), OutlineItem('One-B')])
        outline.root.append(new_item)

    with outlines_doc.open_outline(strict=True):
        list(outline.root)

    # Should also work while the outline is open
    with outlines_doc.open_outline(strict=True) as outline:
        del outlines_doc.Root.Outlines
        new_item = OutlineItem('One')
        outline.root.append(new_item)

    with outlines_doc.open_outline(strict=True):
        list(outline.root)


def test_modify_closed(outlines_doc):
    root_obj = outlines_doc.Root.Outlines
    first_obj = root_obj.First
    second_obj = first_obj.Next
    third_obj = second_obj.Next
    # Initial state
    assert root_obj.Count == 3
    assert first_obj.Count == -2
    assert third_obj.Count == -2
    with outlines_doc.open_outline() as outline:
        # Opens first level
        for i in outline.root:
            i.is_closed = False
    assert root_obj.Count == 7
    assert first_obj.Count == 2
    assert third_obj.Count == 2
    # Opens second level (only present in first section)
    with outlines_doc.open_outline() as outline:
        for i in outline.root[0].children:
            i.is_closed = False
    assert root_obj.Count == 9
    assert first_obj.Count == 4


def test_dest_or_action(outlines_doc):
    first_obj = outlines_doc.Root.Outlines.First
    first_page = outlines_doc.pages[0]
    assert '/A' in first_obj
    assert '/Dest' not in first_obj
    with outlines_doc.open_outline() as outline:
        first = outline.root[0]
        # Set to first page.
        first.destination = 0
    # Reference should be replaced at this point.
    assert first.destination == [first_page.obj, Name.Fit]
    assert first_obj.Dest == first.destination
    # Original action should be gone
    assert '/A' not in first_obj
    # Now save with a new action instead
    with outlines_doc.open_outline() as outline:
        first = outline.root[0]
        first.action = Dictionary(D=first.destination, S=Name.GoTo)
        first.destination = None
    assert first_obj.A.D == [first_page.obj, Name.Fit]
    assert '/Dest' not in first_obj


def test_outline_item_parsed_action_wraps_raw_dictionary(outlines_doc):
    with outlines_doc.open_outline() as outline:
        first = outline.root[0]
        first.action = Dictionary(
            S=Name.GoTo, D=Array([outlines_doc.pages[0].obj, Name.Fit])
        )
    assert isinstance(first.action, Dictionary)
    parsed = first.parsed_action
    assert isinstance(parsed, GoToAction)
    assert parsed.destination == [outlines_doc.pages[0].obj, Name.Fit]


def test_outline_item_parsed_action_none_when_unset():
    item = OutlineItem('Test')
    assert item.parsed_action is None


def test_outline_item_constructor_unwraps_action_instance(outlines_doc):
    action_obj = Dictionary(S=Name.GoTo, D=Array([outlines_doc.pages[0].obj, Name.Fit]))
    action = GoToAction(action_obj)
    item = OutlineItem('Test', action=action)
    assert item.action is action_obj
    assert isinstance(item.action, Dictionary)


def test_outline_item_constructor_unwraps_destination_instance(outlines_doc):
    page_ref = outlines_doc.pages[0].obj
    dest = Destination(page_ref, PageLocation.Fit)
    item = OutlineItem('Test', destination=dest)
    assert item.destination == [page_ref, Name.Fit]
    assert isinstance(item.destination, Array)


def test_outline_item_color_round_trip(outlines_doc):
    with outlines_doc.open_outline() as outline:
        first = outline.root[0]
        first.color = (0.1, 0.2, 0.3)
    first_obj = outlines_doc.Root.Outlines.First
    assert [float(x) for x in first_obj.C] == [0.1, 0.2, 0.3]

    with outlines_doc.open_outline() as outline:
        assert outline.root[0].color == (0.1, 0.2, 0.3)


def test_outline_item_color_default_omitted():
    item = OutlineItem('Test')
    assert item.color is None
    pdf = Pdf.new()
    pdf.add_blank_page()
    obj = item.to_dictionary_object(pdf)
    assert '/C' not in obj


def test_outline_item_color_cleared_deletes_c(outlines_doc):
    with outlines_doc.open_outline() as outline:
        first = outline.root[0]
        first.color = (0.1, 0.2, 0.3)
    first_obj = outlines_doc.Root.Outlines.First
    assert '/C' in first_obj

    with outlines_doc.open_outline() as outline:
        outline.root[0].color = None
    assert '/C' not in first_obj


def test_outline_item_flags_round_trip(outlines_doc):
    with outlines_doc.open_outline() as outline:
        first = outline.root[0]
        first.flags = OutlineItemFlag.Italic | OutlineItemFlag.Bold
    first_obj = outlines_doc.Root.Outlines.First
    assert first_obj.F == 3

    with outlines_doc.open_outline() as outline:
        assert outline.root[0].flags == OutlineItemFlag.Italic | OutlineItemFlag.Bold


def test_outline_item_flags_default_omitted():
    item = OutlineItem('Test')
    assert item.flags == OutlineItemFlag.NONE
    pdf = Pdf.new()
    pdf.add_blank_page()
    obj = item.to_dictionary_object(pdf)
    assert '/F' not in obj


def test_outline_item_italic_bold_properties():
    item = OutlineItem('Test')
    assert item.italic is False
    assert item.bold is False

    item.italic = True
    assert item.italic is True
    assert item.flags == OutlineItemFlag.Italic

    item.bold = True
    assert item.bold is True
    assert item.flags == OutlineItemFlag.Italic | OutlineItemFlag.Bold

    item.italic = False
    assert item.italic is False
    assert item.flags == OutlineItemFlag.Bold

    item.bold = False
    assert item.flags == OutlineItemFlag.NONE


def test_outline_item_structure_element_round_trip(outlines_doc):
    struct_elem = outlines_doc.make_indirect(Dictionary(Type=Name.StructElem))
    with outlines_doc.open_outline() as outline:
        first = outline.root[0]
        first.structure_element = struct_elem
    first_obj = outlines_doc.Root.Outlines.First
    assert first_obj.SE == struct_elem

    with outlines_doc.open_outline() as outline:
        assert outline.root[0].structure_element == struct_elem


def test_outline_item_color_malformed_strict_raises():
    obj = Dictionary(Title='foo', C=Name.NotAColor)
    with pytest.raises(OutlineStructureError, match='/C'):
        OutlineItem.from_dictionary_object(obj, strict=True)


def test_outline_item_color_malformed_nonstrict_drops():
    obj = Dictionary(Title='foo', C=Name.NotAColor)
    item = OutlineItem.from_dictionary_object(obj)
    assert item.color is None


def test_outline_item_flags_malformed_strict_raises():
    obj = Dictionary(Title='foo', F=Name.NotAFlag)
    with pytest.raises(OutlineStructureError, match='/F'):
        OutlineItem.from_dictionary_object(obj, strict=True)


def test_outline_item_flags_malformed_nonstrict_drops():
    obj = Dictionary(Title='foo', F=Name.NotAFlag)
    item = OutlineItem.from_dictionary_object(obj)
    assert item.flags == OutlineItemFlag.NONE


def test_destination_from_array_xyz(resources):
    with Pdf.open(resources / 'outlines.pdf') as doc:
        page_ref = doc.pages[0].obj
        arr = Array([page_ref, Name.XYZ, 10, 20, 1.5])
        dest = Destination.from_array(arr)
        assert dest.page == page_ref
        assert dest.fit_type == PageLocation.XYZ
        assert dest.left == 10
        assert dest.top == 20
        assert dest.zoom == 1.5
        assert dest.right is None


def test_destination_from_array_fit_no_args(resources):
    with Pdf.open(resources / 'outlines.pdf') as doc:
        page_ref = doc.pages[0].obj
        arr = Array([page_ref, Name.Fit])
        dest = Destination.from_array(arr)
        assert dest.page == page_ref
        assert dest.fit_type == PageLocation.Fit
        assert dest.left is None


def test_destination_to_array_matches_make_page_destination(resources):
    with Pdf.open(resources / 'outlines.pdf') as doc:
        page_ref = doc.pages[0].obj
        dest = Destination(
            page_ref, PageLocation.FitR, left=1, bottom=2, right=3, top=4
        )
        assert dest.to_array() == Array([page_ref, Name.FitR, 1, 2, 3, 4])


def test_destination_none_viewport_arg_becomes_null(resources):
    with Pdf.open(resources / 'outlines.pdf') as doc:
        page_ref = doc.pages[0].obj
        dest = Destination(page_ref, PageLocation.XYZ, left=None, top=5, zoom=None)
        arr = dest.to_array()
        assert list(arr) == [page_ref, Name.XYZ, None, 5, None]
        parsed = Destination.from_array(arr)
        assert parsed.left is None
        assert parsed.top == 5
        assert parsed.zoom is None


def test_destination_malformed_empty_array_raises():
    with pytest.raises(OutlineStructureError):
        Destination.from_array(Array([]))
    with pytest.raises(OutlineStructureError):
        Destination.from_array(Array([]), strict=True)


def test_destination_unrecognized_location_strict_raises(resources):
    with Pdf.open(resources / 'outlines.pdf') as doc:
        page_ref = doc.pages[0].obj
        arr = Array([page_ref, Name.Bogus])
        with pytest.raises(OutlineStructureError):
            Destination.from_array(arr, strict=True)


def test_destination_unrecognized_location_nonstrict_defaults_fit(resources):
    with Pdf.open(resources / 'outlines.pdf') as doc:
        page_ref = doc.pages[0].obj
        arr = Array([page_ref, Name.Bogus])
        dest = Destination.from_array(arr)
        assert dest.fit_type == PageLocation.Fit


@settings(deadline=60000)
@given(
    page_num=st.integers(0, 1),
    loc=st.sampled_from(list(PageLocation)),
    values=st.dictionaries(
        st.sampled_from(sorted(ALL_PAGE_LOCATION_KWARGS)),
        st.one_of(st.none(), st.integers(0, 10000)),
    ),
)
def test_destination_round_trip_all_page_locations(resources, page_num, loc, values):
    with Pdf.open(resources / 'outlines.pdf') as doc:
        page_ref = doc.pages[page_num].obj
        arg_names = PAGE_LOCATION_ARGS.get(loc, ())
        kwargs = {k: values.get(k) for k in arg_names}
        dest = Destination(page_ref, loc, **kwargs)
        parsed = Destination.from_array(dest.to_array())
        assert parsed == dest


def test_outline_item_resolved_destination_explicit_array(outlines_doc):
    with outlines_doc.open_outline() as outline:
        first = outline.root[0]
        first.destination = 0
    with outlines_doc.open_outline() as outline:
        dest = outline.root[0].resolved_destination(outlines_doc)
        assert isinstance(dest, Destination)
        assert dest.page == outlines_doc.pages[0].obj
        assert dest.fit_type == PageLocation.Fit


def test_outline_item_resolved_destination_int_page_number():
    pdf = Pdf.new()
    pdf.add_blank_page()
    item = OutlineItem('Test', 0)
    dest = item.resolved_destination(pdf)
    assert dest.page == pdf.pages[0].obj
    assert dest.fit_type == PageLocation.Fit


def test_outline_item_resolved_destination_string_named_dest():
    pdf = Pdf.new()
    page = pdf.add_blank_page()
    nt = NameTree.new(pdf)
    pdf.Root.Names = pdf.make_indirect(Dictionary(Dests=nt.obj))
    NameTree(pdf.Root.Names.Dests)['sec.1'] = pdf.make_indirect(
        Dictionary(D=Array([page.obj, Name.Fit]))
    )
    item = OutlineItem.from_dictionary_object(
        Dictionary(Title='Test', Dest=String('sec.1'))
    )
    dest = item.resolved_destination(pdf)
    assert dest.page == page.obj


def test_outline_item_resolved_destination_name_named_dest():
    pdf = Pdf.new()
    page = pdf.add_blank_page()
    pdf.Root.Dests = pdf.make_indirect(Dictionary())
    pdf.Root.Dests[Name.Chap1] = pdf.make_indirect(
        Dictionary(D=Array([page.obj, Name.Fit]))
    )
    item = OutlineItem.from_dictionary_object(Dictionary(Title='Test', Dest=Name.Chap1))
    dest = item.resolved_destination(pdf)
    assert dest.page == page.obj


def test_outline_item_resolved_destination_unresolvable_returns_none():
    pdf = Pdf.new()
    pdf.add_blank_page()
    item = OutlineItem.from_dictionary_object(
        Dictionary(Title='Test', Dest=String('nope'))
    )
    assert item.resolved_destination(pdf) is None


def test_outline_item_resolved_destination_none_when_no_destination():
    pdf = Pdf.new()
    pdf.add_blank_page()
    item = OutlineItem('Test')
    assert item.resolved_destination(pdf) is None


@settings(deadline=60000)
@given(
    page_num=st.integers(0, 1),
    page_loc=st.sampled_from(list(PageLocation) + ['invalid']),  # type: ignore
    kwargs=st.dictionaries(
        st.sampled_from(list(sorted(ALL_PAGE_LOCATION_KWARGS))), st.integers(0, 10000)
    ),
)
@example(
    page_num=0,
    page_loc='FitR',
    kwargs={'left': 0, 'top': 0, 'bottom': 0, 'right': 0, 'zoom': 0},
)
def test_page_destination(resources, page_num, page_loc, kwargs):
    # @given precludes use of outlines_doc fixture - causes hypothesis health check to
    # fail
    with Pdf.open(resources / 'outlines.pdf') as doc:
        page_ref = doc.pages[page_num]

        if page_loc == 'invalid':
            with pytest.raises(ValueError, match='unsupported page location'):
                make_page_destination(doc, page_num, page_loc, **kwargs)
            return

        dest = make_page_destination(doc, page_num, page_loc, **kwargs)
        if isinstance(page_loc, PageLocation):
            loc_str = page_loc.name
        else:
            loc_str = page_loc
        if loc_str == 'XYZ':
            args = 'left', 'top', 'zoom'
        elif loc_str == 'FitH':
            args = ('top',)
        elif loc_str == 'FitV':
            args = ('left',)
        elif loc_str == 'FitR':
            args = 'left', 'bottom', 'right', 'top'
        elif loc_str == 'FitBH':
            args = ('top',)
        elif loc_str == 'FitBV':
            args = ('left',)
        else:
            args = ()
        expected_dest = [page_ref.obj, Name(f'/{loc_str}')]
        expected_dest.extend(kwargs.get(k, 0) for k in args)
        assert dest == expected_dest


@settings(deadline=60000)
@given(
    title=st.text(max_size=1000),
    page_num=st.integers(0, 1),
    page_loc=st.sampled_from(PageLocation),
)
@example(
    title='',
    page_num=0,
    page_loc='FitR',
)
@example(
    title='þÿ',
    page_num=0,
    page_loc=PageLocation.XYZ,
)
def test_new_item(resources, title, page_num, page_loc):
    # @given precludes use of outlines_doc fixture - causes hypothesis health check to
    # fail
    with Pdf.open(resources / 'outlines.pdf') as doc:
        kwargs = dict.fromkeys(ALL_PAGE_LOCATION_KWARGS, 100)
        page_ref = doc.pages[page_num]

        new_item = OutlineItem(title, page_num, page_loc, **kwargs)
        with doc.open_outline() as outline:
            outline.root.append(new_item)
        if isinstance(page_loc, PageLocation):
            loc_str = page_loc.name
        else:
            loc_str = page_loc
        if loc_str == 'FitR':
            kwarg_len = 4
        elif loc_str == 'XYZ':
            kwarg_len = 3
        elif loc_str in ('FitH', 'FitV', 'FitBH', 'FitBV'):
            kwarg_len = 1
        else:
            kwarg_len = 0
        expected_dest = [page_ref.obj, Name(f'/{loc_str}')]
        expected_dest.extend(repeat(100, kwarg_len))
        assert new_item.destination == expected_dest
        new_obj = new_item.obj
        assert new_obj.Title == title
        assert new_obj.Dest == expected_dest
        assert new_obj.is_indirect is True


def test_outlineitem_str(outlines_doc):
    with outlines_doc.open_outline() as outline:
        assert str(outline.root[0]) == '[+] One -> <Action>'
        assert str(outline.root[1]) == '[ ] Two -> <Action>'

        outline.root[0].is_closed = False
        assert str(outline.root[0]) == '[-] One -> <Action>'

        item = OutlineItem('Test', make_page_destination(outlines_doc, 0))
        assert '[ ] Test -> 1' == str(item)

        assert str(outline) != ''


def test_outline_repr(outlines_doc):
    with outlines_doc.open_outline() as outline:
        assert repr(outline).startswith('<pikepdf.Outline:')
        assert repr(outline.root[0]).startswith('<pikepdf.OutlineItem')


def test_outline_destination_name_object_types():
    # See issues 258, 261
    obj = Dictionary(Title='foo', Dest=Name.Bar)
    item = OutlineItem.from_dictionary_object(obj)
    assert '.Root.Dests' in str(item)


def test_outline_root_setter_valid_input(outlines_doc):
    """Test that root.setter accepts a valid list of OutlineItem."""
    with outlines_doc.open_outline() as outline:
        # Test empty list input
        outline.root = []
        assert outline.root == []

        # Test setting outline.root with valid input
        new_root = [
            OutlineItem("Test outline 1"),
            OutlineItem("Test outline 2"),
        ]
        outline.root = new_root
        assert outline.root == new_root


def test_outline_root_setter_invalid_input_not_list(outlines_doc):
    """Test that root.setter raises ValueError if input is not a list."""
    with outlines_doc.open_outline() as outline:
        with pytest.raises(
            ValueError, match="Root must be a list of OutlineItem objects."
        ):
            outline.root = "Not a list"


def test_outline_root_setter_invalid_input_non_outlineitem(outlines_doc):
    """Test that root.setter raises ValueError if input list contains non-OutlineItem."""
    with outlines_doc.open_outline() as outline:
        invalid_root = ["Invalid", OutlineItem("Valid Section")]
        with pytest.raises(
            ValueError, match="Each item in root must be an OutlineItem."
        ):
            outline.root = invalid_root


@pytest.fixture
def missing_title_doc():
    # Spec-invalid: outline item lacks the required /Title field (issue #730)
    pdf = Pdf.new()
    pdf.add_blank_page()
    item = pdf.make_indirect(Dictionary(Dest=[pdf.pages[0].obj, Name.Fit]))
    pdf.Root.Outlines = pdf.make_indirect(
        Dictionary(Type=Name.Outlines, First=item, Last=item, Count=1)
    )
    yield pdf


def test_missing_title_nonstrict_recovers(missing_title_doc):
    """A missing /Title is quietly corrected to an empty string by default."""
    with missing_title_doc.open_outline() as outline:
        assert len(outline.root) == 1
        assert outline.root[0].title == ""


def test_missing_title_strict_raises(missing_title_doc):
    """A missing /Title raises OutlineStructureError in strict mode."""
    with pytest.raises(OutlineStructureError, match="Title"):
        with missing_title_doc.open_outline(strict=True) as outline:
            _ = outline.root
