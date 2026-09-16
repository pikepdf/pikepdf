# SPDX-FileCopyrightText: 2022 James R. Barlow
# SPDX-License-Identifier: MPL-2.0

# Type stubs for the bindings in src/core/transcoding.cpp.
# See pikepdf/_core/__init__.pyi for how this stub package is laid out.

# pylint: disable=no-method-argument,unused-argument,no-self-use,too-many-public-methods
# ruff: noqa: D418
# mypy: disable-error-code="misc"

from __future__ import annotations

def _unpack_subbyte_2bit(
    in_: bytes | memoryview, out: bytearray | memoryview, scale: int
) -> None:
    """Unpack 2-bit values into bytes scaled by 'scale' (0..85).

    Output buffer must be at least 4x the input length.
    """

def _unpack_subbyte_4bit(
    in_: bytes | memoryview, out: bytearray | memoryview, scale: int
) -> None:
    """Unpack 4-bit values into bytes scaled by 'scale' (0..17).

    Output buffer must be at least 2x the input length.
    """
