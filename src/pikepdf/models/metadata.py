# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
#
# Copyright (C) 2018, James R. Barlow (https://github.com/jbarlow83/)

from functools import wraps

import libxmp

from libxmp.utils import object_to_dict
from libxmp import XMPMeta

from .. import Stream


def refresh(fn):
    @wraps(fn)
    def wrapper(self, *args, **kwargs):
        if not self._records:
            self._refresh()
        return fn(self, *args, **kwargs)
    return wrapper


class PdfMetadata:
    def __init__(self, pdf):
        self.uris = {}
        self._pdf = pdf
        self._xmp = None
        self._records = {}
        self._flags = {}

    def _refresh(self):
        data = self._pdf.Root.Metadata.read_bytes()
        self._xmp = XMPMeta(xmp_str=data.decode('utf-8'))
        xmpdict = object_to_dict(self._xmp)

        for uri, records in xmpdict.items():
            for key, val, flags in records:
                self.uris[key] = uri
                self._flags[key] = flags
                if val == '':
                    # Compound object
                    self._records[key] = self._expected_type(key)()
                elif '[' in key:
                    # Member of compound object
                    compound_key, rest = key.split('[', maxsplit=1)
                    member_key = rest.split(']', maxsplit=1)[0]
                    compound = self._records[compound_key]
                    if isinstance(compound, list):
                        compound.append(val)
                    elif isinstance(compound, set):
                        compound.add(val)
                    elif isinstance(compound, dict):
                        compound[member_key] = val
                else:
                    # Scalar object
                    self._records[key] = val
        return

    @refresh
    def __enter__(self):
        return self._records

    def _expected_type(self, key):
        if self._flags[key]['VALUE_IS_ARRAY']:
            if self._flags[key]['ARRAY_IS_ORDERED']:
                return list
            return set
        if self._flags[key]['VALUE_IS_STRUCT']:
            return dict
        return str

    @staticmethod
    def _property_options(flags):
        return {('prop_' + k.lower()): v for k, v in flags.items()}

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None:
            return
        self._apply_changes()

    def _apply_changes(self):
        for key, val in self._records.items():
            if not isinstance(val, self._expected_type(key)):
                raise TypeError(key)  # Kinda

            uri = self.uris[key]
            if isinstance(val, (list, set, dict)):
                self._xmp.delete_property(uri, key)
                array_options = self._property_options(self._flags[key])
                for item in val:
                    self._xmp.append_array_item(uri, key, item, array_options=array_options)
            else:
                self._xmp.set_property(uri, key, val)

        data = self._xmp.serialize_to_unicode()
        self._pdf.Root.Metadata = Stream(self._pdf, data.encode('utf-8'))
        self._records = {}

    @refresh
    def __contains__(self, key):
        return key in self._records

    @refresh
    def __getitem__(self, key):
        return self._records[key]

    @refresh
    def __iter__(self):
        return iter(self._records)
