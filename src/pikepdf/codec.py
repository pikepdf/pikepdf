# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
#
# Copyright (C) 2017, James R. Barlow (https://github.com/jbarlow83/)

import codecs
from typing import Container, Optional, Tuple

from ._qpdf import pdf_doc_to_utf8, utf8_to_pdf_doc

# pylint: disable=redefined-builtin

# See PDF Reference Manual 1.7, Table D.2.
# The following generates set of all Unicode code points that can be encoded in
# pdfdoc. Since pdfdoc is 8-bit, the vast majority of code points cannot be.
#
# Due to a bug, QPDF <= 10.5 and pikepdf < 5 had some inconsistencies around
# PdfDocEncoding.
PDFDOC_ENCODABLE = frozenset(
    list(range(0x00, 0x17 + 1))
    + list(range(0x20, 0x7E + 1))
    + [
        0x2022,
        0x2020,
        0x2021,
        0x2026,
        0x2014,
        0x2013,
        0x0192,
        0x2044,
        0x2039,
        0x203A,
        0x2212,
        0x2030,
        0x201E,
        0x201C,
        0x201D,
        0x2018,
        0x2019,
        0x201A,
        0x2122,
        0xFB01,
        0xFB02,
        0x0141,
        0x0152,
        0x0160,
        0x0178,
        0x017D,
        0x0131,
        0x0142,
        0x0153,
        0x0161,
        0x017E,
        0x20AC,
    ]
    + [0x02D8, 0x02C7, 0x02C6, 0x02D9, 0x02DD, 0x02DB, 0x02DA, 0x02DC]
    + list(range(0xA1, 0xAC + 1))
    + list(range(0xAE, 0xFF + 1))
)


def _find_first_index(
    s: str, ordinals: Container[int], is_whitelist: bool = True
) -> int:
    for n, char in enumerate(s):
        if is_whitelist and (ord(char) not in ordinals):
            return n
        if not is_whitelist and (ord(char) in ordinals):
            return n  # pragma: no cover
    raise ValueError("couldn't find the unencodable character")  # pragma: no cover


def pdfdoc_encode(input: str, errors: str = 'strict') -> Tuple[bytes, int]:
    error_marker = b'?' if errors == 'replace' else b'\xad'
    success, pdfdoc = utf8_to_pdf_doc(input, error_marker)
    if not success:
        if errors == 'strict':
            # libqpdf doesn't return what character caused the error, and Python
            # needs this, so make an educated guess and raise an exception based
            # on that.
            offending_index = _find_first_index(input, PDFDOC_ENCODABLE)
            raise UnicodeEncodeError(
                'pdfdoc',
                input,
                offending_index,
                offending_index + 1,
                "character cannot be represented in pdfdoc encoding",
            )

        if errors == 'ignore':
            pdfdoc = pdfdoc.replace(b'\xad', b'')
    return pdfdoc, len(input)


def pdfdoc_decode(input: bytes, errors: str = 'strict') -> Tuple[str, int]:
    if isinstance(input, memoryview):
        input = input.tobytes()
    s = pdf_doc_to_utf8(input)
    if errors == 'strict':
        idx = s.find('\ufffd')
        if idx >= 0:
            raise UnicodeDecodeError(
                'pdfdoc',
                input,
                idx,
                idx + 1,
                "no Unicode mapping is defined for this character",
            )

    return s, len(input)


class PdfDocCodec(codecs.Codec):
    """Implements PdfDocEncoding character map used inside PDFs."""

    def encode(self, input: str, errors: str = 'strict') -> Tuple[bytes, int]:
        return pdfdoc_encode(input, errors)

    def decode(self, input: bytes, errors: str = 'strict') -> Tuple[str, int]:
        return pdfdoc_decode(input, errors)


class PdfDocStreamWriter(PdfDocCodec, codecs.StreamWriter):
    pass


class PdfDocStreamReader(PdfDocCodec, codecs.StreamReader):
    def decode(self, input: bytes, errors: str = 'strict') -> Tuple[str, int]:
        return PdfDocCodec.decode(self, input, errors)


class PdfDocIncrementalEncoder(codecs.IncrementalEncoder):
    def encode(self, input: str, final: bool = False) -> bytes:
        return pdfdoc_encode(input, 'strict')[0]


class PdfDocIncrementalDecoder(codecs.IncrementalDecoder):
    def decode(self, input: bytes, final: bool = False) -> str:
        return pdfdoc_decode(input, 'strict')[0]


def find_pdfdoc(encoding: str) -> Optional[codecs.CodecInfo]:
    if encoding in ('pdfdoc', 'pdfdoc_pikepdf'):
        codec = PdfDocCodec()
        return codecs.CodecInfo(
            name=encoding,
            encode=codec.encode,
            decode=codec.decode,
            streamwriter=PdfDocStreamWriter,
            streamreader=PdfDocStreamReader,
            incrementalencoder=PdfDocIncrementalEncoder,
            incrementaldecoder=PdfDocIncrementalDecoder,
        )
    return None  # pragma: no cover


codecs.register(find_pdfdoc)

__all__ = ['utf8_to_pdf_doc', 'pdf_doc_to_utf8']
