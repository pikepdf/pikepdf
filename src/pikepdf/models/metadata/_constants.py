# SPDX-FileCopyrightText: 2022 James R. Barlow
# SPDX-License-Identifier: MPL-2.0

"""XMP metadata constants, templates, and utilities."""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable
from typing import Any, NamedTuple

# XMP Namespace URIs
XMP_NS_DC = "http://purl.org/dc/elements/1.1/"
XMP_NS_PDF = "http://ns.adobe.com/pdf/1.3/"
XMP_NS_PDFA_ID = "http://www.aiim.org/pdfa/ns/id/"
XMP_NS_PDFA_EXTENSION = "http://www.aiim.org/pdfa/ns/extension/"
XMP_NS_PDFA_PROPERTY = "http://www.aiim.org/pdfa/ns/property#"
XMP_NS_PDFA_SCHEMA = "http://www.aiim.org/pdfa/ns/schema#"
XMP_NS_PDFUA_ID = "http://www.aiim.org/pdfua/ns/id/"
XMP_NS_PDFX_ID = "http://www.npes.org/pdfx/ns/id/"
XMP_NS_PHOTOSHOP = "http://ns.adobe.com/photoshop/1.0/"
XMP_NS_PRISM = "http://prismstandard.org/namespaces/basic/1.0/"
XMP_NS_PRISM2 = "http://prismstandard.org/namespaces/basic/2.0/"
XMP_NS_PRISM3 = "http://prismstandard.org/namespaces/basic/3.0/"
XMP_NS_RDF = "http://www.w3.org/1999/02/22-rdf-syntax-ns#"
XMP_NS_XMP = "http://ns.adobe.com/xap/1.0/"
XMP_NS_XMP_MM = "http://ns.adobe.com/xap/1.0/mm/"
XMP_NS_XMP_RIGHTS = "http://ns.adobe.com/xap/1.0/rights/"

# This one should not be registered with lxml
XMP_NS_XML = "http://www.w3.org/XML/1998/namespace"

DEFAULT_NAMESPACES: list[tuple[str, str]] = [
    ('adobe:ns:meta/', 'x'),
    (XMP_NS_DC, 'dc'),
    (XMP_NS_PDF, 'pdf'),
    (XMP_NS_PDFA_ID, 'pdfaid'),
    (XMP_NS_PDFA_EXTENSION, 'pdfaExtension'),
    (XMP_NS_PDFA_PROPERTY, 'pdfaProperty'),
    (XMP_NS_PDFA_SCHEMA, 'pdfaSchema'),
    (XMP_NS_PDFUA_ID, 'pdfuaid'),
    (XMP_NS_PDFX_ID, 'pdfxid'),
    (XMP_NS_PHOTOSHOP, 'photoshop'),
    (XMP_NS_PRISM, 'prism'),
    (XMP_NS_PRISM2, 'prism2'),
    (XMP_NS_PRISM3, 'prism3'),
    (XMP_NS_RDF, 'rdf'),
    (XMP_NS_XMP, 'xmp'),
    (XMP_NS_XMP_MM, 'xmpMM'),
    (XMP_NS_XMP_RIGHTS, 'xmpRights'),
    ('http://crossref.org/crossmark/1.0/', 'crossmark'),
    ('http://www.niso.org/schemas/jav/1.0/', 'jav'),
    ('http://ns.adobe.com/pdfx/1.3/', 'pdfx'),
    ('http://www.niso.org/schemas/ali/1.0/', 'ali'),
]


# XMP packet wrappers
XPACKET_BEGIN = b"""<?xpacket begin="\xef\xbb\xbf" id="W5M0MpCehiHzreSzNTczkc9d"?>\n"""

XMP_EMPTY = b"""<x:xmpmeta xmlns:x="adobe:ns:meta/" x:xmptk="pikepdf">
 <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">
 </rdf:RDF>
</x:xmpmeta>
"""

XPACKET_END = b"""\n<?xpacket end="w"?>\n"""


class XmpContainer(NamedTuple):
    """Map XMP container object to suitable Python container."""

    rdf_type: str
    py_type: type
    insert_fn: Callable[..., None]


class AltList(list):
    """XMP AltList container for language alternatives."""


XMP_CONTAINERS = [
    XmpContainer('Alt', AltList, AltList.append),
    XmpContainer('Bag', set, set.add),
    XmpContainer('Seq', list, list.append),
]


_LANG_ALTS_LAZY = [
    (XMP_NS_DC, 'title'),
    (XMP_NS_DC, 'description'),
    (XMP_NS_DC, 'rights'),
    (XMP_NS_XMP_RIGHTS, 'UsageTerms'),
]

_LOADED_LXML_NAMESPACES = False

# lxml lazy-loading
def __getattr__(name: str) -> Any:
    global _LOADED_LXML_NAMESPACES

    if name == 'LANG_ALTS':
        from lxml.etree import QName

        if not _LOADED_LXML_NAMESPACES:
            from lxml import etree
            # Register all namespaces with lxml
            for _uri, _prefix in DEFAULT_NAMESPACES:
                etree.register_namespace(_prefix, _uri)
            _LOADED_LXML_NAMESPACES = True

        val = frozenset([str(QName(x, y)) for x,y in _LANG_ALTS_LAZY])
        globals()[name] = val

        return val

    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


# These are the illegal characters in XML 1.0. (XML 1.1 is a bit more permissive,
# but we'll be strict to ensure wider compatibility.)
re_xml_illegal_chars = re.compile(
    r"(?u)[^\x09\x0A\x0D\x20-\U0000D7FF\U0000E000-\U0000FFFD\U00010000-\U0010FFFF]"
)
re_xml_illegal_bytes = re.compile(rb"[^\x09\x0A\x0D\x20-\xFF]|&#0;")


def clean(s: str | Iterable[str], joiner: str = '; ') -> str:
    """Ensure an object can safely be inserted in a XML tag body.

    If we still have a non-str object at this point, the best option is to
    join it, because it's apparently calling for a new node in a place that
    isn't allowed in the spec or not supported.
    """
    from warnings import warn

    if not isinstance(s, str):
        if isinstance(s, Iterable):
            warn(f"Merging elements of {s}")
            if isinstance(s, set):
                s = joiner.join(sorted(s))
            else:
                s = joiner.join(s)
        else:
            raise TypeError("object must be a string or iterable of strings")
    return re_xml_illegal_chars.sub('', s)
