# SPDX-FileCopyrightText: 2022 James R. Barlow
# SPDX-License-Identifier: MPL-2.0

# Type stubs for the bindings in src/core/nametree.cpp.
# See pikepdf/_core/__init__.pyi for how this stub package is laid out.

# pylint: disable=no-method-argument,unused-argument,no-self-use,too-many-public-methods
# ruff: noqa: D418
# mypy: disable-error-code="misc"

from __future__ import annotations

from collections.abc import Iterator, MutableMapping
from typing import Any

from pikepdf._core._object import Object, _ObjectMapping
from pikepdf._core._qpdf import Pdf

class NameTree(MutableMapping[str | bytes, Object]):
    """An object for managing *name tree* data structures in PDFs.

    A name tree is a key-value data structure. The keys are any binary strings
    (that is, Python ``bytes``). If ``str`` selected is provided as a key,
    the UTF-8 encoding of that string is tested. Name trees are (confusingly)
    not indexed by ``pikepdf.Name`` objects. They behave like
    ``DictMapping[bytes, pikepdf.Object]``.

    The keys are sorted; pikepdf will ensure that the order is preserved.

    The value may be any PDF object. Typically it will be a dictionary or array.

    Internally in the PDF, a name tree can be a fairly complex tree data structure
    implemented with many dictionaries and arrays. pikepdf (using libqpdf)
    will automatically read, repair and maintain this tree for you. There should not
    be any reason to access the internal nodes of a number tree; use this
    interface instead.

    NameTrees are used to store certain objects like file attachments in a PDF.
    Where a more specific interface exists, use that instead, and it will
    manipulate the name tree in a semantic correct manner for you.

    Do not modify the internal structure of a name tree while you have a
    ``NameTree`` referencing it. Access it only through the ``NameTree`` object.

    Names trees are described in the {{ pdfrm }} section 7.9.6. See section 7.7.4
    for a list of PDF objects that are stored in name trees.

    .. versionadded:: 3.0
    """

    @staticmethod
    def new(pdf: Pdf, *, auto_repair: bool = True) -> NameTree:
        """Create a new NameTree in the provided Pdf.

        You will probably need to insert the name tree in the PDF's
        catalog. For example, to insert this name tree in
        /Root /Names /Dests:

        .. code-block:: python

            nt = NameTree.new(pdf)
            pdf.Root.Names.Dests = nt.obj
        """
    def __contains__(self, name: object, /) -> bool: ...
    def __delitem__(self, name: str | bytes, /) -> None: ...
    def __eq__(self, other: Any, /) -> bool: ...
    def __getitem__(self, name: str | bytes, /) -> Object: ...
    def __iter__(self) -> Iterator[bytes]: ...
    def __len__(self) -> int: ...
    def __setitem__(self, name: str | bytes, o: Object, /) -> None: ...
    def __init__(self, obj: Object, *, auto_repair: bool = ...) -> None: ...
    def _as_map(self) -> _ObjectMapping: ...
    @property
    def obj(self) -> Object:
        """Returns the underlying root object for this name tree."""
