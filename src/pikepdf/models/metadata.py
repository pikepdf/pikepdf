# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
#
# Copyright (C) 2018, James R. Barlow (https://github.com/jbarlow83/)

import logging
import re
import sys
from collections import namedtuple
from collections.abc import Iterable, MutableMapping, Set
from datetime import datetime
from functools import wraps
from io import BytesIO
from warnings import warn

from lxml import etree
from lxml.etree import QName, XMLParser, XMLSyntaxError, parse

from .. import Name, Stream, String
from .. import __version__ as pikepdf_version

XMP_NS_DC = "http://purl.org/dc/elements/1.1/"
XMP_NS_PDF = "http://ns.adobe.com/pdf/1.3/"
XMP_NS_PDFA_ID = "http://www.aiim.org/pdfa/ns/id/"
XMP_NS_PDFX_ID = "http://www.npes.org/pdfx/ns/id/"
XMP_NS_PHOTOSHOP = "http://ns.adobe.com/photoshop/1.0/"
XMP_NS_PRISM2 = "http://prismstandard.org/namespaces/basic/2.0/"
XMP_NS_PRISM3 = "http://prismstandard.org/namespaces/basic/3.0/"
XMP_NS_RDF = "http://www.w3.org/1999/02/22-rdf-syntax-ns#"
XMP_NS_XMP = "http://ns.adobe.com/xap/1.0/"
XMP_NS_XMP_MM = "http://ns.adobe.com/xap/1.0/mm/"
XMP_NS_XMP_RIGHTS = "http://ns.adobe.com/xap/1.0/rights/"

DEFAULT_NAMESPACES = [
    ('adobe:ns:meta/', 'x'),
    (XMP_NS_DC, 'dc'),
    (XMP_NS_PDF, 'pdf'),
    (XMP_NS_PDFA_ID, 'pdfaid'),
    (XMP_NS_PDFX_ID, 'pdfxid'),
    (XMP_NS_PHOTOSHOP, 'photoshop'),
    (XMP_NS_PRISM2, 'prism2'),
    (XMP_NS_PRISM3, 'prism3'),
    (XMP_NS_RDF, 'rdf'),
    (XMP_NS_XMP, 'xmp'),
    (XMP_NS_XMP_MM, 'xmpMM'),
    (XMP_NS_XMP_RIGHTS, 'xmpRights'),
]

for _uri, _prefix in DEFAULT_NAMESPACES:
    etree.register_namespace(_prefix, _uri)

# This one should not be registered
XMP_NS_XML = "http://www.w3.org/XML/1998/namespace"

XPACKET_BEGIN = b"""<?xpacket begin="\xef\xbb\xbf" id="W5M0MpCehiHzreSzNTczkc9d"?>\n"""

XMP_EMPTY = b"""<x:xmpmeta xmlns:x="adobe:ns:meta/" x:xmptk="pikepdf">
 <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">
 </rdf:RDF>
</x:xmpmeta>
"""

XPACKET_END = b"""\n<?xpacket end="w"?>\n"""

XmpContainer = namedtuple('XmpContainer', ['rdf_type', 'py_type', 'insert_fn'])

log = logging.getLogger(__name__)


class NeverRaise(Exception):
    """An exception that is never raised"""

    pass  # pylint: disable=unnecessary-pass


class AltList(list):
    pass


XMP_CONTAINERS = [
    XmpContainer('Alt', AltList, AltList.append),
    XmpContainer('Bag', set, set.add),
    XmpContainer('Seq', list, list.append),
]

LANG_ALTS = frozenset(
    [
        str(QName(XMP_NS_DC, 'title')),
        str(QName(XMP_NS_DC, 'description')),
        str(QName(XMP_NS_DC, 'rights')),
        str(QName(XMP_NS_XMP_RIGHTS, 'UsageTerms')),
    ]
)

# These are the illegal characters in XML 1.0. (XML 1.1 is a bit more permissive,
# but we'll be strict to ensure wider compatibility.)
re_xml_illegal_chars = re.compile(
    r"(?u)[^\x09\x0A\x0D\x20-\U0000D7FF\U0000E000-\U0000FFFD\U00010000-\U0010FFFF]"
)
re_xml_illegal_bytes = re.compile(
    br"[^\x09\x0A\x0D\x20-\xFF]|&#0;"
    # br"&#(?:[0-9]|0[0-9]|1[0-9]|2[0-9]|3[0-1]|x[0-9A-Fa-f]|x0[0-9A-Fa-f]|x1[0-9A-Fa-f]);"
)


def _clean(s, joiner='; '):
    """Ensure an object can safely be inserted in a XML tag body.

    If we still have a non-str object at this point, the best option is to
    join it, because it's apparently calling for a new node in a place that
    isn't allowed in the spec or not supported.
    """
    if not isinstance(s, str) and isinstance(s, Iterable):
        warn("Merging elements of {}".format(s))
        if isinstance(s, Set):
            s = joiner.join(sorted(s))
        else:
            s = joiner.join(s)
    return re_xml_illegal_chars.sub('', s)


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

    # The formatting of %Y is not consistent as described in
    # https://bugs.python.org/issue13305 and underspecification in libc.
    # So explicitly format the year with leading zeros
    s = "{:04d}".format(d.year)
    s += d.strftime(r'%m%d%H%M%S')
    tz = d.strftime('%z')
    if tz:
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
    try:
        return datetime.strptime(s, r'%Y%m%d%H%M%S%z')
    except ValueError:
        return datetime.strptime(s, r'%Y%m%d%H%M%S')


class AuthorConverter:
    @staticmethod
    def xmp_from_docinfo(docinfo_val):
        return [docinfo_val]

    @staticmethod
    def docinfo_from_xmp(xmp_val):
        if isinstance(xmp_val, str):
            return xmp_val
        elif xmp_val is None or xmp_val == [None]:
            return None
        else:
            return '; '.join(xmp_val)


if sys.version_info < (3, 7):

    def fromisoformat(datestr):
        # strptime %z can't parse a timezone with punctuation
        if re.search(r'[+-]\d{2}[-:]\d{2}$', datestr):
            datestr = datestr[:-3] + datestr[-2:]
        try:
            return datetime.strptime(datestr, "%Y-%m-%dT%H:%M:%S%z")
        except ValueError:
            return datetime.strptime(datestr, "%Y-%m-%dT%H:%M:%S")


else:
    fromisoformat = datetime.fromisoformat


class DateConverter:
    @staticmethod
    def xmp_from_docinfo(docinfo_val):
        if docinfo_val == '':
            return ''
        return decode_pdf_date(docinfo_val).isoformat()

    @staticmethod
    def docinfo_from_xmp(xmp_val):
        if xmp_val.endswith('Z'):
            xmp_val = xmp_val[:-1] + '+00:00'
        dateobj = fromisoformat(xmp_val)
        return encode_pdf_date(dateobj)


def ensure_loaded(fn):
    @wraps(fn)
    def wrapper(self, *args, **kwargs):
        if not self._xmp:
            self._load()
        return fn(self, *args, **kwargs)

    return wrapper


class PdfMetadata(MutableMapping):
    """Read and edit the metadata associated with a PDF

    The PDF specification contain two types of metadata, the newer XMP
    (Extensible Metadata Platform, XML-based) and older DocumentInformation
    dictionary. The PDF 2.0 specification removes the DocumentInformation
    dictionary.

    This primarily works with XMP metadata, but includes methods to generate
    XMP from DocumentInformation and will also coordinate updates to
    DocumentInformation so that the two are kept consistent.

    XMP metadata fields may be accessed using the full XML namespace URI or
    the short name. For example ``metadata['dc:description']``
    and ``metadata['{http://purl.org/dc/elements/1.1/}description']``
    both refer to the same field. Several common XML namespaces are registered
    automatically.

    See the XMP specification for details of allowable fields.

    To update metadata, use a with block.

    Example:

        >>> with pdf.open_metadata() as records:
                records['dc:title'] = 'New Title'

    See Also:
        :meth:`pikepdf.Pdf.open_metadata`
    """

    DOCINFO_MAPPING = [
        (XMP_NS_DC, 'creator', Name.Author, AuthorConverter),
        (XMP_NS_DC, 'description', Name.Subject, None),
        (XMP_NS_DC, 'title', Name.Title, None),
        (XMP_NS_PDF, 'Keywords', Name.Keywords, None),
        (XMP_NS_PDF, 'Producer', Name.Producer, None),
        (XMP_NS_XMP, 'CreateDate', Name.CreationDate, DateConverter),
        (XMP_NS_XMP, 'CreatorTool', Name.Creator, None),
        (XMP_NS_XMP, 'ModifyDate', Name.ModDate, DateConverter),
    ]

    NS = {prefix: uri for uri, prefix in DEFAULT_NAMESPACES}
    REVERSE_NS = {uri: prefix for uri, prefix in DEFAULT_NAMESPACES}

    def __init__(
        self, pdf, pikepdf_mark=True, sync_docinfo=True, overwrite_invalid_xml=True
    ):
        self._pdf = pdf
        self._xmp = None
        self.mark = pikepdf_mark
        self.sync_docinfo = sync_docinfo
        self._updating = False
        self.overwrite_invalid_xml = overwrite_invalid_xml

    def load_from_docinfo(self, docinfo, delete_missing=False, raise_failure=False):
        """Populate the XMP metadata object with DocumentInfo

        Arguments:
            docinfo: a DocumentInfo, e.g pdf.docinfo
            delete_missing: if the entry is not DocumentInfo, delete the equivalent
                from XMP
            raise_failure: if True, raise any failure to convert docinfo;
                otherwise warn and continue

        A few entries in the deprecated DocumentInfo dictionary are considered
        approximately equivalent to certain XMP records. This method copies
        those entries into the XMP metadata.
        """
        for uri, shortkey, docinfo_name, converter in self.DOCINFO_MAPPING:
            qname = QName(uri, shortkey)
            # docinfo might be a dict or pikepdf.Dictionary, so lookup keys
            # by str(Name)
            val = docinfo.get(str(docinfo_name))
            if val is None:
                if delete_missing and qname in self:
                    del self[qname]
                continue
            try:
                val = str(val)
                if converter:
                    val = converter.xmp_from_docinfo(val)
                if not val:
                    continue
                self[qname] = val
            except (ValueError, AttributeError) as e:
                msg = "The metadata field {} could not be copied to XMP".format(
                    docinfo_name
                )
                if raise_failure:
                    raise ValueError(msg) from e
                else:
                    warn(msg)
        valid_docinfo_names = set(
            str(docinfo_name) for _, _, docinfo_name, _ in self.DOCINFO_MAPPING
        )
        extra_docinfo_names = set(str(k) for k in docinfo.keys()) - valid_docinfo_names
        for extra in extra_docinfo_names:
            msg = (
                "The metadata field {} with value '{}' has no XMP equivalent, "
                "so it was discarded"
            ).format(extra, repr(docinfo.get(extra)))
            if raise_failure:
                raise ValueError(msg)
            else:
                warn(msg)

    def _load(self):
        try:
            data = self._pdf.Root.Metadata.read_bytes()
        except AttributeError:
            data = XMP_EMPTY
        self._load_from(data)

    def _load_from(self, data):
        if data.strip() == b'':
            data = XMP_EMPTY  # on some platforms lxml chokes on empty documents

        def basic_parser(xml):
            return parse(BytesIO(xml))

        def strip_illegal_bytes_parser(xml):
            return parse(BytesIO(re_xml_illegal_bytes.sub(b'', xml)))

        def recovery_parser(xml):
            parser = XMLParser(recover=True)
            return parse(BytesIO(xml), parser)

        def replace_with_empty_xmp(_xml=None):
            log.warning("Error occurred parsing XMP, replacing with empty XMP.")
            return basic_parser(XMP_EMPTY)

        if self.overwrite_invalid_xml:
            parsers = [
                basic_parser,
                strip_illegal_bytes_parser,
                recovery_parser,
                replace_with_empty_xmp,
            ]
        else:
            parsers = [basic_parser]

        for parser in parsers:
            try:
                self._xmp = parser(data)
            except (XMLSyntaxError if self.overwrite_invalid_xml else NeverRaise) as e:
                if str(e).startswith("Start tag expected, '<' not found") or str(
                    e
                ).startswith("Document is empty"):
                    self._xmp = replace_with_empty_xmp()
                    break
            else:
                break

        try:
            pis = self._xmp.xpath('/processing-instruction()')
            for pi in pis:
                etree.strip_tags(self._xmp, pi.tag)
            self._get_rdf_root()
        except (Exception if self.overwrite_invalid_xml else NeverRaise) as e:
            log.warning("Error occurred parsing XMP", exc_info=e)
            self._xmp = replace_with_empty_xmp()
        return

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
            self._updating = False

    def _update_docinfo(self):
        """Update the PDF's DocumentInfo dictionary to match XMP metadata

        The standard mapping is described here:
            https://www.pdfa.org/pdfa-metadata-xmp-rdf-dublin-core/
        """
        # Touch object to ensure it exists
        self._pdf.docinfo  # pylint: disable=pointless-statement
        for uri, element, docinfo_name, converter in self.DOCINFO_MAPPING:
            qname = QName(uri, element)
            try:
                value = self[qname]
            except KeyError:
                if docinfo_name in self._pdf.docinfo:
                    del self._pdf.docinfo[docinfo_name]
                continue
            if converter:
                try:
                    value = converter.docinfo_from_xmp(value)
                except ValueError:
                    warn(
                        "The DocumentInfo field {} could not be updated from XMP".format(
                            docinfo_name
                        )
                    )
                    value = None
                except Exception as e:
                    raise ValueError(
                        "An error occurred while updating DocumentInfo field {} from XMP {} with value {}".format(
                            docinfo_name, qname, value
                        )
                    ) from e
            if value is None:
                if docinfo_name in self._pdf.docinfo:
                    del self._pdf.docinfo[docinfo_name]
                continue
            value = _clean(value)
            try:
                # Try to save pure ASCII
                self._pdf.docinfo[docinfo_name] = value.encode('ascii')
            except UnicodeEncodeError:
                # qpdf will serialize this as a UTF-16 with BOM string
                self._pdf.docinfo[docinfo_name] = value

    def _get_xml_bytes(self, xpacket=True):
        data = BytesIO()
        if xpacket:
            data.write(XPACKET_BEGIN)
        self._xmp.write(data, encoding='utf-8', pretty_print=True)
        if xpacket:
            data.write(XPACKET_END)
        data.seek(0)
        xml_bytes = data.read()
        return xml_bytes

    def _apply_changes(self):
        """Serialize our changes back to the PDF in memory

        Depending how we are initialized, leave our metadata mark and producer.
        """
        if self.mark:
            self[QName(XMP_NS_XMP, 'MetadataDate')] = datetime.now().isoformat()
            self[QName(XMP_NS_PDF, 'Producer')] = 'pikepdf ' + pikepdf_version
        xml = self._get_xml_bytes()
        self._pdf.Root.Metadata = Stream(self._pdf, xml)
        self._pdf.Root.Metadata[Name.Type] = Name.Metadata
        self._pdf.Root.Metadata[Name.Subtype] = Name.XML
        if self.sync_docinfo:
            self._update_docinfo()

    def _qname(self, name):
        """Convert name to an XML QName

        e.g. pdf:Producer -> {http://ns.adobe.com/pdf/1.3/}Producer
        """
        if isinstance(name, QName):
            return name
        if not isinstance(name, str):
            raise TypeError("{} must be str".format(name))
        if name == '':
            return name
        if name.startswith('{'):
            return name
        prefix, tag = name.split(':', maxsplit=1)
        uri = self.NS[prefix]
        return QName(uri, tag)

    def _prefix_from_uri(self, uriname):
        """Given a fully qualified XML name, find a prefix

        e.g. {http://ns.adobe.com/pdf/1.3/}Producer -> pdf:Producer
        """
        uripart, tag = uriname.split('}', maxsplit=1)
        uri = uripart.replace('{', '')
        return self.REVERSE_NS[uri] + ':' + tag

    def _get_subelements(self, node):
        """Gather the sub-elements attached to a node

        Gather rdf:Bag and and rdf:Seq into set and list respectively. For
        alternate languages values, take the first language only for
        simplicity.
        """
        items = node.find('rdf:Alt', self.NS)
        if items is not None:
            try:
                return items[0].text
            except IndexError:
                return ''

        for xmlcontainer, container, insertfn in XMP_CONTAINERS:
            items = node.find('rdf:{}'.format(xmlcontainer), self.NS)
            if items is None:
                continue
            result = container()
            for item in items:
                insertfn(result, item.text)
            return result
        return ''

    def _get_rdf_root(self):
        rdf = self._xmp.find('.//rdf:RDF', self.NS)
        if rdf is None:
            rdf = self._xmp.getroot()
            if not rdf.tag == '{http://www.w3.org/1999/02/22-rdf-syntax-ns#}RDF':
                raise ValueError("Metadata seems to be XML but not XMP")
        return rdf

    def _get_elements(self, name=''):
        """Get elements from XMP

        Core routine to find elements matching name within the XMP and yield
        them.

        For XMP spec 7.9.2.2, rdf:Description with property attributes,
        we yield the node which will have the desired as one of its attributes.
        qname is returned so that the node.attrib can be used to locate the
        source.

        For XMP spec 7.5, simple valued XMP properties, we yield the node,
        None, and the value. For structure or array valued properties we gather
        the elements. We ignore qualifiers.

        Args:
            name (str): a prefixed name or QName to look for within the
                data section of the XMP; looks for all data keys if omitted

        Yields:
            tuple: (node, qname_attrib, value, parent_node)

        """
        qname = self._qname(name)
        rdf = self._get_rdf_root()
        for rdfdesc in rdf.findall('rdf:Description[@rdf:about=""]', self.NS):
            if qname and qname in rdfdesc.keys():
                yield (rdfdesc, qname, rdfdesc.get(qname), rdf)
            elif not qname:
                for k, v in rdfdesc.items():
                    if v:
                        yield (rdfdesc, k, v, rdf)
            xpath = qname if name else '*'
            for node in rdfdesc.findall(xpath, self.NS):
                if node.text and node.text.strip():
                    yield (node, None, node.text, rdfdesc)
                    continue
                values = self._get_subelements(node)
                yield (node, None, values, rdfdesc)

    def _get_element_values(self, name=''):
        yield from (v[2] for v in self._get_elements(name))

    @ensure_loaded
    def __contains__(self, key):
        try:
            return any(self._get_element_values(key))
        except KeyError:
            return False

    @ensure_loaded
    def __getitem__(self, key):
        try:
            return next(self._get_element_values(key))
        except StopIteration:
            raise KeyError(key) from None

    @ensure_loaded
    def __iter__(self):
        for node, attrib, _val, _parents in self._get_elements():
            if attrib:
                yield attrib
            else:
                yield node.tag

    @ensure_loaded
    def __len__(self):
        return len(list(iter(self)))

    @ensure_loaded
    def __setitem__(self, key, val):
        if not self._updating:
            raise RuntimeError("Metadata not opened for editing, use with block")

        def add_array(node, items):
            rdf_type = next(
                c.rdf_type for c in XMP_CONTAINERS if isinstance(items, c.py_type)
            )
            seq = etree.SubElement(node, QName(XMP_NS_RDF, rdf_type))
            if rdf_type == 'Alt':
                attrib = {QName(XMP_NS_XML, 'lang'): 'x-default'}
            else:
                attrib = None
            for item in items:
                el = etree.SubElement(seq, QName(XMP_NS_RDF, 'li'), attrib=attrib)
                el.text = _clean(item)

        try:
            # Locate existing node to replace
            node, attrib, _oldval, _parent = next(self._get_elements(key))
            if attrib:
                if not isinstance(val, str):
                    raise TypeError(val)
                node.set(attrib, _clean(val))
            elif isinstance(val, (list, set)):
                for child in node.findall('*'):
                    node.remove(child)
                add_array(node, val)
            elif isinstance(val, str):
                for child in node.findall('*'):
                    node.remove(child)
                if str(self._qname(key)) in LANG_ALTS:
                    add_array(node, AltList([_clean(val)]))
                else:
                    node.text = _clean(val)
            else:
                raise TypeError(val)
        except StopIteration:
            # Insert a new node
            rdf = self._get_rdf_root()
            if str(self._qname(key)) in LANG_ALTS:
                val = AltList([_clean(val)])
            if isinstance(val, (list, set)):
                rdfdesc = etree.SubElement(
                    rdf,
                    QName(XMP_NS_RDF, 'Description'),
                    attrib={QName(XMP_NS_RDF, 'about'): ''},
                )
                node = etree.SubElement(rdfdesc, self._qname(key))
                add_array(node, val)
            elif isinstance(val, str):
                _rdfdesc = etree.SubElement(  # lgtm [py/unused-local-variable]
                    rdf,
                    QName(XMP_NS_RDF, 'Description'),
                    attrib={
                        QName(XMP_NS_RDF, 'about'): '',
                        self._qname(key): _clean(val),
                    },
                )
            else:
                raise TypeError(val) from None

    @ensure_loaded
    def __delitem__(self, key):
        if not self._updating:
            raise RuntimeError("Metadata not opened for editing, use with block")
        try:
            node, attrib, _oldval, parent = next(self._get_elements(key))
            if attrib:  # Inline
                del node.attrib[attrib]
                if (
                    len(node.attrib) == 1
                    and len(node) == 0
                    and QName(XMP_NS_RDF, 'about') in node.attrib
                ):
                    # The only thing left on this node is rdf:about="", so remove it
                    parent.remove(node)
            else:
                parent.remove(node)
        except StopIteration:
            raise KeyError(key) from None

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
        key_part = QName(XMP_NS_PDFA_ID, 'part')
        key_conformance = QName(XMP_NS_PDFA_ID, 'conformance')
        try:
            return self[key_part] + self[key_conformance]
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
        pdfx_version = QName(XMP_NS_PDFX_ID, 'GTS_PDFXVersion')
        try:
            return self[pdfx_version]
        except KeyError:
            return ''

    @ensure_loaded
    def __str__(self):
        return self._get_xml_bytes(xpacket=False).decode('utf-8')
