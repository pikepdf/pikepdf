# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
#
# Copyright (C) 2018, James R. Barlow (https://github.com/jbarlow83/)

from collections.abc import MutableMapping
from datetime import datetime
from functools import wraps
from itertools import groupby
from pkg_resources import (
    get_distribution as _get_distribution,
    DistributionNotFound
)
from warnings import warn

from libxmp import XMPMeta, XMPIterator
from libxmp.consts import (
    XMP_NS_DC, XMP_NS_PDF, XMP_NS_PDFA_ID, XMP_NS_PDFX_ID, XMP_NS_RDF, XMP_NS_XMP
)

from .. import Stream, Name

# Repeat this to avoid circular from top package's pikepdf.__version__
try:
    pikepdf_version = _get_distribution(__name__).version
except DistributionNotFound:
    pikepdf_version = "unknown version"


def encode_pdf_date(d: datetime) -> str:
    """
    Encode Python datetime object as PDF date string

    From Adobe pdfmark manual:
    (D:YYYYMMDDHHmmSSOHH'mm')
    D: is an optional prefix. YYYY is the year. All fields after the year are
    optional. MM is the month (01-12), DD is the day (01-31), HH is the
    hour (00-23), mm are the minutes (00-59), and SS are the seconds
    (00-59). The remainder of the string defines the relation of local
    time to GMT. O is either + for a positive difference (local time is
    later than GMT) or - (minus) for a negative difference. HH' is the
    absolute value of the offset from GMT in hours, and mm' is the
    absolute value of the offset in minutes. If no GMT information is
    specified, the relation between the specified time and GMT is
    considered unknown. Regardless of whether or not GMT
    information is specified, the remainder of the string should specify
    the local time.
    """

    pdfmark_date_fmt = r'%Y%m%d%H%M%S'
    s = d.strftime(pdfmark_date_fmt)

    tz = d.strftime('%z')
    if tz == '':
        # Ghostscript <= 9.23 handles missing timezones incorrectly, so if
        # timezone is missing, move it into GMT.
        # https://bugs.ghostscript.com/show_bug.cgi?id=699182
        s += "+00'00'"
    else:
        sign, tz_hours, tz_mins = tz[0], tz[1:3], tz[3:5]
        s += "{}{}'{}'".format(sign, tz_hours, tz_mins)
    return s


def ensure_loaded(fn):
    @wraps(fn)
    def wrapper(self, *args, **kwargs):
        if not self._records:
            self._load()
        return fn(self, *args, **kwargs)
    return wrapper


class PdfMetadata(MutableMapping):
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
        self._updating = False
        self._deleted = set()
        self._changed = set()

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

    def _load(self):
        try:
            data = self._pdf.Root.Metadata.read_bytes()
        except AttributeError:
            self._create_xmp()
        else:
            self._xmp = XMPMeta(xmp_str=data.decode('utf-8'))

        def xmp_group_key(k):
            _schema, prop_name, _value, _flags = k
            return prop_name.split('[', maxsplit=1)[0]

        def xmp_item_index(k):
            _schema, prop_name, _value, _flags = k
            _compound_key, rest = prop_name.split('[', maxsplit=1)
            index = rest.split(']', maxsplit=1)[0]
            return index

        self._deleted = set()
        self._changed = set()
        xmpiter = XMPIterator(self._xmp)
        for prop_name_group, elements in groupby(xmpiter, key=xmp_group_key):
            elements = list(elements)
            parent = next(el for el in elements if el[1] == prop_name_group)
            elements.remove(parent)
            parent_value = parent[2]
            parent_flags = parent[3]

            if parent_flags['VALUE_IS_ARRAY']:
                if parent_flags['ARRAY_IS_ALTTEXT']:
                    record = []
                    for _index, subitems in groupby(elements, key=xmp_item_index):
                        subitems = list(subitems)
                        qualifier = next(el for el in subitems if el[3]['IS_QUALIFIER'])
                        text = next(el for el in subitems if el[3]['HAS_QUALIFIERS'])
                        if qualifier != 'x-default':
                            warn(
                                ("XMP metadata key {} has alternate language text. "
                                "This is not fully supported. If modified they "
                                "will not be preserved.").format(prop_name_group)
                            )
                        record = text[2]
                elif parent_flags['ARRAY_IS_ORDERED']:
                    record = [el[2] for el in elements]
                else:
                    record = set(el[2] for el in elements)
            elif parent_flags['VALUE_IS_STRUCT']:
                raise NotImplementedError()
            elif parent_value == '':
                continue
            else:
                record = parent[2]

            self._flags[prop_name_group] = parent_flags
            self._records[prop_name_group] = record
        return

    @ensure_loaded
    def __enter__(self):
        self._updating = True
        return self

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
        def author_converter(authors):
            if isinstance(authors, str):
                return authors
            else:
                return '; '.join(authors)

        def date_converter(date_str):
            dateobj = datetime.fromisoformat(date_str)
            return encode_pdf_date(dateobj)

        MAPPING = [
            (XMP_NS_DC, 'creator', Name.Authors, author_converter),
            (XMP_NS_DC, 'description', Name.Subject, None),
            (XMP_NS_DC, 'title', Name.Title, None),
            (XMP_NS_PDF, 'Keywords', Name.Keywords, None),
            (XMP_NS_PDF, 'Producer', Name.Producer, None),
            (XMP_NS_XMP, 'CreateDate', Name.CreationDate, date_converter),
            (XMP_NS_XMP, 'CreatorTool', Name.Creator, None),
            (XMP_NS_XMP, 'ModifyDate', Name.ModDate, date_converter),
        ]
        for schema, element, docinfo_name, converter in MAPPING:
            prefix = self._xmp.get_prefix_for_namespace(schema)
            try:
                value = self._records[prefix + element]
            except KeyError:
                if docinfo_name in self._pdf.docinfo:
                    del self._pdf.docinfo[docinfo_name]
                continue
            if converter:
                value = converter(value)
            self._pdf.docinfo[docinfo_name] = value

    def _get_uri(self, key):
        prefix = key.split(':', maxsplit=1)[0]
        return self._xmp.get_namespace_for_prefix(prefix)

    def _apply_changes(self):
        for key in self._deleted:
            uri = self._get_uri(key)
            self._xmp.delete_property(uri, key)

        for key in self._changed:
            val = self._records[key]
            uri = self._get_uri(key)
            if isinstance(val, (list, set, dict)):
                self._xmp.delete_property(uri, key)
                array_options = self._property_options(self._flags[key])
                for item in val:
                    self._xmp.append_array_item(uri, key, item, array_options=array_options)
            elif self._flags[key]['ARRAY_IS_ALTTEXT']:
                self._xmp.delete_property(uri, key)
                self._xmp.set_property(uri, key, val)
            else:
                self._xmp.set_property(uri, key, val)

        if self.mark:
            self._xmp.set_property_datetime(
                XMP_NS_XMP, 'MetadataDate', datetime.now()
            )
            self._xmp.set_property(
                XMP_NS_PDF, 'Producer', 'pikepdf ' + pikepdf_version
            )

        print(self._xmp)
        data = self._xmp.serialize_to_unicode()
        self._pdf.Root.Metadata = Stream(self._pdf, data.encode('utf-8'))
        if self.sync_docinfo:
            self._update_docinfo()
        self._records = {}
        self._deleted = []
        self._updating = False

    @ensure_loaded
    def __contains__(self, key):
        return key in self._records

    @ensure_loaded
    def __len__(self):
        return len(self._records)

    @ensure_loaded
    def __getitem__(self, key):
        return self._records[key]

    @ensure_loaded
    def __iter__(self):
        return iter(self._records)

    def _expected_type(self, key, val=None):
        if key not in self._flags:
            if isinstance(val, (list, set, dict, str)):
                return type(val)
            raise TypeError(val)
        if self._flags[key]['ARRAY_IS_ALTTEXT']:
            return str
        if self._flags[key]['VALUE_IS_ARRAY']:
            if self._flags[key]['ARRAY_IS_ORDERED']:
                return list
            return set
        if self._flags[key]['VALUE_IS_STRUCT']:
            return dict
        return str

    def __setitem__(self, key, val):
        if not self._updating:
            raise RuntimeError("Metadata not opened for editing, use with block")
        if not isinstance(val, self._expected_type(key, val)):
            raise TypeError("Invalid type set for metadata {}".format(key))
        self._changed.add(key)
        self._records[key] = val

    def __delitem__(self, key):
        if not self._updating:
            raise RuntimeError("Metadata not opened for editing, use with block")
        del self._records[key]
        self._deleted.add(key)

    @property
    @ensure_loaded
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
    @ensure_loaded
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
