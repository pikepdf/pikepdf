# SPDX-FileCopyrightText: 2022 James R. Barlow
# SPDX-License-Identifier: MPL-2.0

from __future__ import annotations

"""Defines exceptions that need to be visible to pikepdf._core (C++)."""


class DependencyError(Exception):
    """A third party dependency is needed to extract streams of this type."""
