# SPDX-FileCopyrightText: 2022 James R. Barlow
# SPDX-License-Identifier: MPL-2.0

"""Provide classes to stand in for PDF objects.

The purpose of these is to provide nice-looking classes to allow explicit
construction of PDF objects and more pythonic idioms and facilitate discovery
by documentation generators and linters.

There is some deliberate "smoke and mirrors" here: all of the objects are truly
instances of ``pikepdf.Object``, which is a variant container object. The
construction machinery and metaclasses are implemented in C++ (``_core``); this
module re-exports them and applies cosmetic module names.
"""

from __future__ import annotations

from pikepdf._core import (
    Array,
    Boolean,
    Dictionary,
    Integer,
    Name,
    NamePath,
    Object,
    ObjectType,
    Operator,
    Real,
    Stream,
    String,
)

__all__ = [
    'Array',
    'Boolean',
    'Dictionary',
    'Integer',
    'Name',
    'NamePath',
    'Object',
    'ObjectType',
    'Operator',
    'Real',
    'Stream',
    'String',
]

# By default these identify themselves as pikepdf._core.<Name>; rename them to
# discourage use of the internal module path. Name's metaclass guards attribute
# assignment, but dunder names (starting with '_') are permitted, so __module__
# can be set here.
for _t in (
    Object,
    ObjectType,
    Name,
    Operator,
    String,
    Array,
    Dictionary,
    Stream,
    Integer,
    Boolean,
    Real,
    NamePath,
):
    _t.__module__ = __name__
