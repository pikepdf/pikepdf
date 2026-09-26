# SPDX-FileCopyrightText: 2026 James R. Barlow
# SPDX-License-Identifier: MPL-2.0

"""Embedded and associated files (ISO 19005-3 clause 6.8).

The role schemas of ``pdfa-3b.json`` check the file specifications and
embedded file streams the walker reaches. This module checks the one
requirement that relates objects to each other: every embedded file must be
an associated file, listed in some /AF array of the file.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from typing import TYPE_CHECKING

import pikepdf

if TYPE_CHECKING:
    from pikepdf.pdfa._context import ValidationContext


def _af_values(obj: pikepdf.Object) -> Iterator[pikepdf.Object]:
    """Yield the value of every /AF key in an object and its direct parts."""
    pending: list[pikepdf.Object] = [obj]
    while pending:
        value = pending.pop()
        if isinstance(value, pikepdf.Stream):
            value = value.stream_dict
        if isinstance(value, pikepdf.Dictionary):
            # items(), not get(): keys that are not UTF-8 cannot be looked up
            children = []
            for key, item in value.items():
                if key == '/AF':
                    yield item
                children.append(item)
        elif isinstance(value, pikepdf.Array):
            children = list(value)
        else:
            continue
        pending.extend(
            child
            for child in children
            if isinstance(child, pikepdf.Dictionary | pikepdf.Array)
            and not child.is_indirect
        )


def associated_file_objgens(
    objects: Iterable[object],
) -> set[tuple[int, int]]:
    """Return the objgen of every indirect object listed in an /AF array.

    Args:
        objects: The indirect objects to search, with their direct parts.
            Values that are not pikepdf objects are skipped.
    """
    found: set[tuple[int, int]] = set()
    for obj in objects:
        if not isinstance(obj, pikepdf.Object):
            continue
        for af in _af_values(obj):
            if not isinstance(af, pikepdf.Array):
                continue
            for item in af:
                if isinstance(item, pikepdf.Object) and item.is_indirect:
                    found.add(item.objgen)
    return found


def check_associated_files(ctx: ValidationContext) -> None:
    """Deny each embedded file that is not an associated file (6.8-4).

    Every file specification the walker checked as a ``FileSpec`` that has
    /EF must be listed in an /AF array of some object written to the file.
    """
    filespecs = [objgen for objgen, role in ctx.roles.items() if role == 'FileSpec']
    if not filespecs:
        return
    associated = associated_file_objgens(ctx.model.objects(ctx.pdf))
    for objgen in filespecs:
        if objgen in associated:
            continue
        filespec = ctx.pdf.get_object(objgen)
        if not isinstance(filespec, pikepdf.Dictionary) or '/EF' not in filespec:
            continue
        ctx.deny(
            ctx.rule(None, '6.8-4'),
            f'{ctx.describe(filespec)} (FileSpec)',
            "the embedded file is not an associated file: no /AF array lists "
            "its file specification",
        )
