# SPDX-FileCopyrightText: 2022 James R. Barlow
# SPDX-License-Identifier: MPL-2.0

# Type stubs for the bindings in src/core/namepath.cpp.
# See pikepdf/_core/__init__.pyi for how this stub package is laid out.

# pylint: disable=no-method-argument,unused-argument,no-self-use,too-many-public-methods
# ruff: noqa: D418
# mypy: disable-error-code="misc"

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from pikepdf._core._object_construct import Name

class _NamePath(NamePath):
    """Path for accessing nested Dictionary/Stream values.

    This is the C++ backing class for pikepdf.NamePath.
    Use pikepdf.NamePath instead of this class directly.
    """

    def __init__(self, *args: str | int) -> None: ...
    def __call__(self, arg: str | int, /) -> _NamePath: ...
    def __getitem__(self, index: int, /) -> _NamePath: ...
    def __getattr__(self, name: str, /) -> _NamePath: ...
    def __repr__(self) -> str: ...
    def __len__(self) -> int: ...
    def __bool__(self) -> bool: ...
    def __eq__(self, other: object, /) -> bool: ...
    def __hash__(self) -> int: ...
    def __iter__(self) -> Iterator[str | int]: ...
    def _append_name(self, name: str) -> _NamePath: ...
    def _append_index(self, index: int) -> _NamePath: ...
    def _format_path(self, up_to: int) -> str: ...
    def _is_empty(self) -> bool: ...

# Exceptions

class _NamePathMeta(type):
    def __getattr__(cls, name: str) -> _NamePath: ...
    def __getitem__(cls, key: str | int | Name) -> _NamePath: ...
    def __call__(cls, *args: str | int | Name) -> _NamePath: ...
    def __instancecheck__(cls, instance: Any) -> bool: ...
    def __subclasscheck__(cls, sub: type) -> bool: ...

class NamePath(metaclass=_NamePathMeta):
    """Path for accessing nested Dictionary/Stream values.

    NamePath provides ergonomic access to deeply nested PDF structures with a
    single access operation and helpful error messages when keys are not found.

    Usage examples::

        # Shorthand syntax - most common
        obj[NamePath.Resources.Font.F1]

        # With array indices
        obj[NamePath.Pages.Kids[0].MediaBox]

        # Chained access - supports non Python-identifier names
        NamePath['/A']('/B').C[0]  # equivalent to NamePath.A.B.C[0]

        # Alternate syntax to support lists
        obj[NamePath(Name.Resources, Name.Font)]

        # Using string objects
        obj[NamePath('/Resources', '/Weird-Name')]

        # Empty path returns the object itself
        obj[NamePath()]

        # Setting nested values (all parents must exist)
        obj[NamePath.Root.Info.Title] = pikepdf.String("Test")

        # With default value
        obj.get(NamePath.Root.Metadata, None)

    When a key is not found, the KeyError message identifies the exact failure
    point, e.g.: "Key /C not found; traversed NamePath.A.B"

    .. versionadded:: 10.1
    """

    def __new__(cls, *args: str | int | Name) -> _NamePath: ...

    # Instances are _NamePath, which derives from this class; these dunders are
    # declared here so that a parameter annotated NamePath supports them.
    def __iter__(self) -> Iterator[str | int]: ...
    def __len__(self) -> int: ...
    def __bool__(self) -> bool: ...
