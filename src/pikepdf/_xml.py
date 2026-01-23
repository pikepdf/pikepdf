# SPDX-FileCopyrightText: 2022 James R. Barlow
# SPDX-License-Identifier: MPL-2.0

from __future__ import annotations

from typing import IO, TYPE_CHECKING, Any, AnyStr

if TYPE_CHECKING:
    from lxml.etree import _Element, _ElementTree

_XMLParser = None

def parse_xml(source: AnyStr | IO[Any], recover: bool = False) -> _ElementTree:
    """Wrap lxml's parse to provide protection against XXE attacks."""
    from lxml.etree import XMLParser as _UnsafeXMLParser
    from lxml.etree import parse as _parse

    global _XMLParser

    if _XMLParser is None:
        class _XMLParserImpl(_UnsafeXMLParser):
            def __init__(self, *args: Any, **kwargs: Any):
                # Prevent XXE attacks
                # https://rules.sonarsource.com/python/type/Vulnerability/RSPEC-2755
                kwargs['resolve_entities'] = False
                kwargs['no_network'] = True
                super().__init__(*args, **kwargs)
        _XMLParser = _XMLParserImpl

    parser = _XMLParser(recover=recover, remove_pis=False)
    return _parse(source, parser=parser)

def __getattr__(name: str):
    if name in {'_Element', '_ElementTree'}:
        from lxml import etree
        value = getattr(etree, name)
        globals()[name] = value
        return value

    raise AttributeError(f"module {__name__} has no attribute {name}")

__all__ = ['parse_xml', '_ElementTree', '_Element']
