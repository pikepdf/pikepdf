# SPDX-FileCopyrightText: 2022 James R. Barlow
# SPDX-License-Identifier: MPL-2.0

"""DocumentInfo dictionary access with type-safe operations."""

from __future__ import annotations

from collections.abc import Iterator
from typing import TYPE_CHECKING

from pikepdf.models.metadata._constants import clean
from pikepdf.objects import Name

if TYPE_CHECKING:  # pragma: no cover
    from pikepdf import Pdf


class DocinfoStore:
    """Wrapper for PDF DocumentInfo dictionary operations.

    Handles reading and writing values with proper encoding (ASCII/UTF-16)
    and character cleaning.
    """

    def __init__(self, pdf: Pdf):
        """Initialize with PDF reference.

        Args:
            pdf: The PDF document to manage DocumentInfo for.
        """
        self._pdf = pdf

    def get(self, name: Name) -> str | None:
        """Get DocumentInfo value.

        Args:
            name: The DocumentInfo key (e.g., Name.Title).

        Returns:
            The value as string, or None if not present.
        """
        if name not in self._pdf.docinfo:
            return None
        val = self._pdf.docinfo[name]
        return str(val) if val is not None else None

    def set(self, name: Name, value: str) -> None:
        """Set DocumentInfo value with proper encoding.

        Values that can be encoded as ASCII are stored as ASCII,
        otherwise stored as UTF-16 with BOM.

        Args:
            name: The DocumentInfo key (e.g., Name.Title).
            value: The string value to set.
        """
        # Ensure docinfo exists
        self._pdf.docinfo  # pylint: disable=pointless-statement
        value = clean(value)
        try:
            # Try to save pure ASCII
            self._pdf.docinfo[name] = value.encode('ascii')
        except UnicodeEncodeError:
            # qpdf will serialize this as a UTF-16 with BOM string
            self._pdf.docinfo[name] = value

    def delete(self, name: Name) -> bool:
        """Delete DocumentInfo key.

        Args:
            name: The DocumentInfo key to delete.

        Returns:
            True if key was present and deleted, False if not present.
        """
        if name in self._pdf.docinfo:
            del self._pdf.docinfo[name]
            return True
        return False

    def __contains__(self, name: Name) -> bool:
        """Check if key exists in DocumentInfo."""
        return name in self._pdf.docinfo

    def keys(self) -> Iterator[Name]:
        """Iterate DocumentInfo keys."""
        yield from self._pdf.docinfo.keys()  # type: ignore[misc]
