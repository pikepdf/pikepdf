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
from typing import TYPE_CHECKING, overload

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
