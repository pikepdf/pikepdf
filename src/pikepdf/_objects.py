# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
#
# Copyright (C) 2017, James R. Barlow (https://github.com/jbarlow83/)

"""Provide classes to stand in for PDF objects

The purpose of these is to provide nice-looking classes to allow explicit
construction of PDF objects and more pythonic idioms and facilitate discovery
by documentation generators.

It's also a place to narrow the scope of input types to those more easily
converted to C++.

In reality all of these return objects of class pikepdf.Object or rather
QPDFObjectHandle which is a generic type.

"""

from . import _qpdf
from ._qpdf import Object, ObjectType

# pylint: disable=unused-import
from ._qpdf import Operator, _Null as Null


class _ObjectMeta(type):
    "Supports instance checking"

    def __instancecheck__(cls, instance):
        if type(instance) != Object:
            return False
        return cls.object_type == instance._type_code


class Name(metaclass=_ObjectMeta):
    object_type = ObjectType.name

    def __new__(cls, name):
        # QPDF_Name::unparse ensures that names are always saved in a UTF-8
        # compatible way, so we only need to guard the input.
        if isinstance(name, bytes):
            raise TypeError("Name should be str")
        return _qpdf._new_name(name)


class String(metaclass=_ObjectMeta):
    object_type = ObjectType.string

    def __new__(cls, s):
        if isinstance(s, bytes):
            return _qpdf._new_string(s)
        try:
            ascii_ = s.encode('ascii')
            return _qpdf._new_string(ascii_)
        except UnicodeEncodeError:
            utf16 = b'\xfe\xff' + s.encode('utf-16be')
            return _qpdf._new_string(utf16)


class Array(metaclass=_ObjectMeta):
    object_type = ObjectType.array

    def __new__(cls, a):
        if isinstance(a, (str, bytes)):
            raise TypeError('Strings cannot be converted to arrays of chars')
        return _qpdf._new_array(a)


class Dictionary(metaclass=_ObjectMeta):
    object_type = ObjectType.dictionary

    def __new__(cls, d):
        return _qpdf._new_dictionary(d)


class Stream(metaclass=_ObjectMeta):
    object_type = ObjectType.stream

    def __new__(cls, owner, obj):
        return _qpdf._new_stream(owner, obj)
