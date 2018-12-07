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
import xml.etree.ElementTree as ET

from libxmp import XMPMeta, XMPIterator
from .. import Stream, Name, String


XMP_NS_DC = "http://purl.org/dc/elements/1.1/"
XMP_NS_PDF = "http://ns.adobe.com/pdf/1.3/"
XMP_NS_PDFA_ID = "http://www.aiim.org/pdfa/ns/id/"
XMP_NS_PDFX_ID = "http://www.npes.org/pdfx/ns/id/"
XMP_NS_RDF = "http://www.w3.org/1999/02/22-rdf-syntax-ns#"
XMP_NS_XMP = "http://ns.adobe.com/xap/1.0/"

DEFAULT_NAMESPACES = [
    (XMP_NS_DC, 'dc'),
    (XMP_NS_PDF, 'pdf'),
    (XMP_NS_RDF, 'rdf'),
    (XMP_NS_XMP, 'xmp'),
]


# Repeat this to avoid circular from top package's pikepdf.__version__
try:
    pikepdf_version = _get_distribution(__name__).version
except DistributionNotFound:
    pikepdf_version = "unknown version"


def encode_pdf_date(d: datetime) -> str:
    """Encode Python datetime object as PDF date string

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


def decode_pdf_date(s: str) -> datetime:
    """Decode a pdfmark date to a Python datetime object

    A pdfmark date is a string in a paritcular format. See the pdfmark
    Reference for the specification.
    """
    if isinstance(s, String):
        s = str(s)
    if s.startswith('D:'):
        s = s[2:]

    # Literal Z00'00', is incorrect but found in the wild,
    # probably made by OS X Quartz -- standardize
    if s.endswith("Z00'00'"):
        s = s.replace("Z00'00'", '+0000')
    elif s.endswith('Z'):
        s = s.replace('Z', '+0000')
    s = s.replace("'", "")  # Remove apos from PDF time strings
    return datetime.strptime(s, r'%Y%m%d%H%M%S%z')


class AuthorConverter:
    @staticmethod
    def xmp_from_docinfo(docinfo_val):
        return str(docinfo_val)

    @staticmethod
    def docinfo_from_xmp(xmp_val):
        if isinstance(xmp_val, str):
            return xmp_val
        else:
            return '; '.join(xmp_val)


class DateConverter:
    @staticmethod
    def xmp_from_docinfo(docinfo_val):
        return decode_pdf_date(docinfo_val).isoformat()

    @staticmethod
    def docinfo_from_xmp(xmp_val):
        dateobj = datetime.fromisoformat(xmp_val)
        return encode_pdf_date(dateobj)


def ensure_loaded(fn):
    @wraps(fn)
    def wrapper(self, *args, **kwargs):
        if not self._xmp:
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

    MAPPING = [
        (XMP_NS_DC, 'creator', Name.Authors, AuthorConverter),
        (XMP_NS_DC, 'description', Name.Subject, None),
        (XMP_NS_DC, 'title', Name.Title, None),
        (XMP_NS_PDF, 'Keywords', Name.Keywords, None),
        (XMP_NS_PDF, 'Producer', Name.Producer, None),
        (XMP_NS_XMP, 'CreateDate', Name.CreationDate, DateConverter),
        (XMP_NS_XMP, 'CreatorTool', Name.Creator, None),
        (XMP_NS_XMP, 'ModifyDate', Name.ModDate, DateConverter),
    ]

    def __init__(self, pdf, pikepdf_mark=True, sync_docinfo=True):
        self._pdf = pdf
        self._xmp = None
        self._ns = {prefix: uri for uri, prefix in DEFAULT_NAMESPACES}
        self._records = {}
        self._flags = {}
        self.mark = pikepdf_mark
        self.sync_docinfo = sync_docinfo
        self._updating = False
        self._deleted = set()
        self._changed = set()

    def _create_xmp(self):
        self._xmp = XMPMeta()

    def load_from_docinfo(self, docinfo):
        """Populate the XMP metadata object with DocumentInfo

        A few entries in the deprecated DocumentInfo dictionary are considered
        approximately equivalent to certain XMP records. This method copies
        those entries into the XMP metadata.
        """
        for uri, shortkey, docinfo_name, converter in self.MAPPING:
            prefix = self._xmp.get_prefix_for_namespace(uri)
            key = prefix + shortkey
            val = docinfo.get(docinfo_name)
            if val is None:
                continue
            val = str(val)
            if converter:
                val = converter.xmp_from_docinfo(val)
            self[key] = val

    def _load(self):
        try:
            data = self._pdf.Root.Metadata.read_bytes()
        except AttributeError:
            self._create_xmp()
        else:
            self._xmp = ET.fromstring(data)

    @ensure_loaded
    def __enter__(self):
        self._updating = True
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        try:
            if exc_type is not None:
                return
            self._apply_changes()
        finally:
            self._records = {}
            self._deleted = set()
            self._changed = set()
            self._updating = False

    def _update_docinfo(self):
        """Update the PDF's DocumentInfo dictionary to match XMP metadata

        The standard mapping is described here:
            https://www.pdfa.org/pdfa-metadata-xmp-rdf-dublin-core/
        """

        for schema, element, docinfo_name, converter in self.MAPPING:
            prefix = self._xmp.get_prefix_for_namespace(schema)
            try:
                value = self._records[prefix + element]
            except KeyError:
                if docinfo_name in self._pdf.docinfo:
                    del self._pdf.docinfo[docinfo_name]
                continue
            if converter:
                value = converter.docinfo_from_xmp(value)
            self._pdf.docinfo[docinfo_name] = value

    def _get_uri(self, key):
        prefix = key.split(':', maxsplit=1)[0]
        return self._xmp.get_namespace_for_prefix(prefix)

    def _apply_changes(self):
        if self.mark:
            self._xmp.set_property_datetime(
                XMP_NS_XMP, 'MetadataDate', datetime.now()
            )
            self._xmp.set_property(
                XMP_NS_PDF, 'Producer', 'pikepdf ' + pikepdf_version
            )

        data = self._xmp.serialize_to_unicode()
        self._pdf.Root.Metadata = Stream(self._pdf, data.encode('utf-8'))
        self._pdf.Root.Metadata[Name.Type] = Name.Metadata
        self._pdf.Root.Metadata[Name.Subtype] = Name.XML
        if self.sync_docinfo:
            self._update_docinfo()

    @ensure_loaded
    def __contains__(self, key):
        return bool(self._xmp.find('.//{}'.format(key), self._ns))

    @ensure_loaded
    def __len__(self):
        return len(self._xmp.find('.//{}'.format(key), self._ns))

    @ensure_loaded
    def __getitem__(self, key):
        element = self._xmp.find('.//{}'.format(key), self._ns)
        has_children = bool(element.find('.//', self._ns))
        if has_children:
            raise NotImplementedError()
        return element.tag

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

    @ensure_loaded
    def __setitem__(self, key, val):
        if not self._updating:
            raise RuntimeError("Metadata not opened for editing, use with block")
        if not isinstance(val, self._expected_type(key, val)):
            raise TypeError("Invalid type set for metadata {}".format(key))
        self._changed.add(key)
        self._records[key] = val

    @ensure_loaded
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
