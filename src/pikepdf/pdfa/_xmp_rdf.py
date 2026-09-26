# SPDX-FileCopyrightText: 2026 James R. Barlow
# SPDX-License-Identifier: MPL-2.0

"""Strict reading and canonical writing of XMP packets.

The packet is parsed without recovery, and ``rdf:RDF`` is walked directly,
so that the form of every property value (simple, ``rdf:Bag``, ``rdf:Seq``,
``rdf:Alt`` or structure) is seen exactly as it is written. Only the subset
of RDF that XMP serializers produce for the predefined PDF/A schemas is
accepted; anything else is reported as a problem.

The same reader decides what the speculative PDF/A conversion keeps from an
input packet, and the writer produces the packet the conversion outputs, so
the conversion only ever writes what the validator approves.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import cache
from typing import Literal, TypedDict, cast

from lxml import etree

from pikepdf.models.metadata import XPACKET_BEGIN, XPACKET_END
from pikepdf.pdfa._catalogue import load_json
from pikepdf.pdfa._flavour import Flavour

RDF = 'http://www.w3.org/1999/02/22-rdf-syntax-ns#'
X = 'adobe:ns:meta/'
XML_LANG = '{http://www.w3.org/XML/1998/namespace}lang'
PDFAID = 'http://www.aiim.org/pdfa/ns/id/'

_ABOUT = f'{{{RDF}}}about'
_PARSE_TYPE = f'{{{RDF}}}parseType'
_RESOURCE = f'{{{RDF}}}resource'
_DESCRIPTION = f'{{{RDF}}}Description'
_LI = f'{{{RDF}}}li'
_ARRAYS = {f'{{{RDF}}}{kind}': kind for kind in ('Bag', 'Seq', 'Alt')}

_CLARK = re.compile(r'^\{([^}]*)\}(.+)$')
_XMP_DATE = re.compile(
    r'^\d{4}(-\d{2}(-\d{2}(T\d{2}:\d{2}(:\d{2}(\.\d+)?)?'
    r'(Z|[+-]\d{2}:\d{2})?)?)?)?$'
)
_INTEGER = re.compile(r'^[+-]?\d+$')
_MIME_TYPE = re.compile(
    r'^[A-Za-z0-9][A-Za-z0-9!#$&^_.+-]*/[A-Za-z0-9][A-Za-z0-9!#$&^_.+-]*$'
)
_XML_ILLEGAL = re.compile(
    r'[^\x09\x0a\x0d\x20-\ud7ff\ue000-\ufffd\U00010000-\U0010ffff]'
)

Form = Literal['simple', 'Bag', 'Seq', 'Alt', 'struct', 'resource']
Category = Literal['syntax', 'about', 'unknown', 'type', 'unsupported']

# The RDF form each value type of the property tables must have
_TYPE_FORMS: dict[str, Form] = {
    'text': 'simple',
    'date': 'simple',
    'integer': 'simple',
    'boolean': 'simple',
    'mimetype': 'simple',
    'langalt': 'Alt',
    'bag': 'Bag',
    'seq': 'Seq',
    'seq-date': 'Seq',
}


class XmpTables(TypedDict):
    """The contents of ``data/xmp_properties.json``."""

    namespaces: dict[str, str]
    declaration_only: dict[str, str]
    xmp2004: dict[str, dict[str, str]]
    xmp2005: dict[str, dict[str, str]]
    flavour_namespaces: dict[str, list[str] | str]


@cache
def tables() -> XmpTables:
    """Return the XMP property tables in ``data/xmp_properties.json``."""
    return load_json('xmp_properties.json')


def property_table(flavour: Flavour) -> dict[str, dict[str, str]]:
    """Return the predefined properties for *flavour*, by namespace and name."""
    return tables()['xmp2004' if flavour.part == 1 else 'xmp2005']


def property_label(key: str, prefix: str | None = None) -> str:
    """Return ``prefix:name`` for a Clark-notation key, using known prefixes."""
    match = _CLARK.match(key)
    if match is None:
        return key
    uri, name = match.groups()
    prefixes = {u: p for p, u in tables()['namespaces'].items()}
    return f'{prefixes.get(uri, prefix or uri)}:{name}'


@dataclass(frozen=True)
class Value:
    """The value of an XMP property.

    Attributes:
        form: ``simple`` for a text value, ``Bag``, ``Seq`` or ``Alt`` for an
            array, ``struct`` for a structure and ``resource`` for an
            ``rdf:resource`` URI.
        text: The text of a simple value, or the URI of a resource.
        items: The items of an array.
        langs: For an ``Alt``, the ``xml:lang`` of each item.
        simple_items: False if an item of an array is not simple text.
        qualified: True if an item of an array has qualifiers, which are not
            kept.
    """

    form: Form
    text: str | None = None
    items: tuple[str, ...] = ()
    langs: tuple[str | None, ...] = ()
    simple_items: bool = True
    qualified: bool = False

    def x_default(self) -> str | None:
        """Return the ``x-default`` item of a language alternative."""
        if self.form != 'Alt':
            return None
        for item, lang in zip(self.items, self.langs, strict=True):
            if lang == 'x-default':
                return item
        return None


@dataclass(frozen=True)
class Problem:
    """Something in a packet that the reader does not accept.

    Attributes:
        category: ``syntax`` for RDF that XMP does not permit, ``about`` for
            a Description that does not describe the document (one with no
            ``rdf:about``, or whose ``rdf:about`` is not empty and differs
            from that of another Description), ``unknown``
            for a property not in the tables, ``type`` for a value of the
            wrong type, ``unsupported`` for content that is not checked.
        label: ``prefix:name`` of the property concerned, if any.
        message: What is wrong.
        dropped: Whether the content concerned is not in the properties read.
    """

    category: Category
    label: str | None
    message: str
    dropped: bool = True


@dataclass
class Reading:
    """The result of reading a packet.

    Attributes:
        properties: Properties that are predefined for the flavour and whose
            values have the expected type, by Clark-notation key, in the
            order they occur.
        problems: Everything the reader did not accept.
        parsed: False if the packet is not well-formed XMP.
    """

    properties: dict[str, Value] = field(default_factory=dict)
    problems: list[Problem] = field(default_factory=list)
    parsed: bool = True

    def text(self, key: str) -> str | None:
        """Return the text of a simple property, or None."""
        value = self.properties.get(key)
        return value.text if value is not None and value.form == 'simple' else None

    def dropped_labels(self) -> list[str]:
        """Return the labels of the properties not kept, without repeats."""
        return list(
            dict.fromkeys(p.label for p in self.problems if p.dropped and p.label)
        )


def _is_blank(text: str | None) -> bool:
    return text is None or text.strip(' \t\r\n') == ''


def _elements(node: etree._Element) -> list[etree._Element]:
    """Return the child elements of *node*, skipping comments."""
    return [child for child in node if isinstance(child.tag, str)]


def _has_stray_text(node: etree._Element) -> bool:
    """Return True if *node* has text other than whitespace between children."""
    if not _is_blank(node.text):
        return True
    return any(not _is_blank(child.tail) for child in node)


def _has_special_nodes(node: etree._Element) -> bool:
    return any(
        isinstance(child, etree._Entity | etree._ProcessingInstruction)
        for child in node
    )


class _Reader:
    def __init__(self, flavour: Flavour):
        self.flavour = flavour
        self.table = property_table(flavour)
        self.reading = Reading()
        self.seen: set[str] = set()
        self.document_about = ''

    def problem(
        self,
        category: Category,
        label: str | None,
        message: str,
        *,
        dropped: bool = True,
    ) -> None:
        self.reading.problems.append(Problem(category, label, message, dropped))

    def read(self, data: bytes) -> Reading:
        parser = etree.XMLParser(
            recover=False,
            resolve_entities=False,
            no_network=True,
            load_dtd=False,
            huge_tree=False,
            remove_comments=True,
        )
        try:
            tree = etree.fromstring(data, parser).getroottree()
        except (etree.XMLSyntaxError, ValueError) as e:
            self.fail(f"XMP is not well-formed XML: {e}")
            return self.reading
        if tree.docinfo.doctype:  # type: ignore[union-attr]
            self.fail("XMP has a document type declaration")
            return self.reading
        rdf = self.find_rdf(tree.getroot())
        if rdf is None:
            return self.reading
        if rdf.attrib:
            self.problem('syntax', None, "rdf:RDF has attributes")
        if _has_stray_text(rdf) or _has_special_nodes(rdf):
            self.problem('syntax', None, "rdf:RDF contains text")
        self.document_about = _document_about(rdf)
        for node in _elements(rdf):
            if node.tag != _DESCRIPTION:
                self.problem(
                    'syntax',
                    None,
                    f"rdf:RDF contains {self.label(node.tag, node.prefix)}, "
                    "not rdf:Description",
                )
                continue
            self.read_description(node)
        return self.reading

    def fail(self, message: str) -> None:
        self.reading.parsed = False
        self.problem('syntax', None, message)

    def find_rdf(self, root: etree._Element) -> etree._Element | None:
        if root.tag == f'{{{RDF}}}RDF':
            return root
        if root.tag != f'{{{X}}}xmpmeta':
            self.fail(f"XMP root element is {root.tag}, not x:xmpmeta or rdf:RDF")
            return None
        children = _elements(root)
        if (
            len(children) != 1
            or children[0].tag != f'{{{RDF}}}RDF'
            or _has_stray_text(root)
            or _has_special_nodes(root)
        ):
            self.fail("x:xmpmeta does not hold exactly one rdf:RDF")
            return None
        return children[0]

    def label(self, key: str, prefix: str | None = None) -> str:
        return property_label(key, prefix)

    def read_description(self, desc: etree._Element) -> None:
        about = desc.get(_ABOUT)
        good_about = about == self.document_about
        if not good_about:
            described = 'no rdf:about' if about is None else f'rdf:about={about!r}'
            self.problem('about', None, f"rdf:Description with {described}")
        for key, text in desc.attrib.items():
            if key == _ABOUT:
                continue
            key = str(key)
            if key.startswith(f'{{{RDF}}}') or not key.startswith('{'):
                self.problem(
                    'syntax', None, f"rdf:Description has attribute {self.label(key)}"
                )
                continue
            if key == XML_LANG:
                self.problem(
                    'unsupported', None, "rdf:Description has xml:lang", dropped=False
                )
                continue
            prefix = _prefix_of(desc, key)
            self.add(key, prefix, Value('simple', text=cast(str, text)), good_about)
        if _has_stray_text(desc) or _has_special_nodes(desc):
            self.problem('syntax', None, "rdf:Description contains text")
        for node in _elements(desc):
            key = node.tag
            if key.startswith(f'{{{RDF}}}'):
                self.problem(
                    'syntax',
                    None,
                    f"rdf:Description contains {self.label(key, node.prefix)}",
                )
                continue
            value = self.read_value(node)
            if value is not None:
                self.add(key, node.prefix, value, good_about)

    def read_value(self, node: etree._Element) -> Value | None:
        """Return the value of a property element, or None if it is invalid."""
        label = self.label(node.tag, node.prefix)
        parse_type = None
        resource = None
        fields = []
        for key, text in node.attrib.items():
            key = str(key)
            if key == XML_LANG:
                continue
            if key == _PARSE_TYPE:
                parse_type = text
            elif key == _RESOURCE:
                resource = text
            elif key.startswith(f'{{{RDF}}}') or not key.startswith('{'):
                self.problem('syntax', label, f"{label} has attribute {key}")
                return None
            else:
                fields.append(key)
        children = _elements(node)
        if _has_special_nodes(node):
            self.problem('syntax', label, f"{label} contains an entity reference")
            return None
        if parse_type is not None:
            if parse_type != 'Resource' or resource is not None:
                self.problem(
                    'syntax', label, f"{label} has rdf:parseType={parse_type!r}"
                )
                return None
            if _has_stray_text(node):
                self.problem('syntax', label, f"{label} mixes text and fields")
                return None
            return Value('struct')
        if resource is not None:
            if children or not _is_blank(node.text) or fields:
                self.problem('syntax', label, f"{label} has rdf:resource and content")
                return None
            return Value('resource', text=cast(str, resource))
        if fields:
            if children or not _is_blank(node.text):
                self.problem('syntax', label, f"{label} has qualifiers and content")
                return None
            return Value('struct')
        if not children:
            return Value('simple', text=node.text or '')
        if _has_stray_text(node):
            self.problem('syntax', label, f"{label} mixes text and elements")
            return None
        if len(children) != 1:
            self.problem('syntax', label, f"{label} has more than one value")
            return None
        child = children[0]
        if child.tag == _DESCRIPTION:
            return Value('struct')
        kind = _ARRAYS.get(child.tag)
        if kind is None:
            self.problem(
                'syntax',
                label,
                f"{label} contains {self.label(child.tag, child.prefix)}",
            )
            return None
        return self.read_array(label, kind, child)

    def read_array(self, label: str, kind: str, array: etree._Element) -> Value | None:
        if array.attrib:
            self.problem('unsupported', label, f"rdf:{kind} of {label} has attributes")
            return None
        if _has_stray_text(array) or _has_special_nodes(array):
            self.problem('syntax', label, f"rdf:{kind} of {label} contains text")
            return None
        items: list[str] = []
        langs: list[str | None] = []
        simple = True
        qualified = False
        for li in _elements(array):
            if li.tag != _LI:
                self.problem(
                    'syntax',
                    label,
                    f"rdf:{kind} of {label} contains {self.label(li.tag, li.prefix)}",
                )
                return None
            lang = None
            for key, text in li.attrib.items():
                key = str(key)
                if key == XML_LANG and kind == 'Alt':
                    lang = text
                elif key == _PARSE_TYPE:
                    simple = False
                elif key.startswith(f'{{{RDF}}}'):
                    self.problem('syntax', label, f"an item of {label} has {key}")
                    return None
                else:
                    qualified = True
            if _elements(li) or _has_special_nodes(li):
                simple = False
            items.append(cast(str, li.text or ''))
            langs.append(cast("str | None", lang))
        return Value(
            kind,  # type: ignore[arg-type]
            items=tuple(items),
            langs=tuple(langs),
            simple_items=simple,
            qualified=qualified,
        )

    def add(self, key: str, prefix: str | None, value: Value, good_about: bool) -> None:
        label = self.label(key, prefix)
        duplicate = key in self.seen
        self.seen.add(key)
        if duplicate:
            self.problem('syntax', label, f"{label} occurs more than once")
            return
        if not good_about:
            self.problem('about', label, f"{label} is in a Description that is dropped")
            return
        match = _CLARK.match(key)
        assert match is not None
        uri, name = match.groups()
        value_type = self.table.get(uri, {}).get(name)
        if value_type is None:
            self.problem('unknown', label, f"XMP property {label} is not permitted")
            return
        if value_type in {'struct', 'seq-struct'}:
            self.problem(
                'unsupported',
                label,
                f"the content of structured XMP property {label} is not checked",
            )
            return
        if value.form == 'resource':
            self.problem('unsupported', label, f"{label} is an rdf:resource")
            return
        reason = _type_problem(value_type, value)
        if reason is not None:
            self.problem('type', label, f"XMP property {label} {reason}")
            return
        if value.qualified:
            # The value is kept, without the qualifiers
            self.problem(
                'unsupported',
                label,
                f"an item of XMP property {label} has a qualifier",
                dropped=False,
            )
        self.reading.properties[key] = value


def _document_about(rdf: etree._Element) -> str:
    """Return the ``rdf:about`` of the Descriptions that describe the document.

    XMP requires every top-level Description to have the same ``rdf:about``,
    normally empty. Some writers, including pikepdf's own metadata editor,
    give them all a non-empty value such as ``uuid:...``; if every
    Description with an ``rdf:about`` has the same value, they all describe
    the document. If the values differ, only the empty one does.
    """
    abouts = {
        node.get(_ABOUT)
        for node in _elements(rdf)
        if node.tag == _DESCRIPTION and node.get(_ABOUT) is not None
    }
    if len(abouts) == 1:
        return cast(str, abouts.pop())
    return ''


def _prefix_of(node: etree._Element, key: str) -> str | None:
    match = _CLARK.match(key)
    if match is None:
        return None
    uri = match.group(1)
    for prefix, ns in node.nsmap.items():
        if ns == uri:
            return prefix
    return None


def _type_problem(value_type: str, value: Value) -> str | None:
    """Return why *value* is not of the *value_type* of the tables, or None."""
    if value_type not in _TYPE_FORMS:
        raise ValueError(f"unknown XMP value type {value_type!r}")
    invalid = f"is not a valid {value_type}"
    if value.form != _TYPE_FORMS[value_type]:
        return invalid
    if not value.simple_items:
        return "has an item that is not simple text"
    text = value.text or ''
    if value_type == 'date' and not _XMP_DATE.match(text):
        return invalid
    if value_type == 'integer' and not _INTEGER.match(text):
        return invalid
    if value_type == 'boolean' and text not in {'True', 'False'}:
        return invalid
    if value_type == 'mimetype' and not _MIME_TYPE.match(text):
        return invalid
    if value_type == 'seq-date' and not all(_XMP_DATE.match(i) for i in value.items):
        return invalid
    if value_type == 'langalt':
        if not all(value.langs):
            return "has an item without xml:lang"
        if value.langs.count('x-default') > 1:
            return "has more than one x-default item"
    return None


def read_packet(data: bytes, flavour: Flavour | str) -> Reading:
    """Read an XMP packet strictly.

    Args:
        data: The packet, as stored in the metadata stream.
        flavour: The PDF/A flavour whose predefined properties apply.
    """
    return _Reader(Flavour(flavour)).read(data)


def is_date(text: str) -> bool:
    """Return True if *text* is an XMP date."""
    return bool(_XMP_DATE.match(text))


def xml_safe(text: str) -> str:
    """Remove the characters XML 1.0 cannot represent from *text*."""
    return _XML_ILLEGAL.sub('', text)


def write_packet(properties: dict[str, Value]) -> bytes:
    """Serialize *properties* as a packet in the form the reader accepts.

    Every property is written as an element of a single ``rdf:Description``
    with an empty ``rdf:about``. Only simple values and arrays can be
    written; in a language alternative the ``x-default`` item is first.
    """
    prefixes = {uri: prefix for prefix, uri in tables()['namespaces'].items()}
    used: dict[str, str] = {}
    for key in properties:
        match = _CLARK.match(key)
        if match is None or match.group(1) not in prefixes:
            raise ValueError(f"cannot write XMP property {key}")
        uri = match.group(1)
        used[prefixes[uri]] = uri
    root = etree.Element(f'{{{X}}}xmpmeta', nsmap={'x': X})
    rdf = etree.SubElement(root, f'{{{RDF}}}RDF', nsmap={'rdf': RDF})
    desc = etree.SubElement(rdf, _DESCRIPTION, nsmap=used)
    desc.set(_ABOUT, '')
    for key, value in properties.items():
        node = etree.SubElement(desc, key)
        if value.form == 'simple':
            node.text = value.text or ''
            continue
        if value.form not in {'Bag', 'Seq', 'Alt'}:
            raise ValueError(f"cannot write XMP property {key} of form {value.form}")
        array = etree.SubElement(node, f'{{{RDF}}}{value.form}')
        langs = value.langs or (None,) * len(value.items)
        pairs = list(zip(value.items, langs, strict=True))
        if value.form == 'Alt':
            pairs.sort(key=lambda pair: pair[1] != 'x-default')
        for item, lang in pairs:
            li = etree.SubElement(array, _LI)
            if value.form == 'Alt':
                li.set(XML_LANG, lang or 'x-default')
            li.text = item
    body = etree.tostring(root, encoding='utf-8', pretty_print=True)
    return XPACKET_BEGIN + body + XPACKET_END
