# SPDX-FileCopyrightText: 2022 James R. Barlow
# SPDX-License-Identifier: MPL-2.0

# Type stubs for the bindings in src/core/tokenfilter.cpp.
# See pikepdf/_core/__init__.pyi for how this stub package is laid out.

# pylint: disable=no-method-argument,unused-argument,no-self-use,too-many-public-methods
# ruff: noqa: D418
# mypy: disable-error-code="misc"

from __future__ import annotations

from collections.abc import Iterable
from enum import Enum
from typing import Any

class TokenType(Enum):
    """Type of a token that appeared in a PDF content stream.

    When filtering content streams, each token is labeled according to the role
    in plays.
    """

    array_close: ...
    """The token data represents the end of an array."""
    array_open: ...
    """The token data represents the start of an array."""
    bad: ...
    """An invalid token."""
    bool: ...
    """The token data represents an integer, real number, null or boolean,
        respectively."""
    brace_close: ...
    """The token data represents the end of a brace."""
    brace_open: ...
    """The token data represents the start of a brace."""
    comment: ...
    """Signifies a comment that appears in the content stream."""
    dict_close: ...
    """The token data represents the end of a dictionary."""
    dict_open: ...
    """The token data represents the start of a dictionary."""
    eof: ...
    """Denotes the end of the tokens in this content stream."""
    inline_image: ...
    """An inline image in the content stream. The whole inline image is
        represented by the single token."""
    integer: ...
    """The token data represents an integer."""
    name_: ...
    """The token is the name (pikepdf.Name) of an object. In practice, these
        are among the most interesting tokens.

        .. versionchanged:: 3.0
            In versions older than 3.0, ``.name`` was used instead. This interfered
            with semantics of the ``Enum`` object, so this was fixed.
    """
    null: ...
    """The token data represents a null."""
    real: ...
    """The token data represents a real number."""
    space: ...
    """Whitespace within the content stream."""
    string: ...
    """The token data represents a string. The encoding is unclear and situational."""
    word: ...
    """Otherwise uncategorized bytes are returned as ``word`` tokens. PDF
        operators are words."""

class Token:
    def __init__(self, arg0: TokenType, arg1: bytes, /) -> None: ...
    def __eq__(self, other: Any, /) -> bool: ...
    @property
    def error_msg(self) -> str:
        """If the token is an error, this returns the error message."""
    @property
    def raw_value(self) -> bytes:
        """The binary representation of a token."""
    @property
    def type_(self) -> TokenType:
        """Returns the type of token."""
    @property
    def value(self) -> str:
        """Interprets the token as a string."""

class _QPDFTokenFilter: ...

class TokenFilter(_QPDFTokenFilter):
    def __init__(self) -> None: ...
    def handle_token(self, token: Token = ...) -> None | Token | Iterable[Token]:
        """Handle a :class:`pikepdf.Token`.

        This is an abstract method that must be defined in a subclass
        of ``TokenFilter``. The method will be called for each token.
        The implementation may return either ``None`` to discard the
        token, the original token to include it, a new token, or an
        iterable containing zero or more tokens. An implementation may
        also buffer tokens and release them in groups (for example, it
        could collect an entire PDF command with all of its operands,
        and then return all of it).

        The final token will always be a token of type ``TokenType.eof``,
        (unless an exception is raised).

        If this method raises an exception, the exception will be
        caught by C++, consumed, and replaced with a less informative
        exception. Use :meth:`pikepdf.Pdf.get_warnings` to view the
        original.
        """
