# SPDX-FileCopyrightText: 2022 James R. Barlow
# SPDX-License-Identifier: MPL-2.0

"""Defines exceptions that need to be visible to pikepdf._core (C++)."""

from __future__ import annotations

from pikepdf._core import PikepdfError


class PikepdfWarning(UserWarning):
    """Root of the pikepdf warning hierarchy.

    Every warning pikepdf issues on its own behalf derives from this, so
    ``warnings.simplefilter('error', PikepdfWarning)`` turns all of them into
    exceptions. See :class:`pikepdf.PikepdfError` for the exception side.
    """


class DependencyError(PikepdfError):
    """A third party dependency is needed to extract streams of this type."""


class PageCopyWarning(PikepdfWarning):
    """Form fields or named destinations may be lost when copying pages.

    Emitted when copying pages between documents (e.g. ``pages.extend()``) in a
    way that drops or orphans AcroForm form fields or fails to carry named
    destinations referenced by the copied pages. Use
    :meth:`pikepdf.Pdf.add_pages_from` to preserve them.
    """
