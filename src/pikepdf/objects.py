# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
#
# Copyright (C) 2017, James R. Barlow (https://github.com/jbarlow83/)

"""Provide classes to stand in for PDF objects

The purpose of these is to provide nice-looking classes to allow explicit
construction of PDF objects and more pythonic idioms and facilitate discovery
by documentation generators and linters.

It's also a place to narrow the scope of input types to those more easily
converted to C++.

There is some deliberate "smoke and mirrors" here: all of the objects are truly
instances of ``pikepdf.Object``, which is a variant container object. The
``__new__`` constructs a ``pikepdf.Object`` in each case, and the rest of the
class definition is present as an aide for code introspection.
"""

# pylint: disable=unused-import, abstract-method

from typing import TYPE_CHECKING, Iterable, Optional, Union

from . import _qpdf
from ._qpdf import Object, ObjectType

if TYPE_CHECKING:
    from pikepdf import Pdf

# By default pikepdf.Object will identify itself as pikepdf._qpdf.Object
# Here we change the module to discourage people from using that internal name
# Instead it will become pikepdf.objects.Object
Object.__module__ = __name__
ObjectType.__module__ = __name__


# type(Object) is the metaclass that pybind11 defines; we wish to extend that
# pylint cannot see the C++ metaclass definition is thoroughly confused.
# pylint: disable=invalid-metaclass


class _ObjectMeta(type(Object)):  # type: ignore
    """Supports instance checking"""

    def __instancecheck__(self, instance):
        # Note: since this class is a metaclass, self is a class object
        if type(instance) != Object:
            return False
        return self.object_type == instance._type_code


class _NameObjectMeta(_ObjectMeta):
    """Supports usage pikepdf.Name.Whatever -> Name('/Whatever')"""

    def __getattr__(self, attr):
        if attr.startswith('_'):
            return _ObjectMeta.__getattr__(attr)
        return Name('/' + attr)

    def __setattr__(self, attr, value):
        if attr.startswith('_'):
            return _ObjectMeta.__setattr__(attr, value)
        raise TypeError("Attributes may not be set on pikepdf.Name")

    def __getitem__(self, item):
        if item.startswith('/'):
            item = item[1:]
        raise TypeError(
            (
                "pikepdf.Name is not subscriptable. You probably meant:\n"
                "    pikepdf.Name.{item}\n"
                "or\n"
                "    pikepdf.Name('/{item}')\n"
            ).format(item=item)
        )


class Name(Object, metaclass=_NameObjectMeta):
    """Constructs a PDF Name object

    Names can be constructed with two notations:

        1. ``Name.Resources``

        2. ``Name('/Resources')``

    The two are semantically equivalent. The former is preferred for names
    that are normally expected to be in a PDF. The latter is preferred for
    dynamic names and attributes.
    """

    object_type = ObjectType.name

    def __new__(cls, name: str):
        # QPDF_Name::unparse ensures that names are always saved in a UTF-8
        # compatible way, so we only need to guard the input.
        if isinstance(name, bytes):
            raise TypeError("Name should be str")
        return _qpdf._new_name(name)


class Operator(Object, metaclass=_ObjectMeta):
    """Constructs an operator for use in a content stream.

    An Operator is one of a limited set of commands that can appear in PDF content
    streams (roughly the mini-language that draws objects, lines and text on a
    virtual PDF canvas). The commands :func:`parse_content_stream` and
    :func:`unparse_content_stream` create and expect Operators respectively, along
    with their operands.

    pikepdf uses the special Operator "INLINE IMAGE" to denote an inline image
    in a content stream.
    """

    object_type = ObjectType.operator

    def __new__(cls, name: str):
        return _qpdf._new_operator(name)


class String(Object, metaclass=_ObjectMeta):
    """Constructs a PDF String object"""

    object_type = ObjectType.string

    def __new__(cls, s: Union[str, bytes]):
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


class Array(Object, metaclass=_ObjectMeta):
    """Constructs a PDF Array object"""

    object_type = ObjectType.array

    def __new__(cls, a: Optional[Iterable] = None):
        """
        Args:
            a (iterable): An iterable of objects. All objects must be either
                `pikepdf.Object` or convertible to `pikepdf.Object`.

        Returns:
            pikepdf.Object
        """

        if isinstance(a, (str, bytes)):
            raise TypeError('Strings cannot be converted to arrays of chars')
        if a is None:
            a = []
        return _qpdf._new_array(a)


class Dictionary(Object, metaclass=_ObjectMeta):
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
            return _qpdf._new_dictionary({('/' + k): v for k, v in kwargs.items()})
        if not d:
            d = {}
        if d and any(not key.startswith('/') for key in d.keys()):
            raise ValueError("Dictionary created from strings must begin with '/'")
        return _qpdf._new_dictionary(d)


class Stream(Object, metaclass=_ObjectMeta):
    """Constructs a PDF Stream object"""

    object_type = ObjectType.stream

    def __new__(cls, owner: 'Pdf', obj: bytes):
        """
        Args:
            owner (pikepdf.Pdf): The Pdf to which this stream shall be attached.
            obj (bytes): The data bytes for the stream.

        Returns:
            pikepdf.Object
        """
        return _qpdf._new_stream(owner, obj)
