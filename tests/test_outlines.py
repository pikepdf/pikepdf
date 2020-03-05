from itertools import repeat

import pytest
from hypothesis import given, example
from hypothesis import strategies as st

from pikepdf import Pdf, Dictionary, Name, Outline, OutlineItem, PageLocation, get_page_destination
from pikepdf.models.outlines import ALL_PAGE_LOCATION_KWARGS


@pytest.fixture
def outlines_doc(resources):
    # Contains an outline with references
    return Pdf.open(resources / 'outlines.pdf')


def test_load_outlines(outlines_doc):
    root_obj = outlines_doc.Root.Outlines
    first_obj = root_obj.First
    second_obj = first_obj.Next
    third_obj = second_obj.Next

    outlines = Outline(outlines_doc)
    assert len(outlines.root) == 3
    sec_one = outlines.root[0]
    assert sec_one.title == 'One'
    assert sec_one.is_closed is True
    assert sec_one.obj == first_obj
    sec_two = outlines.root[1]
    assert sec_two.title == 'Two'
    assert sec_two.is_closed is False
    assert sec_two.obj == second_obj
    sec_three = outlines.root[2]
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
    outlines = Outline(outlines_doc)

    # Remove all references
    for obj in [root_obj,
                first_obj, first_obj_a, first_obj_b, first_obj_b_i, first_obj_b_ii,
                second_obj, third_obj, third_obj_a, third_obj_b]:
        for n in ['/First', '/Last', '/Prev', '/Next', '/Parent']:
            if n in obj:
                del obj[n]

    outlines.save()
    # References should just be reproduced. Exhaustive check:
    for ref in [first_obj.Parent, second_obj.Parent, third_obj.Parent]:
        assert ref == root_obj
    for ref in [root_obj.First, second_obj.Prev,
                first_obj_a.Parent, first_obj_b.Parent]:
        assert ref == first_obj
    assert first_obj.First == first_obj_a
    assert first_obj_b.Prev == first_obj_a
    for ref in [first_obj.Last, first_obj_a.Next,
                first_obj_b_i.Parent, first_obj_b_ii.Parent]:
        assert ref == first_obj_b
    assert first_obj_b.First == first_obj_b_i
    assert first_obj_b_ii.Prev == first_obj_b_i
    assert first_obj_b.Last == first_obj_b_ii
    assert first_obj_b_i.Next == first_obj_b_ii
    assert first_obj.Next == second_obj
    for ref in [root_obj.Last, second_obj.Next,
                third_obj_a.Parent, third_obj_b.Parent]:
        assert ref == third_obj
    assert third_obj.First == third_obj_a
    assert third_obj_b.Prev == third_obj_a
    assert third_obj.Last == third_obj_b
    assert third_obj_a.Next == third_obj_b


def test_fix_references_swap_root(outlines_doc):
    root_obj = outlines_doc.Root.Outlines
    first_obj = root_obj.First
    second_obj = first_obj.Next
    third_obj = second_obj.Next
    outlines = Outline(outlines_doc)

    # Swap first and last item
    first_item = outlines.root.pop(0)
    last_item = outlines.root.pop()
    outlines.root.insert(0, last_item)
    outlines.root.append(first_item)
    outlines.save()

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
    outlines = Outline(outlines_doc)

    second_level = outlines.root[0].children[1].children  # One B (I and II)
    sec_one_b_i, sec_one_b_ii = second_level
    # Move second level items to root
    outlines.root.extend(second_level)
    second_level.clear()
    outlines.save()

    assert third_obj.Next == sec_one_b_i.obj
    assert sec_one_b_i.obj.Next == sec_one_b_ii.obj
    assert sec_one_b_i.obj.Prev == third_obj
    assert root_obj.Last == sec_one_b_ii.obj
    assert sec_one_b_i.obj.Parent == root_obj
    assert sec_one_b_ii.obj.Parent == root_obj
    assert first_b_obj.Count == 0
    assert '/First' not in first_b_obj
    assert '/Last' not in first_b_obj


def test_modify_closed(outlines_doc):
    root_obj = outlines_doc.Root.Outlines
    first_obj = root_obj.First
    second_obj = first_obj.Next
    third_obj = second_obj.Next
    # Initial state
    assert root_obj.Count == 3
    assert first_obj.Count == -2
    assert third_obj.Count == -2
    outlines = Outline(outlines_doc)
    # Opens first level
    for i in outlines.root:
        i.is_closed = False
    outlines.save()
    assert root_obj.Count == 7
    assert first_obj.Count == 2
    assert third_obj.Count == 2
    # Opens second level (only present in first section)
    for i in outlines.root[0].children:
        i.is_closed = False
    outlines.save()
    assert root_obj.Count == 9
    assert first_obj.Count == 4


def test_dest_or_action(outlines_doc):
    outlines = Outline(outlines_doc)
    first = outlines.root[0]
    first_obj = outlines_doc.Root.Outlines.First
    first_page = outlines_doc.pages[0]
    assert '/A' in first_obj
    assert '/Dest' not in first_obj
    # Set to first page.
    first.destination = 0
    outlines.save()
    # Reference should be replaced at this point.
    assert first.destination == [first_page, Name.Fit]
    assert first_obj.Dest == first.destination
    # Original action should be gone
    assert '/A' not in first_obj
    # Now save with a new action instead
    first.action = Dictionary(D=first.destination, S=Name.GoTo)
    first.destination = None
    outlines.save()
    assert first_obj.A.D == [first_page, Name.Fit]
    assert '/Dest' not in first_obj


@given(
    page_num=st.integers(0, 1),
    page_loc=st.sampled_from(PageLocation),
    kwargs=st.dictionaries(st.sampled_from(list(sorted(ALL_PAGE_LOCATION_KWARGS))), st.integers(0, 10000))
)
@example(
    page_num=0,
    page_loc='FitR',
    kwargs={'left': 0, 'top': 0, 'bottom': 0, 'right': 0, 'zoom': 0}
)
def test_page_destination(outlines_doc, page_num, page_loc, kwargs):
    page_ref = outlines_doc.pages[page_num]
    dest = get_page_destination(outlines_doc, page_num, page_loc, **kwargs)
    if isinstance(page_loc, PageLocation):
        loc_str = page_loc.name
    else:
        loc_str = page_loc
    if loc_str == 'XYZ':
        args = 'left', 'top', 'zoom'
    elif loc_str == 'FitH':
        args = 'top',
    elif loc_str == 'FitV':
        args = 'left',
    elif loc_str == 'FitR':
        args = 'left', 'bottom', 'right', 'top'
    elif loc_str == 'FitBH':
        args = 'top',
    elif loc_str == 'FitBV':
        args = 'left',
    else:
        args = ()
    expected_dest = [
        page_ref,
        '/{0}'.format(loc_str)
    ]
    expected_dest.extend(
        kwargs.get(k, 0)
        for k in args
    )
    assert dest == expected_dest


@given(
    title=st.text(),
    page_num=st.integers(0, 1),
    page_loc=st.sampled_from(PageLocation),
)
@example(
    title='',
    page_num=0,
    page_loc='FitR',
)
def test_new_item(outlines_doc, title, page_num, page_loc):
    kwargs = dict.fromkeys(ALL_PAGE_LOCATION_KWARGS, 100)
    outlines = Outline(outlines_doc)
    page_ref = outlines_doc.pages[page_num]

    new_item = OutlineItem(title, page_num, page_loc, **kwargs)
    outlines.root.append(new_item)
    outlines.save()
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
    expected_dest = [
        page_ref,
        '/{0}'.format(loc_str)
    ]
    expected_dest.extend(repeat(100, kwarg_len))
    assert new_item.destination == expected_dest
    new_obj = new_item.obj
    assert new_obj.Title == title
    assert new_obj.Dest == expected_dest
    assert new_obj.is_indirect is True
