# SPDX-FileCopyrightText: 2022 James R. Barlow
# SPDX-License-Identifier: MPL-2.0

# Type stubs for the bindings in src/core/qpdf_pagelist.cpp.
# See pikepdf/_core/__init__.pyi for how this stub package is laid out.

# pylint: disable=no-method-argument,unused-argument,no-self-use,too-many-public-methods
# ruff: noqa: D418
# mypy: disable-error-code="misc"

from __future__ import annotations

from collections.abc import Iterable
from typing import overload

from pikepdf._core._page import Page

class PageList:
    """For accessing pages in a PDF.

    A ``list``-like object enumerating a range of pages in a :class:`pikepdf.Pdf`.
    It may be all of the pages or a subset. Obtain using :attr:`pikepdf.Pdf.pages`.

    See :class:`pikepdf.Page` for accessing individual pages.
    """

    def append(self, page: Page, /) -> None:
        """Add another page to the end.

        While this method copies pages from one document to another, it does not
        copy certain metadata such as annotations, form fields, bookmarks or
        structural tree elements. Copying these is a more complex, application
        specific operation.
        """
    def extend(self, other: PageList | Iterable[Page], /) -> None:
        """Extend the ``Pdf`` by adding pages from an iterable of pages.

        While this method copies pages from one document to another, it does not
        copy certain metadata such as annotations, form fields, bookmarks or
        structural tree elements. Copying these is a more complex, application
        specific operation.
        """
    @overload
    def from_objgen(self, objgen: tuple[int, int]) -> Page: ...
    @overload
    def from_objgen(self, objgen: int, gen: int) -> Page: ...
    def from_objgen(
        self, objgen: tuple[int, int] | int, gen: int | None = None
    ) -> Page:
        """Given an objgen (object ID, generation), return the page.

        Raises an exception if no page matches.
        """
    def index(self, page: Page, /) -> int:
        """Given a page, find the index.

        That is, returns ``n`` such that ``pdf.pages[n] == this_page``.
        A ``ValueError`` exception is thrown if the page does not belong to
        to this ``Pdf``. The first page has index 0.
        """
    def insert(self, index: int, obj: Page, /) -> None:
        """Insert a page at the specified location.

        Args:
            index: location at which to insert page, 0-based indexing
            obj: page object to insert
        """
    def p(self, pnum: int, /) -> Page:
        """Look up page number in ordinal numbering, where 1 is the first page.

        This is provided for convenience in situations where ordinal numbering
        is more natural. It is equivalent to ``.pages[pnum - 1]``. ``.p(0)``
        is an error and negative indexing is not supported.

        If the PDF defines custom page labels (such as labeling front matter
        with Roman numerals and the main body with Arabic numerals), this
        function does not account for that. Use :attr:`pikepdf.Page.label`
        to get the page label for a page.
        """
    def remove(self, page: Page | None = None, *, p: int) -> None:
        """Remove a page.

        Args:
            page: If page is not None, remove that page.
            p: 1-based page number to remove, if page is None.
        """
    def reverse(self) -> None:
        """Reverse the order of pages."""
    @overload
    def __delitem__(self, idx: int, /) -> None: ...
    @overload
    def __delitem__(self, sl: slice, /) -> None: ...
    @overload
    def __getitem__(self, idx: int, /) -> Page: ...
    @overload
    def __getitem__(self, sl: slice, /) -> list[Page]: ...
    def __iter__(self) -> _PageListIterator: ...
    def __len__(self) -> int: ...
    @overload
    def __setitem__(self, idx: int, page: Page, /) -> None: ...
    @overload
    def __setitem__(self, sl: slice, pages: Iterable[Page], /) -> None: ...

class _PageListIterator:
    def __iter__(self) -> _PageListIterator: ...
    def __next__(self) -> Page: ...
