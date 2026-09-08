# SPDX-FileCopyrightText: 2022 James R. Barlow
# SPDX-License-Identifier: MPL-2.0

# Type stubs for the bindings in src/core/numbertree.cpp.
# See pikepdf/_core/__init__.pyi for how this stub package is laid out.

# pylint: disable=no-method-argument,unused-argument,no-self-use,too-many-public-methods
# ruff: noqa: D418
# mypy: disable-error-code="misc"

from __future__ import annotations

from collections.abc import Iterator, MutableMapping
from typing import Any

from pikepdf._core._object import Object, _ObjectMapping
from pikepdf._core._qpdf import Pdf

class NumberTree(MutableMapping[int, Object]):
    """An object for managing *number tree* data structures in PDFs.

    A number tree is a key-value data structure, like name trees, except that the
    key is an integer. It behaves like ``Dict[int, pikepdf.Object]``.

    The keys can be sparse - not all integers positions will be populated. Keys
    are also always sorted; pikepdf will ensure that the order is preserved.

    The value may be any PDF object. Typically it will be a dictionary or array.

    Internally in the PDF, a number tree can be a fairly complex tree data structure
    implemented with many dictionaries and arrays. pikepdf (using libqpdf)
    will automatically read, repair and maintain this tree for you. There should not
    be any reason to access the internal nodes of a number tree; use this
    interface instead.

    NumberTrees are not used much in PDF. The main thing they provide is a mapping
    between 0-based page numbers and user-facing page numbers (which pikepdf
    also exposes as ``Page.label``). The ``/PageLabels`` number tree is where the
    page numbering rules are defined.

    Number trees are described in the {{ pdfrm }} section 7.9.7. See section 12.4.2
    for a description of the page labels number tree. Here is an example of modifying
    an existing page labels number tree:

    .. code-block:: python

        pagelabels = NumberTree(pdf.Root.PageLabels)
        # Label pages starting at 0 with lowercase Roman numerals
        pagelabels[0] = Dictionary(S=Name.r)
        # Label pages starting at 6 with decimal numbers
        pagelabels[6] = Dictionary(S=Name.D)

        # Page labels will now be:
        # i, ii, iii, iv, v, 1, 2, 3, ...

    Do not modify the internal structure of a name tree while you have a
    ``NumberTree`` referencing it. Access it only through the ``NumberTree`` object.

    .. versionadded:: 5.4
    """

    @staticmethod
    def new(pdf: Pdf, *, auto_repair: bool = True) -> NumberTree:
        """Create a new NumberTree in the provided Pdf.

        You will probably need to insert the number tree in the PDF's
        catalog. For example, to insert this number tree in
        /Root /PageLabels:

        .. code-block:: python

            nt = NumberTree.new(pdf)
            pdf.Root.PageLabels = nt.obj
        """
    def __contains__(self, key: object, /) -> bool: ...
    def __delitem__(self, key: int, /) -> None: ...
    def __eq__(self, other: Any, /) -> bool: ...
    def __getitem__(self, key: int, /) -> Object: ...
    def __iter__(self) -> Iterator[int]: ...
    def __len__(self) -> int: ...
    def __setitem__(self, key: int, o: Object, /) -> None: ...
    def __init__(self, obj: Object, *, auto_repair: bool = ...) -> None: ...
    def _as_map(self) -> _ObjectMapping: ...
    @property
    def obj(self) -> Object: ...
