# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
#
# Copyright (C) 2018, James R. Barlow (https://github.com/jbarlow83/)

from functools import wraps
from operator import itemgetter
from datetime import datetime

import libxmp

from libxmp.utils import object_to_dict
from libxmp import XMPMeta

from .. import __version__
from .. import Stream, Name

NAMESPACES = {
    'dc': "http://purl.org/dc/elements/1.1/",
    'pdf': "http://ns.adobe.com/pdf/1.3/",
    'xmp': "http://ns.adobe.com/xap/1.0/",
}

def refresh(fn):
    @wraps(fn)
    def wrapper(self, *args, **kwargs):
        if not self._records:
            self._refresh()
        return fn(self, *args, **kwargs)
    return wrapper

class PdfMetadata:
    def __init__(self, pdf, pikepdf_mark=True, sync_docinfo=True):
        self.uris = {}
        self._pdf = pdf
        self._xmp = None
        self._records = {}
        self._flags = {}
        self.mark = pikepdf_mark
        self.sync_docinfo = sync_docinfo

    def _refresh(self):
        data = self._pdf.Root.Metadata.read_bytes()
        self._xmp = XMPMeta(xmp_str=data.decode('utf-8'))
        xmpdict = object_to_dict(self._xmp)

        # Sort to ensure all members of a compound object immediately follow
        # the compound. Not sure if libxmp guarantees order.
        for uri, records in sorted(xmpdict.items(), key=itemgetter(0)):
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

    def _expected_type(self, key, val=None):
        if key not in self._flags:
            if isinstance(val, (list, set, dict, str)):
                return type(val)
            raise TypeError(val)
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

    def _update_docinfo(self):
        MAPPING = {
            (NAMESPACES['dc'], 'title'): Name.Title,
            (NAMESPACES['dc'], 'subject'): Name.Subject,
            (NAMESPACES['dc'], 'date'): Name.CreationDate,
            (NAMESPACES['pdf'], 'Keywords'): Name.Keywords,
            (NAMESPACES['pdf'], 'Producer'): Name.Producer,
        }
        for xmpparts, docinfo_name in MAPPING.items():
            schema, element = xmpparts
            value = self._xmp.get_property(schema, element)
            self._pdf.docinfo[docinfo_name] = value

        if 'dc:creator' in self._records:
            creators = '; '.join(self._records['dc:creator'])
            self._pdf.docinfo[Name.Authors] = creators

    def _get_uri(self, key):
        if key in self.uris:
            return self.uris[key]
        prefix = key.split(':', maxsplit=1)[0]
        return self._xmp.get_namespace_for_prefix(prefix)

    def _apply_changes(self):
        for key, val in self._records.items():
            if not isinstance(val, self._expected_type(key, val)):
                raise TypeError(key)  # Kinda

            uri = self._get_uri(key)
            if isinstance(val, (list, set, dict)):
                self._xmp.delete_property(uri, key)
                array_options = self._property_options(self._flags[key])
                for item in val:
                    self._xmp.append_array_item(uri, key, item, array_options=array_options)
            else:
                self._xmp.set_property(uri, key, val)

        if self.mark:
            self._xmp.set_property_datetime(
                NAMESPACES['xmp'], 'MetadataDate', datetime.now()
            )
            self._xmp.set_property(
                NAMESPACES['pdf'], 'Producer', 'pikepdf ' + __version__
            )

        data = self._xmp.serialize_to_unicode()
        self._pdf.Root.Metadata = Stream(self._pdf, data.encode('utf-8'))
        if self.sync_docinfo:
            self._update_docinfo()
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
