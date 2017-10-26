# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
#
# Copyright (C) 2017, James R. Barlow (https://github.com/jbarlow83/)

from . import qpdf
import collections.abc

# This is a repository of half-baked ideas, mainly an effort to automatically
# unbox QPDFObjectHandle to equivalent Python types
# I'm unconvinced that's a good idea in the first place, convenient as it is,
# as it involves roundtripping a lot of data and boxed types can usually have
# a nice repr() or str() or whatever. Also here is a half-baked syntax
# checker.

class PdfObject:
    @classmethod
    def specialize(cls, obj):
        if obj.type_code == qpdf.ObjectType.ot_integer:
            return obj.as_int()  # Integer is transparent

        elif obj.type_code == qpdf.ObjectType.ot_boolean:
            return obj.as_bool()

        elif obj.type_code == qpdf.ObjectType.ot_null:
            return None

        elif obj.type_code == qpdf.ObjectType.ot_dictionary:
            if obj.get("/Type") == qpdf.Object.Name("/Page"):
                return PdfPage(obj)
            return PdfDict(obj)

        return PdfObject(obj)


    def __init__(self, obj):
        self.obj = obj

    def __repr__(self):
        return self.__class__.__name__ + "(" + repr(self.obj) + ")"


class PdfName(PdfObject):
    def __init__(self, name):
        if isinstance(name, str):
            if not name.startswith('/'):
                raise ValueError("Name must start with /")
            self.obj = qpdf.Object.Name(name)
            return

        elif isinstance(name, qpdf.Object):
            self.obj = name
            return

        elif isinstance(name, PdfName):
            self.obj = name.obj
            return

        raise NotImplemented()

    def __str__(self):
        return ""


class PdfDict(PdfObject, collections.abc.MutableMapping):
    def __init__(self, *args, **kwargs):
        if len(args) == 0:
            d = {}
            # Translate PdfDict(Type='/Page', Parent=None...) to
            # a valid name dictionary
            for key, val in kwargs:
                if key[0].isupper():
                    d['/' + key] = val
                else:
                    raise ValueError("Invalid PDF dict /Name")

            self.obj = qpdf.Object.Dictionary(d)
            return

        elif isinstance(args[0], qpdf.Object):
            self.obj = args[0]
            return

        elif isinstance(args[0], collections.abc.Mapping):
            self.obj = qpdf.Object.Dictionary(args[0])
            return

        raise NotImplemented()

    def __contains__(self, key):
        return self.obj.__contains__(key)

    def __len__(self):
        return self.obj.__len__()

    def __iter__(self):
        return iter(self.obj.as_dict())

    def __getitem__(self, key):
        return PdfObject.specialize(self.obj.__getitem__(key))

    def __setitem__(self, key, val):
        return self.obj.__setitem__(key, val)

    def __delitem__(self, key):
        return self.obj.__delitem__(key)

    def keys(self):
        return self.obj.keys()

    def items(self):
        return self.obj.as_dict().items()

    def values(self):
        return self.obj.as_dict().values()


class RestrictedDict(PdfDict):
    REQUIRED_KEYS = frozenset()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def validate(self):
        self_keys = set(self.keys())
        missing_keys = self_keys - self.REQUIRED_KEYS
        if missing_keys:
            return False
        return True


class PdfPage(RestrictedDict):
    REQUIRED_KEYS = frozenset(['/Type', '/Parent', '/Resources', '/MediaBox'])

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def merge(self, other):
        if not isinstance(other, PdfPage):
            raise ValueError("PdfPage can only be merged with another PdfPage")


class Resources(PdfDict):
    pass








class Pdf(qpdf.QPDF):

    @property
    def root(self):
        return PdfObject.specialize(super().root)

    @property
    def trailer(self):
        return super().trailer
