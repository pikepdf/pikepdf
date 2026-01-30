# SPDX-FileCopyrightText: 2022 James R. Barlow
# SPDX-License-Identifier: MPL-2.0

"""XMP document handling - pure XMP XML manipulation without PDF awareness."""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterable, Iterator
from io import BytesIO
from typing import TYPE_CHECKING, Any

from pikepdf._xml import parse_xml
from pikepdf.models.metadata._constants import (
    DEFAULT_NAMESPACES,
    XMP_CONTAINERS,
    XMP_EMPTY,
    XMP_NS_RDF,
    XMP_NS_XML,
    XPACKET_BEGIN,
    XPACKET_END,
    AltList,
    clean,
    re_xml_illegal_bytes,
)

if TYPE_CHECKING:
    from lxml.etree import QName, _Element, _ElementTree


log = logging.getLogger(__name__)


class NeverRaise(Exception):
    """An exception that is never raised."""


def _parser_basic(xml: bytes) -> _ElementTree:
    return parse_xml(BytesIO(xml))


def _parser_strip_illegal_bytes(xml: bytes) -> _ElementTree:
    return parse_xml(BytesIO(re_xml_illegal_bytes.sub(b'', xml)))


def _parser_recovery(xml: bytes) -> _ElementTree:
    return parse_xml(BytesIO(xml), recover=True)


def _parser_replace_with_empty_xmp(_xml: bytes = b'') -> _ElementTree:
    log.warning("Error occurred parsing XMP, replacing with empty XMP.")
    return _parser_basic(XMP_EMPTY)


PARSERS_OVERWRITE_INVALID_XML: list[Callable[[bytes], _ElementTree]] = [
    _parser_basic,
    _parser_strip_illegal_bytes,
    _parser_recovery,
    _parser_replace_with_empty_xmp,
]

PARSERS_STANDARD: list[Callable[[bytes], _ElementTree]] = [_parser_basic]


class XmpDocument:
    """Pure XMP XML manipulation.

    This class handles parsing, traversing, modifying, and serializing XMP
    metadata without any PDF-specific knowledge. It can be used standalone
    for XMP manipulation.

    Example:
        >>> xmp = XmpDocument(xmp_bytes)
        >>> title = xmp.get('dc:title')
        >>> xmp.set('dc:title', 'New Title')
        >>> xml_bytes = xmp.to_bytes()
    """

    # Namespace mappings
    NS: dict[str, str] = {prefix: uri for uri, prefix in DEFAULT_NAMESPACES}
    REVERSE_NS: dict[str, str] = dict(DEFAULT_NAMESPACES)

    def __init__(
        self,
        data: bytes = b'',
        *,
        parsers: Iterable[Callable[[bytes], _ElementTree]] | None = None,
        overwrite_invalid_xml: bool = True,
    ):
        """Parse XMP data.

        Args:
            data: XMP XML bytes to parse. Empty creates a new XMP document.
            parsers: Custom parser chain. If None, uses default based on
                overwrite_invalid_xml setting.
            overwrite_invalid_xml: If True, use recovery parsers for invalid XML.
        """
        if parsers is None:
            parsers = (
                PARSERS_OVERWRITE_INVALID_XML
                if overwrite_invalid_xml
                else PARSERS_STANDARD
            )

        self._xmp: _ElementTree = self._parse(data, parsers, overwrite_invalid_xml)

    def _parse(
        self,
        data: bytes,
        parsers: Iterable[Callable[[bytes], _ElementTree]],
        overwrite_invalid_xml: bool,
    ) -> _ElementTree:
        """Parse XMP data using fallback parsers."""
        from lxml import etree
        from lxml.etree import XMLSyntaxError

        if data.strip() == b'':
            data = XMP_EMPTY  # on some platforms lxml chokes on empty documents

        xmp: _ElementTree | None = None
        for parser in parsers:
            try:
                xmp = parser(data)
            except (
                XMLSyntaxError if overwrite_invalid_xml else NeverRaise  # type: ignore
            ) as e:
                if str(e).startswith("Start tag expected, '<' not found") or str(
                    e
                ).startswith("Document is empty"):
                    xmp = _parser_replace_with_empty_xmp()
                    break
            else:
                break

        if xmp is not None:
            try:
                pis = xmp.xpath('/processing-instruction()')
                for pi in pis:  # type: ignore[union-attr]
                    etree.strip_tags(xmp, pi.tag)  # type: ignore[union-attr]
                self._get_rdf_root_from(xmp)
            except (
                Exception  # pylint: disable=broad-except
                if overwrite_invalid_xml
                else NeverRaise
            ) as e:
                log.warning("Error occurred parsing XMP", exc_info=e)
                xmp = _parser_replace_with_empty_xmp()
        else:
            log.warning("Error occurred parsing XMP")
            xmp = _parser_replace_with_empty_xmp()

        return xmp

    @classmethod
    def register_xml_namespace(cls, uri: str, prefix: str) -> None:
        """Register a new XML/XMP namespace.

        Arguments:
            uri: The long form of the namespace.
            prefix: The alias to use when interpreting XMP.
        """
        from lxml import etree

        cls.NS[prefix] = uri
        cls.REVERSE_NS[uri] = prefix
        etree.register_namespace(prefix, uri)

    @classmethod
    def qname(cls, name: QName | str) -> str:
        """Convert name to an XML QName.

        e.g. pdf:Producer -> {http://ns.adobe.com/pdf/1.3/}Producer
        """
        from lxml.etree import QName

        if isinstance(name, QName):
            return str(name)
        if not isinstance(name, str):
            raise TypeError(f"{name} must be str")
        if name == '':
            return name
        if name.startswith('{'):
            return name
        try:
            prefix, tag = name.split(':', maxsplit=1)
        except ValueError:
            # If missing the namespace, it belongs in the default namespace.
            prefix, tag = '', name
        uri = cls.NS.get(prefix, None)
        return str(QName(uri, tag))

    def prefix_from_uri(self, uriname: str) -> str:
        """Given a fully qualified XML name, find a prefix.

        e.g. {http://ns.adobe.com/pdf/1.3/}Producer -> pdf:Producer
        """
        uripart, tag = uriname.split('}', maxsplit=1)
        uri = uripart.replace('{', '')
        return self.REVERSE_NS[uri] + ':' + tag

    def _get_rdf_root_from(self, xmp: _ElementTree) -> _Element:
        """Get the rdf:RDF root element from an XMP tree."""
        rdf = xmp.find('.//rdf:RDF', self.NS)
        if rdf is None:
            rdf = xmp.getroot()
            if not rdf.tag == '{http://www.w3.org/1999/02/22-rdf-syntax-ns#}RDF':
                raise ValueError("Metadata seems to be XML but not XMP")
        return rdf

    def _get_rdf_root(self) -> _Element:
        """Get the rdf:RDF root element."""
        return self._get_rdf_root_from(self._xmp)

    def _get_elements(
        self, name: str | QName = ''
    ) -> Iterator[tuple[_Element, str | bytes | None, Any, _Element]]:
        """Get elements from XMP.

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
            name: a prefixed name or QName to look for within the
                data section of the XMP; looks for all data keys if omitted

        Yields:
            tuple: (node, qname_attrib, value, parent_node)

        """
        qname = self.qname(name)
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

    def _get_subelements(self, node: _Element) -> Any:
        """Gather the sub-elements attached to a node.

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
            items = node.find(f'rdf:{xmlcontainer}', self.NS)
            if items is None:
                continue
            result = container()
            for item in items:
                insertfn(result, item.text)
            return result
        return ''

    def _get_element_values(self, name: str | QName = '') -> Iterator[Any]:
        yield from (v[2] for v in self._get_elements(name))

    def __contains__(self, key: str | QName) -> bool:
        """Test if XMP key exists."""
        return any(self._get_element_values(key))

    def get(self, key: str | QName, default: Any = None) -> Any:
        """Get XMP value for key, or default if not found."""
        try:
            return next(self._get_element_values(key))
        except StopIteration:
            return default

    def __getitem__(self, key: str | QName) -> Any:
        """Retrieve XMP metadata for key."""
        try:
            return next(self._get_element_values(key))
        except StopIteration:
            raise KeyError(key) from None

    def __iter__(self) -> Iterator[str]:
        """Iterate through XMP metadata attributes and nodes."""
        for node, attrib, _val, _parents in self._get_elements():
            if attrib:
                yield str(attrib)
            else:
                yield node.tag

    def __len__(self) -> int:
        """Return number of items in metadata."""
        return len(list(iter(self)))

    def set_value(
        self,
        key: str | QName,
        val: set[str] | list[str] | str,
    ) -> None:
        """Set XMP metadata key to value."""
        qkey = self.qname(key)

        try:
            # Update existing node
            self._setitem_update(key, val, qkey)
        except StopIteration:
            # Insert a new node
            self._setitem_insert(key, val)

    def __setitem__(self, key: str | QName, val: set[str] | list[str] | str) -> None:
        """Set XMP metadata key to value."""
        self.set_value(key, val)

    def _setitem_add_array(self, node: _Element, items: Iterable) -> None:
        rdf_type = next(
            c.rdf_type for c in XMP_CONTAINERS if isinstance(items, c.py_type)
        )
        from lxml import etree
        from lxml.etree import QName
        seq = etree.SubElement(node, str(QName(XMP_NS_RDF, rdf_type)))
        tag_attrib: dict[str, str] | None = None
        if rdf_type == 'Alt':
            tag_attrib = {str(QName(XMP_NS_XML, 'lang')): 'x-default'}
        for item in items:
            el = etree.SubElement(seq, str(QName(XMP_NS_RDF, 'li')), attrib=tag_attrib)
            if item is not None:
                inner_text: str | None = clean(item)
                if inner_text == '':
                    inner_text = None
                el.text = inner_text

    def _setitem_update(self, key: str | QName, val: Any, qkey: str) -> None:
        from pikepdf.models.metadata._constants import LANG_ALTS

        # Locate existing node to replace
        node, attrib, _oldval, _parent = next(self._get_elements(key))
        if attrib:
            if not isinstance(val, str):
                if qkey == self.qname('dc:creator'):
                    # dc:creator incorrectly created as an attribute - we're
                    # replacing it anyway, so remove the old one
                    del node.attrib[qkey]
                    self._setitem_add_array(node, clean(val))
                else:
                    raise TypeError(f"Setting {key} to {val} with type {type(val)}")
            else:
                node.set(attrib, clean(val))
        elif isinstance(val, list | set):
            for child in node.findall('*'):
                node.remove(child)
            self._setitem_add_array(node, val)
        elif isinstance(val, str):
            for child in node.findall('*'):
                node.remove(child)
            if str(self.qname(key)) in LANG_ALTS:
                self._setitem_add_array(node, AltList([clean(val)]))
            else:
                node.text = clean(val)
        else:
            raise TypeError(f"Setting {key} to {val} with type {type(val)}")

    def _setitem_insert(self, key: str | QName, val: Any) -> None:
        from lxml import etree
        from lxml.etree import QName

        from pikepdf.models.metadata._constants import LANG_ALTS

        rdf = self._get_rdf_root()
        if str(self.qname(key)) in LANG_ALTS:
            val = AltList([clean(val)])
        # Reuse existing rdf:Description element if available, to avoid
        # creating multiple Description elements with the same rdf:about=""
        rdfdesc = rdf.find('rdf:Description[@rdf:about=""]', self.NS)
        if rdfdesc is None:
            rdfdesc = etree.SubElement(
                rdf,
                str(QName(XMP_NS_RDF, 'Description')),
                attrib={str(QName(XMP_NS_RDF, 'about')): ''},
            )
        if isinstance(val, list | set):
            node = etree.SubElement(rdfdesc, self.qname(key))
            self._setitem_add_array(node, val)
        elif isinstance(val, str):
            node = etree.SubElement(rdfdesc, self.qname(key))
            node.text = clean(val)
        else:
            raise TypeError(f"Setting {key} to {val} with type {type(val)}") from None

    def delete(self, key: str | QName) -> bool:
        """Delete item from XMP metadata.

        Returns:
            True if item was found and deleted, False if not found.
        """
        from lxml.etree import QName

        try:
            node, attrib, _oldval, parent = next(self._get_elements(key))
            if attrib:  # Inline
                del node.attrib[attrib]
                if (
                    len(node.attrib) == 1
                    and len(node) == 0
                    and QName(XMP_NS_RDF, 'about') in node.attrib.keys()
                ):
                    # The only thing left on this node is rdf:about="", so remove it
                    parent.remove(node)
            else:
                parent.remove(node)
            return True
        except StopIteration:
            return False

    def __delitem__(self, key: str | QName) -> None:
        """Delete item from XMP metadata."""
        if not self.delete(key):
            raise KeyError(key)

    def to_bytes(self, xpacket: bool = True) -> bytes:
        """Serialize XMP to XML bytes.

        Args:
            xpacket: If True, wrap in xpacket markers.

        Returns:
            XML bytes representation of the XMP.
        """
        data = BytesIO()
        if xpacket:
            data.write(XPACKET_BEGIN)
        self._xmp.write(data, encoding='utf-8', pretty_print=True)
        if xpacket:
            data.write(XPACKET_END)
        data.seek(0)
        return data.read()

    def __str__(self) -> str:
        """Convert XMP metadata to XML string."""
        return self.to_bytes(xpacket=False).decode('utf-8')
