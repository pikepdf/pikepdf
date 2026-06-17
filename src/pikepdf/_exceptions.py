# SPDX-FileCopyrightText: 2022 James R. Barlow
# SPDX-License-Identifier: MPL-2.0

from __future__ import annotations

"""Defines exceptions that need to be visible to pikepdf._core (C++)."""


class DependencyError(Exception):
    """A third party dependency is needed to extract streams of this type."""


class PageCopyWarning(UserWarning):
    """Form fields or named destinations may be lost when copying pages.

    Emitted when copying pages between documents (e.g. ``pages.extend()``) in a
    way that drops or orphans AcroForm form fields or fails to carry named
    destinations referenced by the copied pages. Use
    :meth:`pikepdf.Pdf.add_pages_from` to preserve them.
    """
