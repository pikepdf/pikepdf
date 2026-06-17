# SPDX-FileCopyrightText: 2026 James R. Barlow
# SPDX-License-Identifier: MPL-2.0
"""Results and helpers for copying pages between PDFs."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from pikepdf import Pdf

from pikepdf.objects import Array, Dictionary, Name, String


@dataclass
class _DestRef:
    """A named-destination reference found on a copied page.

    ``owner[key]`` is the ``String``/``Name`` value to rewrite if the
    destination is renamed during migration.
    """

    owner: Dictionary
    key: Name
    kind: str  # 'string' (Names.Dests name tree) or 'name' (Root.Dests dict)
    name: str  # str(value): the string text, or a name like '/Chapter1'


def _maybe_add_dest(owner: Dictionary, key: Name, refs: list[_DestRef]) -> None:
    val = owner.get(key)
    if isinstance(val, String):
        refs.append(_DestRef(owner, key, 'string', str(val)))
    elif isinstance(val, Name):
        refs.append(_DestRef(owner, key, 'name', str(val)))
    # Array values are explicit destinations and need no migration.


def _collect_from_action(action: object, refs: list[_DestRef], depth: int = 0) -> None:
    if depth > 50 or not isinstance(action, Dictionary):
        return
    if action.get(Name.S) == Name.GoTo:
        _maybe_add_dest(action, Name.D, refs)
    nxt = action.get(Name.Next)
    if isinstance(nxt, Array):
        for sub in nxt:
            _collect_from_action(sub, refs, depth + 1)
    elif isinstance(nxt, Dictionary):
        _collect_from_action(nxt, refs, depth + 1)


def _collect_named_dest_refs(page_obj: Dictionary) -> list[_DestRef]:
    refs: list[_DestRef] = []
    annots = page_obj.get(Name.Annots)
    if not isinstance(annots, Array):
        return refs
    for annot in annots:
        if not isinstance(annot, Dictionary):
            continue
        _maybe_add_dest(annot, Name.Dest, refs)
        _collect_from_action(annot.get(Name.A), refs)
        aa = annot.get(Name.AA)
        if isinstance(aa, Dictionary):
            for k in aa.keys():
                _collect_from_action(aa[k], refs)
    return refs


@dataclass
class PageCopyResult:
    """Facts about a :meth:`pikepdf.Pdf.add_pages_from` operation.

    This object is intentionally extensible: future complex-merge concerns
    (outlines, structure tree, named destinations) will add fields here.
    """

    pages_added: int
    forms: Literal['preserve', 'strip']
    fields_added: int = 0
    renamed_fields: dict[str, str] = field(default_factory=dict)
    partial_fields: list[str] = field(default_factory=list)


def _resolve_indices(
    src: Pdf, pages: Iterable[int] | range | slice | None
) -> list[int]:
    n = len(src.pages)
    if pages is None:
        return list(range(n))
    if isinstance(pages, slice):
        return list(range(*pages.indices(n)))
    return [i if i >= 0 else n + i for i in pages]


def copy_pages(
    dest: Pdf,
    src: Pdf,
    pages: Iterable[int] | range | slice | None = None,
    *,
    forms: Literal['preserve', 'strip'] = 'preserve',
) -> PageCopyResult:
    indices = _resolve_indices(src, pages)
    src_acro = src.acroform
    dest_acro = dest.acroform

    start = len(dest.pages)
    src_pages = [src.pages[i] for i in indices]
    # Copy each page with append() (does NOT emit PageCopyWarning, unlike extend)
    for sp in src_pages:
        dest.pages.append(sp)

    if forms == 'strip':
        for offset in range(len(src_pages)):
            page_obj = dest.pages[start + offset].obj
            if Name.Annots in page_obj:
                kept = Array(
                    [a for a in page_obj.Annots if a.get(Name.Subtype) != Name.Widget]
                )
                if len(kept) == 0:
                    del page_obj.Annots
                else:
                    page_obj.Annots = kept

    renamed: dict[str, str] = {}
    if forms == 'preserve' and src_acro.exists:
        before = len(dest_acro.fields)
        for offset, sp in enumerate(src_pages):
            new_page = dest.pages[start + offset]
            src_names = [
                f.fully_qualified_name for f in src_acro.get_form_fields_for_page(sp)
            ]
            dest_acro.fix_copied_annotations(new_page, sp, src_acro)
            dest_names = [
                f.fully_qualified_name
                for f in dest_acro.get_form_fields_for_page(new_page)
            ]
            for old, new in zip(src_names, dest_names):
                if old is not None and new is not None and old != new:
                    renamed[old] = new
        fields_added = len(dest_acro.fields) - before
    else:
        fields_added = 0

    partial: list[str] = []
    if forms == 'preserve' and src_acro.exists and len(indices) < len(src.pages):
        selected = set(indices)
        # Map FQN -> set of all page indices where that field has widget annotations.
        # We use get_field_for_annotation so that multi-widget fields (parent+Kids)
        # are correctly attributed to their logical FQN.
        fqn_pages: dict[str, set[int]] = {}
        for i, p in enumerate(src.pages):
            for annot in src_acro.get_widget_annotations_for_page(p):
                fld = src_acro.get_field_for_annotation(annot).top_level_field
                name = fld.fully_qualified_name
                if name is not None:
                    fqn_pages.setdefault(name, set()).add(i)
        # Collect FQNs of fields on selected pages, then filter to those that also
        # have widgets on non-selected pages.
        selected_fqns: set[str] = set()
        for sp in src_pages:
            for fld in src_acro.get_form_fields_for_page(sp):
                if fld.fully_qualified_name is not None:
                    selected_fqns.add(fld.fully_qualified_name)
        for name in selected_fqns:
            if fqn_pages.get(name, set()) - selected:
                partial.append(name)

    return PageCopyResult(
        pages_added=len(src_pages),
        forms=forms,
        fields_added=fields_added,
        renamed_fields=renamed,
        partial_fields=partial,
    )
