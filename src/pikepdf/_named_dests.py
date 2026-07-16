# SPDX-FileCopyrightText: 2026 James R. Barlow
# SPDX-License-Identifier: MPL-2.0
"""Shared helpers for resolving PDF named destinations (12.3.2.4).

Named destinations may be stored in either the modern name tree (catalog's
``/Names/Dests``, PDF 1.2+, preferred) or the legacy dictionary (catalog's
``/Dests``, PDF 1.1). This module centralizes the lookup logic shared by
:mod:`pikepdf._page_copy` (page-copy migration) and
:mod:`pikepdf.models.outlines` (resolving an outline item's named
destination).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from pikepdf import Pdf

from pikepdf.objects import Array, Dictionary, Name, Object

DestKind = Literal['string', 'name']


def lookup_named_destination_entry(
    pdf: Pdf, name: str, kind: DestKind
) -> Object | None:
    """Look up a named destination's raw entry.

    The entry is either an ``Array`` (an explicit destination) or a
    ``Dictionary`` with a ``/D`` entry (and optionally ``/SD``).

    Arguments:
        pdf: The PDF document to look up the destination in.
        name: The destination's name. For ``kind='name'``, this must
            include the leading ``/`` (e.g. ``str(Name.Chap1)``).
        kind: ``'string'`` to look up in the modern ``Names.Dests`` name
            tree (PDF 1.2+); ``'name'`` to look up in the legacy
            ``Root.Dests`` dictionary (PDF 1.1).
    """
    if kind == 'string':
        from pikepdf import NameTree

        names = pdf.Root.get(Name.Names)
        if not isinstance(names, Dictionary):
            return None
        dests = names.get(Name.Dests)
        if dests is None:
            return None
        nt = NameTree(dests)
        return nt[name] if name in nt else None
    dests = pdf.Root.get(Name.Dests)
    if not isinstance(dests, Dictionary):
        return None
    return dests.get(Name(name))


def resolve_named_destination(pdf: Pdf, name: str, kind: DestKind) -> Array | None:
    """Resolve a named destination to its explicit destination ``Array``.

    Returns ``None`` if the name is not found, or the entry is malformed
    (its ``/D`` is not an array, or the array's first element is not an
    indirect page reference).
    """
    entry = lookup_named_destination_entry(pdf, name, kind)
    if entry is None:
        return None
    arr = entry.get(Name.D) if isinstance(entry, Dictionary) else entry
    if not isinstance(arr, Array) or len(arr) == 0:
        return None
    if not getattr(arr[0], 'is_indirect', False):
        return None
    return arr
