# SPDX-FileCopyrightText: 2026 James R. Barlow
# SPDX-License-Identifier: MPL-2.0
"""Carry optional content (layers) along with pages copied between PDFs.

Copying a page copies the optional content groups it refers to, but a viewer
ignores every group that the catalog's ``/OCProperties`` does not list
(ISO 32000-2, 8.11.4.2). This module lists the copied groups in the
destination and gives them the state, and the place in the user interface,
that the source's default configuration gave them.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import TYPE_CHECKING, TypeGuard

if TYPE_CHECKING:
    from pikepdf import Page, Pdf

from pikepdf._core import ObjectSet
from pikepdf.objects import Array, Dictionary, Name, Object, Stream, String

# Nesting of /Order beyond this is not something a viewer could present, and
# is dropped rather than followed.
_MAX_ORDER_DEPTH = 32

_ObjGen = tuple[int, int]


def _items(value: object) -> Iterable[Object]:
    """Return the items of an array, or nothing if *value* is not an array."""
    return value if isinstance(value, Array) else ()


def _is_group(value: object) -> TypeGuard[Dictionary]:
    """Test whether *value* can be listed as an optional content group."""
    return (
        isinstance(value, Dictionary)
        and value.is_indirect
        and value.get(Name.Type) == Name.OCG
    )


class _GroupFinder:
    """Collects the optional content groups that content depends on."""

    def __init__(self) -> None:
        self.groups: list[Object] = []
        self._seen = ObjectSet()

    def add(self, value: object) -> None:
        """Add the groups named by an ``/OC`` entry or a property list.

        *value* is an optional content group, or a membership dictionary that
        makes visibility depend on several groups.
        """
        if not isinstance(value, Dictionary):
            return
        if _is_group(value):
            if self._seen.add(value):
                self.groups.append(value)
            return
        if value.get(Name.Type) != Name.OCMD or not self._seen.add(value):
            return
        # /OCGs is one group or an array of them. /VE is an expression: an
        # array of an operator followed by groups and further expressions.
        pending = [value.get(Name.OCGs), value.get(Name.VE)]
        while pending:
            item = pending.pop()
            if isinstance(item, Array):
                if self._seen.add(item):
                    pending.extend(item)
            elif _is_group(item) and self._seen.add(item):
                self.groups.append(item)

    def add_resources(self, resources: Dictionary | None) -> None:
        if resources is None or not self._seen.add(resources):
            return
        # Marked content names its group through /Properties. Which entries
        # the content really uses is not examined; all are taken to be used.
        for properties in (resources.get_dict(Name.Properties) or {}).values():
            self.add(properties)
        for xobject in (resources.get_dict(Name.XObject) or {}).values():
            if isinstance(xobject, Stream):
                self.add(xobject.get(Name.OC))


def _find_groups(src: Pdf, src_pages: list[Page]) -> list[Object]:
    """Return the optional content groups that *src_pages* depend on."""
    finder = _GroupFinder()
    for page in src_pages:
        for annot in _items(page.obj.get(Name.Annots)):
            if isinstance(annot, Dictionary):
                finder.add(annot.get(Name.OC))
    for scope in src.content_scopes(pages=src_pages):
        # A form XObject or appearance stream may itself be optional
        if isinstance(scope.content, Stream):
            finder.add(scope.content.get(Name.OC))
        finder.add_resources(scope.resources)
    return finder.groups


def _extend(config: Dictionary, key: Name, new_items: Sequence[Object]) -> None:
    if not new_items:
        return
    existing = config.get(key)
    if isinstance(existing, Array):
        existing.extend(new_items)
    else:
        config[key] = Array(new_items)


class _Copied:
    """The groups newly listed in the destination, found by source group."""

    def __init__(self) -> None:
        self._by_source: dict[_ObjGen, Object] = {}

    def add(self, source: Object, copy: Object) -> None:
        self._by_source[source.objgen] = copy

    def get(self, source: object) -> Object | None:
        if not _is_group(source):
            return None
        return self._by_source.get(source.objgen)

    def select(self, sources: object) -> list[Object]:
        """Return the copies of those of *sources* that were copied, each once."""
        found: list[Object] = []
        seen = ObjectSet()
        for source in _items(sources):
            copy = self.get(source)
            if copy is not None and seen.add(copy):
                found.append(copy)
        return found


def _filter_order(
    order: Array, copied: _Copied, seen: ObjectSet, depth: int = 0
) -> tuple[list[Object], int]:
    """Reduce an ``/Order`` array to the groups that were copied.

    Returns the new items and the number of groups among them and below them.
    """
    kept: list[Object] = []
    n_groups = 0
    after_group = False  # whether a nested array would attach to a kept group
    for index, item in enumerate(order):
        if isinstance(item, Array):
            if depth >= _MAX_ORDER_DEPTH or not seen.add(item):
                continue
            below, n_below = _filter_order(item, copied, seen, depth + 1)
            if not n_below:
                continue
            n_groups += n_below
            if isinstance(below[0], String) or after_group:
                kept.append(Array(below))
            else:
                # Sublayers of a group that was not copied. Left nested, they
                # would be shown as sublayers of whatever now precedes them.
                kept.extend(below)
        elif isinstance(item, String):
            # The label of a collection, which only a nested array may have
            if index == 0 and depth > 0:
                kept.append(String(bytes(item)))
        elif isinstance(item, Dictionary):
            copy = copied.get(item)
            after_group = copy is not None
            if copy is not None:
                kept.append(copy)
                n_groups += 1
    return kept, n_groups


def _usage_applications(source: object, copied: _Copied) -> list[Dictionary]:
    """Return the ``/AS`` usage application dictionaries for the copied groups."""
    found = []
    for usage in _items(source):
        if not isinstance(usage, Dictionary):
            continue
        event = usage.get(Name.Event)
        groups = copied.select(usage.get(Name.OCGs))
        if not isinstance(event, Name) or not groups:
            continue
        categories = [
            c for c in _items(usage.get(Name.Category)) if isinstance(c, Name)
        ]
        found.append(
            Dictionary(Event=event, Category=Array(categories), OCGs=Array(groups))
        )
    return found


def migrate_layers(dest: Pdf, src: Pdf, src_pages: list[Page]) -> int:
    """List the groups that copied pages depend on in *dest*, with their state.

    Returns the number of groups newly listed in *dest*.
    """
    src_props = src.Root.get(Name.OCProperties)
    if not isinstance(src_props, Dictionary):
        return 0
    # A group the source does not list is ignored by viewers, and stays so
    listed = ObjectSet(g for g in _items(src_props.get(Name.OCGs)) if _is_group(g))
    groups = [g for g in _find_groups(src, src_pages) if g in listed]
    if not groups:
        return 0

    dest_props = dest.Root.get(Name.OCProperties)
    already = ObjectSet()
    if isinstance(dest_props, Dictionary):
        for existing in _items(dest_props.get(Name.OCGs)):
            if isinstance(existing, Object):
                already.add(existing)

    copied = _Copied()
    new_groups: list[tuple[Object, Object]] = []
    for group in groups:
        copy = group if group.is_owned_by(dest) else dest.copy_foreign(group)
        if already.add(copy):
            copied.add(group, copy)
            new_groups.append((group, copy))
    if not new_groups:
        return 0

    if not isinstance(dest_props, Dictionary):
        dest_props = dest.make_indirect(Dictionary())
        dest.Root.OCProperties = dest_props
    _extend(dest_props, Name.OCGs, [copy for _, copy in new_groups])
    config = dest_props.get(Name.D)
    if not isinstance(config, Dictionary):
        dest_props.D = Dictionary()
        config = dest_props.D

    src_config = src_props.get(Name.D)
    if not isinstance(src_config, Dictionary):
        src_config = Dictionary()

    # A configuration sets every group to /BaseState, then turns on those in
    # /ON, then turns off those in /OFF.
    src_base_off = src_config.get(Name.BaseState) == Name.OFF
    src_on = ObjectSet(g for g in _items(src_config.get(Name.ON)) if _is_group(g))
    src_off = ObjectSet(g for g in _items(src_config.get(Name.OFF)) if _is_group(g))
    dest_base_off = config.get(Name.BaseState) == Name.OFF
    turn_on = []
    turn_off = []
    for group, copy in new_groups:
        visible = group not in src_off and (group in src_on or not src_base_off)
        if visible and dest_base_off:
            turn_on.append(copy)
        elif not visible and not dest_base_off:
            turn_off.append(copy)
    _extend(config, Name.ON, turn_on)
    _extend(config, Name.OFF, turn_off)

    src_order = src_config.get(Name.Order)
    if isinstance(src_order, Array):
        order, _ = _filter_order(src_order, copied, ObjectSet([src_order]))
        _extend(config, Name.Order, order)

    _extend(config, Name.Locked, copied.select(src_config.get(Name.Locked)))

    # At most one group of a radio button group is on. One member alone is
    # not constrained by anything.
    radio_groups = []
    for radio_group in _items(src_config.get(Name.RBGroups)):
        members = copied.select(radio_group)
        if len(members) >= 2:
            radio_groups.append(Array(members))
    _extend(config, Name.RBGroups, radio_groups)

    _extend(config, Name.AS, _usage_applications(src_config.get(Name.AS), copied))
    return len(new_groups)
