# SPDX-FileCopyrightText: 2026 Khushwant Parihar
# SPDX-License-Identifier: MPL-2.0

"""Support for tagged PDF logical structure (see {{ pdfrm }} section 14.7)."""

from __future__ import annotations

from pikepdf.models.structure._common import StructureTreeError
from pikepdf.models.structure._content import (
    ContentMarker,
    FontUsage,
    MarkedContent,
    find_font_usage,
    find_marked_content,
    mark_text_runs,
    next_mcid,
)
from pikepdf.models.structure._tree import (
    MarkedContentRef,
    ObjectRef,
    ParentTree,
    StructElem,
    StructTree,
)

__all__ = [
    'ContentMarker',
    'FontUsage',
    'MarkedContent',
    'MarkedContentRef',
    'ObjectRef',
    'ParentTree',
    'StructElem',
    'StructTree',
    'StructureTreeError',
    'find_font_usage',
    'find_marked_content',
    'mark_text_runs',
    'next_mcid',
]
