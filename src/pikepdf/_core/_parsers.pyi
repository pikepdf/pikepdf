# SPDX-FileCopyrightText: 2022 James R. Barlow
# SPDX-License-Identifier: MPL-2.0

# Type stubs for the bindings in src/core/parsers.cpp.
# See pikepdf/_core/__init__.pyi for how this stub package is laid out.

# pylint: disable=no-method-argument,unused-argument,no-self-use,too-many-public-methods
# ruff: noqa: D418
# mypy: disable-error-code="misc"

from __future__ import annotations

from collections.abc import Iterable
from decimal import Decimal
from typing import TYPE_CHECKING, Any, overload

from pikepdf._core._object import Object, _ObjectList
from pikepdf._core._object_construct import Array, Operator

if TYPE_CHECKING:
    from pikepdf.models.image import PdfInlineImage

class ContentStreamInstruction:
    """Represents one complete instruction inside a content stream."""

    @overload
    def __init__(self, operands: _ObjectList, operator: Operator, /) -> None: ...
    @overload
    def __init__(
        self,
        operands: Iterable[Object | int | float | Decimal | Array],
        operator: Operator,
        /,
    ) -> None: ...
    @overload
    def __init__(self, other: ContentStreamInstruction, /) -> None: ...
    def __init__(self, *args) -> None: ...
    @property
    def operands(self) -> _ObjectList:
        """The operands (parameters) supplied to the operator."""
    @property
    def operator(self) -> Operator:
        """The operator used in this instruction."""
    def __getitem__(self, index: int, /) -> _ObjectList | Operator:
        """``[0]`` returns the operands, and ``[1]`` returns the operator."""
    def __len__(self) -> int: ...

class ContentStreamInlineImage:
    """Represents an instruction to draw an inline image.

    pikepdf consolidates the BI-ID-EI sequence of operators, as appears in a PDF to
    declare an inline image, and replaces them with a single virtual content stream
    instruction with the operator "INLINE IMAGE".
    """

    @property
    def operands(self) -> _ObjectList:
        """Returns a list of operands, whose sole entry is the inline image."""
    @property
    def operator(self) -> Operator:
        """Always return the fictitious operator 'INLINE IMAGE'."""
    def __getitem__(self, index: int, /) -> _ObjectList | Operator: ...
    def __len__(self) -> int: ...
    @property
    def iimage(self) -> PdfInlineImage:
        """Returns the inline image itself."""

class _ContentChecker:
    """Parse and check content streams for :mod:`pikepdf.pdfa`.

    The checks that need no graphics state run here, so that most operands
    never become Python objects: operand types against the operator table,
    the operator allowlist, and the implementation limits on operands.
    Everything else is handed back to Python as an event.

    Args:
        operators: The operand signature of each permitted operator, as in
            ``pikepdf.pdfa._content.OPERATORS``; ``'*'`` accepts any.
        handlers: The operators Python handles, each mapped to whether its
            handler reads the operands.
        min_integer: Least permitted integer.
        max_integer: Greatest permitted integer.
        max_real: Greatest permitted magnitude of a real.
        min_real: Least permitted magnitude of a nonzero real, or 0.
        max_string: Longest permitted string, in bytes.
        max_name: Longest permitted name, in bytes after ``#xx`` expansion,
            without the slash; also applies to dictionary keys.
        max_array: Most elements permitted in an array, or None.
        max_dict: Most entries permitted in a dictionary, or None.
        max_nesting: Deepest permitted nesting of arrays and dictionaries.
    """

    def __init__(
        self,
        operators: dict[str, str],
        handlers: dict[str, bool],
        *,
        min_integer: int,
        max_integer: int,
        max_real: float,
        min_real: float,
        max_string: int,
        max_name: int,
        max_array: int | None,
        max_dict: int | None,
        max_nesting: int,
    ) -> None: ...
    def check(self, stream: Object) -> tuple[list[tuple[Any, ...]], int]:
        """Parse and check a content stream.

        The stream is grouped into instructions exactly as
        :func:`pikepdf.parse_content_stream` does, raising the same errors
        and warnings.

        Returns:
            The events, in stream order, and the number of instructions
            (counting each inline image as one). Each event is a tuple
            whose first two items are its kind and the index of its
            instruction:

            - ``('limits', index, operand)``: an operand that may break an
              implementation limit, for Python to check. Deferred
              operands are a superset of those that break a limit.
            - ``('undefined', index, operator)``: an operator not in the
              table.
            - ``('operands', index, operator, operands)``: operands that do
              not match the operator's signature.
            - ``('op', index, operator, operands)``: an operator Python
              handles; *operands* is empty if its handler does not read
              them.
            - ``('inline', index, instruction)``: an inline image, as a
              :class:`ContentStreamInlineImage`.

            An instruction may have several ``'limits'`` events, before its
            other event, if any.
        """

def _scan_raw_content(data: bytes, inline_images: list[bytes]) -> list[tuple[str, str]]:
    """Check hex strings in raw content stream bytes.

    Tokenizes just enough to find hex strings: literal strings, comments
    and inline image data are skipped.

    Args:
        data: The raw (decoded) content stream.
        inline_images: The raw data of each inline image, in order, as the
            content parser found it.

    Returns:
        (clause, message) for each problem: ``6.1.6-1`` for a hex string with
        an odd number of digits, ``6.1.6-2`` for one with characters that are
        not hex digits, and ``inline-image`` if the inline images cannot be
        matched with those the parser found.
    """
