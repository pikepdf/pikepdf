# SPDX-FileCopyrightText: 2022 James R. Barlow
# SPDX-License-Identifier: MPL-2.0

from __future__ import annotations

"""Defines exceptions that need to be visible to pikepdf._core (C++)."""


class DependencyError(Exception):
    """A third party dependency is needed to extract streams of this type."""


class FormCopyWarning(UserWarning):
    """Interactive form fields or widgets may be lost or left non-functional.

    Emitted when copying pages between documents in a way that drops or orphans
    AcroForm form fields. Use :meth:`pikepdf.Pdf.add_pages_from` to preserve them.
    """
