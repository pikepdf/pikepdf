# SPDX-FileCopyrightText: 2026 James R. Barlow
# SPDX-License-Identifier: MPL-2.0
"""Carry outline items (bookmarks) along with pages copied between PDFs."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pikepdf import Pdf

from pikepdf._core import ObjectSet
from pikepdf._named_dests import resolve_named_destination
from pikepdf.models.outlines import Outline, OutlineItem, OutlineStructureError
from pikepdf.objects import Array, Dictionary, Name, Object, String

# Items nested more deeply than this in the source are not carried.
_MAX_DEPTH = 64

_ObjGen = tuple[int, int]


def _explicit_destination(src: Pdf, item: OutlineItem) -> Array | None:
    """Return the explicit destination in *src* that an item goes to, if any."""
    target: object = item.destination
    if target is None and item.action is not None:
        if item.action.get(Name.S) != Name.GoTo:
            return None
        target = item.action.get(Name.D)
    if isinstance(target, String):
        return resolve_named_destination(src, str(target), 'string')
    if isinstance(target, Name):
        return resolve_named_destination(src, str(target), 'name')
    return target if isinstance(target, Array) else None


def _retarget(
    src: Pdf, item: OutlineItem, page_map: dict[_ObjGen, Object]
) -> Array | None:
    """Return a destination for *item* on a copied page, or None if not on one."""
    source = _explicit_destination(src, item)
    if source is None or len(source) == 0:
        return None
    page = source[0]
    if not isinstance(page, Dictionary) or not page.is_indirect:
        return None
    new_page = page_map.get(page.objgen)
    if new_page is None:
        return None
    return Array([new_page, *(source[i] for i in range(1, len(source)))])


class _Carrier:
    def __init__(self, src: Pdf, page_map: dict[_ObjGen, Object]) -> None:
        self.src = src
        self.page_map = page_map
        self.added = 0
        self.dropped = 0

    def carry(self, items: list[OutlineItem]) -> list[OutlineItem]:
        """Return new items for those of *items* that lead to a copied page.

        An item that does not is still kept, without its destination, when an
        item below it is kept.
        """
        kept = []
        for item in items:
            children = self.carry(item.children)
            destination = _retarget(self.src, item, self.page_map)
            if destination is None and not children:
                self.dropped += 1
                continue
            new = OutlineItem(
                item.title, destination, color=item.color, flags=item.flags
            )
            new.is_closed = item.is_closed
            new.children = children
            kept.append(new)
            self.added += 1
        return kept


def _last_top_level_item(root: Dictionary) -> Dictionary | None:
    last = root.get(Name.Last)
    if isinstance(last, Dictionary):
        return last
    # /Last is required when there are items, but follow the items if not
    seen = ObjectSet()
    node = root.get(Name.First)
    while isinstance(node, Dictionary) and seen.add(node):
        last = node
        node = node.get(Name.Next)
    return last if isinstance(last, Dictionary) else None


def _append(dest: Pdf, items: list[OutlineItem]) -> None:
    """Add *items* after the top level items of the outline of *dest*.

    The items already in the outline are not rewritten.
    """
    writer = Outline(dest, max_depth=_MAX_DEPTH)
    root = dest.Root.get(Name.Outlines)
    if not isinstance(root, Dictionary):
        root = dest.make_indirect(Dictionary(Type=Name.Outlines))
        dest.Root.Outlines = root
    elif not root.is_indirect:
        root = dest.make_indirect(root)
        dest.Root.Outlines = root

    last = _last_top_level_item(root)
    if last is None:
        writer._save_level_outline(root, items, 0, ObjectSet())
        return

    # Link the new items to each other under a stand-in for the root, then
    # move them to the end of the real one.
    holder = dest.make_indirect(Dictionary())
    writer._save_level_outline(holder, items, 0, ObjectSet())
    first_new = holder.First
    node: Object | None = first_new
    while node is not None:
        node.Parent = root
        node = node.get(Name.Next)
    last.Next = first_new
    first_new.Prev = last
    root.Last = holder.Last
    root.Count = max(root.get_int(Name.Count, 0), 0) + holder.get_int(Name.Count, 0)
    del holder.First, holder.Last


def migrate_outlines(
    dest: Pdf, src: Pdf, page_map: dict[_ObjGen, Object]
) -> tuple[int, int]:
    """Add the outline items of *src* that lead to copied pages to *dest*.

    *page_map* gives the page in *dest* for the objgen of each copied page of
    *src*. Returns the number of items added and the number left behind.
    """
    if not isinstance(src.Root.get(Name.Outlines), Dictionary):
        return 0, 0
    try:
        source_items = Outline(src, max_depth=_MAX_DEPTH).root
    except (OutlineStructureError, AttributeError, TypeError, ValueError):
        # An outline too damaged to read is left behind entirely
        return 0, 0
    carrier = _Carrier(src, page_map)
    items = carrier.carry(source_items)
    if items:
        _append(dest, items)
    return carrier.added, carrier.dropped
