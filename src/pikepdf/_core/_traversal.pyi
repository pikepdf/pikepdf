# SPDX-FileCopyrightText: 2026 James R. Barlow
# SPDX-License-Identifier: MPL-2.0

# Type stubs for the bindings in src/core/traversal.cpp.
# See pikepdf/_core/__init__.pyi for how this stub package is laid out.

# pylint: disable=no-method-argument,unused-argument,no-self-use,too-many-public-methods
# ruff: noqa: D418
# mypy: disable-error-code="misc"

from __future__ import annotations

from collections.abc import Iterable
from enum import IntFlag

from pikepdf._core._object import Object, ObjectHelper
from pikepdf._core._object_construct import Dictionary
from pikepdf._core._page import Page
from pikepdf._core._qpdf import Pdf

class ObjectSet:
    """The objects that a walk of a PDF's object graph has already visited.

    The objects of a PDF form a graph, not a tree. An object may be referenced
    from many places, and may refer back to one of its own ancestors, whether
    by design (a page and its ``/Parent``), by the choice of the software that
    wrote the file (form XObjects that share one ``/Resources`` dictionary
    listing all of them), or by malice. Code that follows references must
    therefore remember where it has been. Limiting the depth of the walk is
    not enough: that stops an endless loop, but still visits a shared object
    once for every path that leads to it, and the number of paths grows
    exponentially with the depth.

    :meth:`add` reports whether an object is new, so a walk needs one line to
    be safe:

    .. code-block:: python

        seen = pikepdf.ObjectSet()
        pending = [pdf.Root.Outlines]
        while pending:
            node = pending.pop()
            if not isinstance(node, pikepdf.Dictionary) or not seen.add(node):
                continue
            ...  # examine node
            pending.append(node.get(Name.Next))
            pending.append(node.get(Name.First))

    Objects are told apart by identity, not by value: two dictionaries with
    the same contents are different objects, while every reference to one
    indirect object is the same object, as
    :meth:`pikepdf.Object.is_same_object_as` tests. This is more reliable than a
    :class:`set` of :attr:`pikepdf.Object.objgen`, which cannot tell direct
    objects apart, since they all report ``(0, 0)``, and confuses objects that
    have the same number in different :class:`pikepdf.Pdf`.

    Only :class:`pikepdf.Object` and its helpers, such as :class:`pikepdf.Page`,
    can be added. A helper counts as the object it wraps. Numbers, booleans and
    other values that pikepdf converts to Python types have no identity to
    track, and adding one raises :exc:`TypeError`.

    The set keeps its objects alive in memory but does not keep their
    :class:`pikepdf.Pdf` open. It cannot be iterated; it answers only whether
    an object has been seen.

    Where pikepdf provides a walk, prefer it to writing one. In particular,
    :meth:`pikepdf.Pdf.content_scopes` finds everything that pages draw and
    the resources they use, and needs no ``ObjectSet``.

    Args:
        objects: Objects to add to the new set.

    .. versionadded:: 10.17
    """

    def __init__(
        self, objects: Iterable[Object | ObjectHelper] | None = None
    ) -> None: ...
    def add(self, obj: Object | ObjectHelper) -> bool:
        """Add an object, and report whether it was new.

        Returns:
            True if the object was not in the set before this call, so the
            caller is visiting it for the first time. False if it was already
            present. Note that this differs from :meth:`set.add`, which returns
            nothing.
        """
    def discard(self, obj: Object | ObjectHelper) -> None:
        """Remove an object, if it is present."""
    def clear(self) -> None:
        """Remove every object."""
    def __contains__(self, obj: object) -> bool: ...
    def __len__(self) -> int: ...
    def __repr__(self) -> str: ...

class _ContentScopeKind(IntFlag):
    """The kinds of content scope, named as :attr:`pikepdf.ContentScope.kind`."""

    page: ...
    form: ...
    appearance: ...
    pattern: ...
    glyph: ...
    softmask: ...

class _ContentScopeWalk:
    """Finds the content scopes of pages, reporting each once.

    The implementation of :meth:`pikepdf.Pdf.content_scopes`. One instance
    remembers what it has reported across calls to :meth:`walk`.
    """

    def __init__(self) -> None: ...
    def walk(
        self, page: Page, kinds: int
    ) -> list[tuple[_ContentScopeKind, Object, Dictionary | None]]:
        """Return (kind, content, resources) for each new scope of *page*.

        *kinds* is a mask of the kinds to return; everything is searched.
        """

def _action_chain(action: Object) -> list[Dictionary]:
    """Return an action and each action reachable through /Next, each once.

    /Next holds one action or an array of them. Actions are returned in the
    order a viewer would first reach them. Anything that is not a dictionary
    is skipped.
    """

def _reachable_objects(pdf: Pdf, roots: Iterable[Object]) -> list[Object]:
    """Return the indirect objects reachable from *roots*, each once.

    Objects are in the order a depth-first walk first meets them. An indirect
    integer, real, boolean or null is left out.
    """
