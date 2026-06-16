# SPDX-FileCopyrightText: 2026 James R. Barlow
# SPDX-License-Identifier: MPL-2.0
"""Results and helpers for copying pages between PDFs."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from pikepdf import Pdf


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
    # Copy each page with append() (does NOT emit FormCopyWarning, unlike extend)
    for sp in src_pages:
        dest.pages.append(sp)

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

    return PageCopyResult(
        pages_added=len(src_pages),
        forms=forms,
        fields_added=fields_added,
        renamed_fields=renamed,
    )
