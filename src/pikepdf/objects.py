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
from ._qpdf import Operator


class _ObjectMeta(type):
    """Supports instance checking"""

    def __instancecheck__(cls, instance):
        if type(instance) != Object:
            return False
        return cls.object_type == instance._type_code


class _NameObjectMeta(_ObjectMeta):
    """Supports usage pikepdf.Name.Whatever -> Name('/Whatever')"""

    def __getattr__(self, attr):
        return Name('/' + attr)

    def __setattr__(self, name, value):
        raise TypeError("Attributes may not be set on pikepdf.Name")

    def __getitem__(self, item):
        if item.startswith('/'):
            item = item[1:]
        raise TypeError(
            (
                "pikepdf.Name is not subscriptable. You probably meant:\n"
                "    pikepdf.Name.{}\n"
                "or\n"
                "    pikepdf.Name('/{}')\n"
            ).format(item, item)
        )


class Name(metaclass=_NameObjectMeta):
    """Constructs a PDF Name object

    Names can be constructed with two notations:

        1. ``Name.Resources``

        2. ``Name('/Resources')``

    The two are semantically equivalent. The former is preferred for names
    that are normally expected to be in a PDF. The latter is preferred for
    dynamic names and attributes.
    """
    object_type = ObjectType.name

    def __new__(cls, name):
        # QPDF_Name::unparse ensures that names are always saved in a UTF-8
        # compatible way, so we only need to guard the input.
        if isinstance(name, bytes):
            raise TypeError("Name should be str")
        return _qpdf._new_name(name)


class String(metaclass=_ObjectMeta):
    """Constructs a PDF String object"""
    object_type = ObjectType.string

    def __new__(cls, s):
        """
        Args:
            s (str or bytes): The string to use. String will be encoded for
                PDF, bytes will be constructed without encoding.

        Returns:
            pikepdf.Object
        """
        if isinstance(s, bytes):
            return _qpdf._new_string(s)
        return _qpdf._new_string_utf8(s)


class Array(metaclass=_ObjectMeta):
    """Constructs a PDF Array object"""
    object_type = ObjectType.array

    def __new__(cls, a=[]):
        """
        Args:
            a (iterable): A list of objects. All objects must be either
                `pikepdf.Object` or convertible to `pikepdf.Object`.

        Returns:
            pikepdf.Object
        """

        if isinstance(a, (str, bytes)):
            raise TypeError('Strings cannot be converted to arrays of chars')
        return _qpdf._new_array(a)


class Dictionary(metaclass=_ObjectMeta):
    """Constructs a PDF Dictionary object"""
    object_type = ObjectType.dictionary

    def __new__(cls, d=None, **kwargs):
        """
        Constructs a PDF Dictionary from either a Python ``dict`` or keyword
        arguments.

        These two examples are equivalent:

        .. code-block:: python

            pikepdf.Dictionary({'/NameOne': 1, '/NameTwo': 'Two'})

            pikepdf.Dictionary(NameOne=1, NameTwo='Two')

        In either case, the keys must be strings, and the strings
        correspond to the desired Names in the PDF Dictionary. The values
        must all be convertible to `pikepdf.Object`.

        Returns:
            pikepdf.Object
        """
        if kwargs and d is not None:
            raise ValueError('Unsupported parameters')
        if kwargs:
            # Add leading slash
            # Allows Dictionary(MediaBox=(0,0,1,1), Type=Name('/Page')...
            return _qpdf._new_dictionary(
                {('/' + k) : v for k, v in kwargs.items()})
        if not d:
            d = {}
        return _qpdf._new_dictionary(d)


class Stream(metaclass=_ObjectMeta):
    """Constructs a PDF Stream object"""
    object_type = ObjectType.stream

    def __new__(cls, owner, obj):
        """
        Args:
            owner (pikepdf.Pdf): The Pdf to which this stream shall be attached.
            obj (bytes or list): If ``bytes``, the data bytes for the stream.
                If ``list``, a list of ``(operands, operator)`` tuples such
                as returned by :func:`pikepdf.parse_content_stream`.

        Returns:
            pikepdf.Object
        """
        return _qpdf._new_stream(owner, obj)
