# SPDX-FileCopyrightText: 2026 James R. Barlow
# SPDX-License-Identifier: MPL-2.0
"""Results and helpers for copying pages between PDFs."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


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
