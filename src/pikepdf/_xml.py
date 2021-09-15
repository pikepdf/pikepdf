# SPDX-FileCopyrightText: 2021 James R. Barlow <james@purplerock.ca>
# SPDX-License-Identifier: MPL-2.0

from typing import IO, Any, AnyStr, Union

from lxml.etree import XMLParser as _UnsafeXMLParser
from lxml.etree import parse as _parse


class _XMLParser(_UnsafeXMLParser):
    def __init__(self, *args, **kwargs):
        # Prevent XXE attacks
        # https://rules.sonarsource.com/python/type/Vulnerability/RSPEC-2755
        kwargs['resolve_entities'] = False
        kwargs['no_network'] = True
        super().__init__(*args, **kwargs)


def parse_xml(source: Union[AnyStr, IO[Any]], recover: bool = False):
    """Wrapper around lxml's parse to provide protection against XXE attacks."""

    parser = _XMLParser(recover=recover, remove_pis=False)
    return _parse(source, parser=parser)


__all__ = ['parse_xml']
