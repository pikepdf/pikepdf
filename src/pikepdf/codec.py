# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
#
# Copyright (C) 2017, James R. Barlow (https://github.com/jbarlow83/)

from typing import Optional, Tuple
import codecs

from ._qpdf import utf8_to_pdf_doc, pdf_doc_to_utf8


def pdfdoc_encode(input: str, errors='strict') -> Tuple[bytes, int]:
    error_marker = b'?' if errors == 'replace' else b'\xad'
    success, pdfdoc = utf8_to_pdf_doc(input, error_marker)
    if not success:
        if errors == 'strict':
            raise ValueError("'pdfdoc' codec can't encode")
        if errors == 'ignore':
            pdfdoc = pdfdoc.replace(b'\xad', b'')
    return pdfdoc, len(input)


def pdfdoc_decode(input: bytes, errors='strict') -> Tuple[str, int]:
    if isinstance(input, memoryview):
        input = input.tobytes()
    utf8 = pdf_doc_to_utf8(input)
    return utf8, len(input)


class PdfDocCodec(codecs.Codec):
    """Implements PdfDocEncoding character map used inside PDFs"""

    def encode(self, input: str, errors='strict'):
        return pdfdoc_encode(input, errors)

    def decode(self, input: bytes, errors='strict'):
        return pdfdoc_decode(input, errors)


def find_pdfdoc(encoding: str) -> Optional[codecs.CodecInfo]:
    if encoding == 'pdfdoc':
        return codecs.CodecInfo(
            name='pdfdoc', encode=PdfDocCodec().encode, decode=PdfDocCodec().decode
        )
    return None


codecs.register(find_pdfdoc)

__all__ = ['utf8_to_pdf_doc', 'pdf_doc_to_utf8']
