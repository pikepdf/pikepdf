# SPDX-FileCopyrightText: 2026 James R. Barlow
# SPDX-License-Identifier: MPL-2.0

"""The content streams of a page and the resources each is interpreted with.

The search itself is in src/core/traversal.cpp. This module holds the type it
reports and the handling of the ``kinds`` argument.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from typing import Literal

from pikepdf._core import Page, _ContentScopeWalk
from pikepdf.objects import Dictionary, Object, Stream

ContentScopeKind = Literal['page', 'form', 'appearance', 'pattern', 'glyph', 'softmask']

# The bit that content_scope_kind in src/core/traversal.h gives each kind
_KIND_BITS: dict[str, int] = {
    'page': 1,
    'form': 2,
    'appearance': 4,
    'pattern': 8,
    'glyph': 16,
    'softmask': 32,
}
_KIND_NAMES: dict[int, ContentScopeKind] = {
    1: 'page',
    2: 'form',
    4: 'appearance',
    8: 'pattern',
    16: 'glyph',
    32: 'softmask',
}
_ALL_KINDS = sum(_KIND_BITS.values())


@dataclass(frozen=True, slots=True, eq=False)
class ContentScope:
    """A content stream and the resources it is interpreted with.

    A content stream refers to fonts, images and other objects by name, and
    the names are looked up in a resource dictionary. The stream and its
    resources must therefore be considered together.

    Returned by :meth:`pikepdf.Pdf.content_scopes` and
    :meth:`pikepdf.Page.content_scopes`.

    The same stream may appear in more than one scope, with different
    resources, when what it means depends on where it is used.

    Two ``ContentScope`` are equal only if they are the same Python object.
    Use :meth:`pikepdf.Object.is_same_object_as` to compare what they hold.

    .. versionadded:: 10.17
    """

    kind: ContentScopeKind
    """What the content stream is.

    ``'page'``
        The content of a page.
    ``'form'``
        A form XObject, listed in the ``/XObject`` resources of another scope.
    ``'appearance'``
        An appearance stream of one of the page's annotations, including the
        widgets of form fields.
    ``'pattern'``
        A tiling pattern.
    ``'glyph'``
        The procedure that draws one glyph of a Type 3 font.
    ``'softmask'``
        The transparency group of a soft mask in a graphics state parameter
        dictionary.
    """

    content: Object
    """The content stream: the page's dictionary for ``'page'``, else a stream.

    Either can be given to :func:`pikepdf.parse_content_stream`.
    """

    resources: Dictionary | None
    """The resource dictionary that names in the content stream refer to.

    This is the stream's own ``/Resources`` if it has one. A page may inherit
    its resources from the page tree, and the glyph procedures of a Type 3
    font use the font's resources. A form XObject or Type 3 font with no
    resources of its own, as early versions of PDF allowed, uses those of the
    page it is used on. ``None`` if there are none or they are not a
    dictionary.

    The dictionary is the one in the file and is often shared between scopes.
    """

    page: Page | None
    """The page that this scope was found on.

    When pages share a scope, this is the first of them. ``None`` if the
    search started from a form XObject rather than a page.
    """


def kinds_mask(kinds: Iterable[str] | str | None) -> int:
    """Check a ``kinds`` argument and convert it to the form C++ takes."""
    if kinds is None:
        return _ALL_KINDS
    if isinstance(kinds, str):
        kinds = (kinds,)
    mask = 0
    for kind in kinds:
        if not isinstance(kind, str):
            raise TypeError(f"content scope kinds are strings, not {kind!r}")
        if kind not in _KIND_BITS:
            raise ValueError(
                f"unknown content scope kind {kind!r}; "
                f"the kinds are {', '.join(_KIND_BITS)}"
            )
        mask |= _KIND_BITS[kind]
    return mask


def page_scopes(page: Page, mask: int, walk: _ContentScopeWalk) -> list[ContentScope]:
    """Find the content scopes of one page that *walk* has not yet reported."""
    owner = None if isinstance(page.obj, Stream) else page
    return [
        ContentScope(_KIND_NAMES[bit], content, resources, owner)
        for bit, content, resources in walk.walk(page, mask)
    ]


def pdf_scopes(pages: Iterable[Page], mask: int) -> Iterator[ContentScope]:
    """Report the content scopes of each page, one page at a time."""
    walk = _ContentScopeWalk()
    for page in pages:
        yield from page_scopes(page, mask, walk)
