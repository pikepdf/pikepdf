# SPDX-FileCopyrightText: 2022 James R. Barlow
# SPDX-License-Identifier: MPL-2.0

# Type variables and aliases shared across this stub package.
#
# Nothing here exists at runtime. The aliases whose meaning depends on the
# conversion mode of the owning document live here so that explicit- versus
# implicit-mode typing can be refined in one place.
#
# See pikepdf/_core/__init__.pyi for how this stub package is laid out.

# pylint: disable=no-method-argument,unused-argument,no-self-use,too-many-public-methods
# ruff: noqa: D418
# mypy: disable-error-code="misc"

from __future__ import annotations

from decimal import Decimal
from typing import TypeAlias, TypeVar

from pikepdf._core._object import Object

T = TypeVar('T')
TObj = TypeVar('TObj', bound='Object')
Numeric = TypeVar('Numeric', int, float, Decimal)

# Operand and result types of Integer/Real arithmetic and comparisons.
_Number: TypeAlias = 'int | float | Decimal | Object'
# Arithmetic always yields a native Python number, never a pikepdf object.
_NumberResult: TypeAlias = 'int | float | Decimal'
