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
    clean,
    load_lxml_namespaces,
    re_xml_illegal_bytes,
)
from pikepdf.models.metadata._schema import normalize_value

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

        self._strict = not overwrite_invalid_xml
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

        load_lxml_namespaces()

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
                self._repair_namespaces(xmp)
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
    def _repair_namespaces(cls, xmp: _ElementTree) -> None:
        """Rebind names that were parsed without their namespace.

        When XML is recovered after a parse error, lxml keeps an element or
        attribute whose namespace prefix was never declared under its literal
        name, colon and all - ``xmp:MetadataDate`` rather than
        ``{http://ns.adobe.com/xap/1.0/}MetadataDate``. Such a name can be
        iterated but never looked up, since lookups resolve the prefix to its
        URI, and it cannot be serialized to well-formed XML either. Rebind
        the names we recognize and discard the rest.
        """
        repaired = dropped = 0
        for element in list(xmp.iter()):
            tag = element.tag
            if not isinstance(tag, str):
                continue  # Comment or processing instruction
            if not tag.startswith('{') and ':' in tag:
                uri, local = cls._split_literal_name(tag)
                if uri is None:
                    parent = element.getparent()
                    if parent is not None:
                        parent.remove(element)
                        dropped += 1
                    continue
                element.tag = f'{{{uri}}}{local}'
                repaired += 1
            for name in list(element.attrib):
                if not isinstance(name, str):
                    continue
                if name.startswith('{') or ':' not in name:
                    continue
                uri, local = cls._split_literal_name(name)
                value = element.attrib.pop(name)
                if uri is None:
                    dropped += 1
                    continue
                element.set(f'{{{uri}}}{local}', value)
                repaired += 1

        if repaired or dropped:
            log.warning(
                "XMP contained %d name(s) with an undeclared namespace prefix; "
                "%d were recovered and %d discarded",
                repaired + dropped,
                repaired,
                dropped,
            )

    @classmethod
    def _split_literal_name(cls, name: str) -> tuple[str | None, str]:
        """Split a ``prefix:local`` name, resolving the prefix if we know it."""
        prefix, _, local = name.partition(':')
        uri = cls.NS.get(prefix)
        if not local or ':' in local:
            return None, local  # Truncated or otherwise unusable
        return uri, local

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
        try:
            return str(QName(uri, tag))
        except ValueError as e:
            raise ValueError(f"{name!r} is not a valid XMP property name") from e

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
                    if str(k).startswith('{' + XMP_NS_RDF + '}'):
                        continue  # rdf:about and other RDF syntax, not data
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

    def _lookup(self, key: str | QName) -> Iterator[Any]:
        """Yield the values of a key, treating an unusable name as absent."""
        try:
            self.qname(key)
        except ValueError:
            return  # Not a name any element could have
        yield from self._get_element_values(key)

    def __contains__(self, key: str | QName) -> bool:
        """Test if XMP key exists.

        A key that exists but holds an empty value is still present.
        """
        return any(True for _ in self._lookup(key))

    def get(self, key: str | QName, default: Any = None) -> Any:
        """Get XMP value for key, or default if not found."""
        try:
            return next(self._lookup(key))
        except StopIteration:
            return default

    def __getitem__(self, key: str | QName) -> Any:
        """Retrieve XMP metadata for key."""
        try:
            return next(self._lookup(key))
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
        val: Any,
        *,
        strict: bool | None = None,
        _stacklevel: int = 4,
    ) -> None:
        """Set XMP metadata key to value.

        The value is converted to the type the XMP specification defines for
        the property, where pikepdf knows it. If the value cannot be converted
        without changing its meaning, a :class:`pikepdf.XmpTypeWarning` is
        issued, or :class:`TypeError` raised when ``strict``.
        """
        if strict is None:
            strict = self._strict
        qkey = self._writable_qname(key)
        val, rdf_type = normalize_value(
            self._display_name(key, qkey),
            qkey,
            val,
            strict=strict,
            stacklevel=_stacklevel,
        )

        if not self._setitem_update(key, val, qkey, rdf_type):
            self._setitem_insert(key, val, rdf_type)

    def _display_name(self, key: str | QName, qkey: str) -> str:
        """Name a property the way a user would write it, for messages."""
        try:
            return self.prefix_from_uri(qkey)
        except (KeyError, ValueError):
            return str(key)

    def _writable_qname(self, key: str | QName) -> str:
        """Convert a name to be written, rejecting namespaces we don't know."""
        qkey = self.qname(key)
        if isinstance(key, str) and ':' in key and not key.startswith('{'):
            prefix = key.split(':', maxsplit=1)[0]
            if prefix not in self.NS:
                raise KeyError(
                    f"The namespace prefix of {key} is not registered. Call "
                    "pikepdf.models.metadata.XmpDocument.register_xml_namespace() "
                    "to register it before use."
                )
        return qkey

    def __setitem__(self, key: str | QName, val: Any) -> None:
        """Set XMP metadata key to value."""
        self.set_value(key, val)

    def _setitem_add_array(
        self, node: _Element, items: Iterable, rdf_type: str | None = None
    ) -> None:
        if rdf_type is None:
            # Property is not one we know the type of, so infer the container
            # from the Python type of the value.
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

    def _setitem_update(
        self, key: str | QName, val: Any, qkey: str, rdf_type: str | None
    ) -> bool:
        """Replace the value of an existing property.

        Returns:
            True if an existing property was updated, False if the caller
            should insert the property instead.
        """
        # Locate existing node to replace
        try:
            node, attrib, _oldval, _parent = next(self._get_elements(key))
        except StopIteration:
            return False

        is_array = rdf_type is not None or isinstance(val, list | set)
        if attrib:
            if is_array:
                # The property was stored as an attribute of rdf:Description,
                # which cannot hold an array. Discard it and insert an element.
                del node.attrib[qkey]
                return False
            if not isinstance(val, str):
                raise TypeError(f"Setting {key} to {val} with type {type(val)}")
            node.set(attrib, clean(val))
            return True

        for child in node.findall('*'):
            node.remove(child)
        if is_array:
            self._setitem_add_array(node, val, rdf_type)
        elif isinstance(val, str):
            node.text = clean(val)
        else:
            raise TypeError(f"Setting {key} to {val} with type {type(val)}")
        return True

    def _setitem_insert(
        self, key: str | QName, val: Any, rdf_type: str | None = None
    ) -> None:
        from lxml import etree
        from lxml.etree import QName

        rdf = self._get_rdf_root()
        # Reuse existing rdf:Description element if available, to avoid
        # creating multiple Description elements with the same rdf:about=""
        rdfdesc = rdf.find('rdf:Description[@rdf:about=""]', self.NS)
        if rdfdesc is None:
            rdfdesc = etree.SubElement(
                rdf,
                str(QName(XMP_NS_RDF, 'Description')),
                attrib={str(QName(XMP_NS_RDF, 'about')): ''},
            )
        if rdf_type is not None or isinstance(val, list | set):
            node = etree.SubElement(rdfdesc, self.qname(key))
            self._setitem_add_array(node, val, rdf_type)
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
            self.qname(key)
        except ValueError:
            return False
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
