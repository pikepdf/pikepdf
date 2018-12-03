# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
#
# Copyright (C) 2018, James R. Barlow (https://github.com/jbarlow83/)

from functools import wraps
from operator import itemgetter
from datetime import datetime

# Repeat this to avoid circular from top package's pikepdf.__version__
from pkg_resources import (
    get_distribution as _get_distribution,
    DistributionNotFound
)
try:
    pikepdf_version = _get_distribution(__name__).version
except DistributionNotFound:
    pikepdf_version = "unknown version"

import libxmp
from libxmp import XMPMeta, XMPError
from libxmp.consts import (
    XMP_NS_DC, XMP_NS_PDF, XMP_NS_PDFA_ID, XMP_NS_PDFX_ID, XMP_NS_RDF, XMP_NS_XMP
)
from libxmp.utils import object_to_dict

from .. import Stream, Name


def refresh(fn):
    @wraps(fn)
    def wrapper(self, *args, **kwargs):
        if not self._records:
            self._refresh()
        return fn(self, *args, **kwargs)
    return wrapper

class PdfMetadata:
    """Read and edit the XMP metadata associated with a PDF

    Requires/relies on python-xmp-toolkit and libexempi.

    To update metadata, use a with block.

    .. code-block:: python

        with pdf.open_metadata() as records:
            records['dc:title'] = 'New Title'

    See Also:
        :meth:`pikepdf.Pdf.open_metadata`

    """

    def __init__(self, pdf, pikepdf_mark=True, sync_docinfo=True):
        self._pdf = pdf
        self._xmp = None
        self._records = {}
        self._flags = {}
        self.mark = pikepdf_mark
        self.sync_docinfo = sync_docinfo

    def _create_xmp(self):
        self._xmp = XMPMeta()
        DEFAULT_NAMESPACES = [
            (XMP_NS_DC, 'dc'),
            (XMP_NS_PDF, 'pdf'),
            (XMP_NS_RDF, 'rdf'),
            (XMP_NS_XMP, 'xmp'),
        ]
        for uri, prefix in DEFAULT_NAMESPACES:
            self._xmp.register_namespace(uri, prefix)

    def _refresh(self):
        try:
        data = self._pdf.Root.Metadata.read_bytes()
        except AttributeError:
            self._create_xmp()
        else:
        self._xmp = XMPMeta(xmp_str=data.decode('utf-8'))
        xmpdict = object_to_dict(self._xmp)

        # Sort to ensure all members of a compound object immediately follow
        # the compound. Not sure if libxmp guarantees order.
        for uri, records in sorted(xmpdict.items(), key=itemgetter(0)):
            for key, val, flags in records:
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
        """Update the PDF's DocumentInfo dictionary to match XMP metadata

        The standard mapping is described here:
            https://www.pdfa.org/pdfa-metadata-xmp-rdf-dublin-core/
        """
        MAPPING = {
            (XMP_NS_DC, 'description'): Name.Subject,
            (XMP_NS_DC, 'title'): Name.Title,
            (XMP_NS_PDF, 'Keywords'): Name.Keywords,
            (XMP_NS_PDF, 'Producer'): Name.Producer,
            (XMP_NS_XMP, 'CreateDate'): Name.CreationDate,
            (XMP_NS_XMP, 'CreatorTool'): Name.Creator,
            (XMP_NS_XMP, 'ModifyDate'): Name.ModDate,
        }
        for xmpparts, docinfo_name in MAPPING.items():
            schema, element = xmpparts
            value = self._xmp.get_property(schema, element)
            self._pdf.docinfo[docinfo_name] = value
        dc_prefix = self._xmp.get_prefix_for_namespace(XMP_NS_DC)
        dc_creator = self._records.get(dc_prefix + 'creator', None)
        if dc_creator:
            if isinstance(dc_creator, str):
                creators = dc_creator
            else:
                creators = '; '.join(dc_creator)
            self._pdf.docinfo[Name.Authors] = creators

    def _get_uri(self, key):
        prefix = key.split(':', maxsplit=1)[0]
        return self._xmp.get_namespace_for_prefix(prefix)

    def _apply_changes(self):
        for key, val in self._records.items():
            val_type = self._expected_type(key, val)
            if not isinstance(val, val_type):
                raise TypeError("{}: expected type {}".format(key, repr(val_type)))
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
                XMP_NS_XMP, 'MetadataDate', datetime.now()
            )
            self._xmp.set_property(
                XMP_NS_PDF, 'Producer', 'pikepdf ' + pikepdf_version
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

    @property
    @refresh
    def pdfa_status(self):
        """Returns the PDF/A conformance level claimed by this PDF, or False

        A PDF may claim to PDF/A compliant without this being true. Use an
        independent verifier such as veraPDF to test if a PDF is truly
        conformant.

        Returns:
            str: The conformance level of the PDF/A, or an empty string if the
            PDF does not claim PDF/A conformance. Possible valid values
            are: 1A, 1B, 2A, 2B, 2U, 3A, 3B, 3U.
        """
        pdfaid = self._xmp.get_prefix_for_namespace(XMP_NS_PDFA_ID)
        key_part = pdfaid + 'part'
        key_conformance = pdfaid + 'conformance'
        try:
            return self._records[key_part] + self._records[key_conformance]
        except KeyError:
            return ''

    @property
    @refresh
    def pdfx_status(self):
        """Returns the PDF/X conformance level claimed by this PDF, or False

        A PDF may claim to PDF/X compliant without this being true. Use an
        independent verifier such as veraPDF to test if a PDF is truly
        conformant.

        Returns:
            str: The conformance level of the PDF/X, or an empty string if the
            PDF does not claim PDF/X conformance.
        """
        pdfxid = self._xmp.get_prefix_for_namespace(XMP_NS_PDFX_ID)
        pdfx_version = pdfxid + 'GTS_PDFXVersion'
        try:
            return self._records[pdfx_version]
        except KeyError:
            return ''
