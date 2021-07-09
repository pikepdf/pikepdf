# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
#
# Copyright (C) 2017, James R. Barlow (https://github.com/jbarlow83/)

import codecs
from typing import Optional, Tuple

from ._qpdf import pdf_doc_to_utf8, utf8_to_pdf_doc

# pylint: disable=redefined-builtin


def pdfdoc_encode(input: str, errors: str = 'strict') -> Tuple[bytes, int]:
    error_marker = b'?' if errors == 'replace' else b'\xad'
    try:
        success, pdfdoc = utf8_to_pdf_doc(input, error_marker)
    except RuntimeError as e:
        # This error should occur from within in pybind11, with a RuntimeError
        # message like:
        #   "Unable to extract string contents! (encoding issue)"
        # It is not known to happen except when str contains Unicode surrogates.
        raise UnicodeError("'pdfdoc' codec can't process Unicode surrogates") from e
    if not success:
        if errors == 'strict':
            # libqpdf does not give precise information about where in a
            # string encoding failed, so we cannot raise UnicodeEncodeError
            # which requires those details, so we raise UnicodeError,
            # which documentation states is acceptable.
            raise UnicodeError("'pdfdoc' codec can't encode some characters")
        if errors == 'ignore':
            pdfdoc = pdfdoc.replace(error_marker, b'')
    return pdfdoc, len(input)


def pdfdoc_decode(input: bytes, errors: str = 'strict') -> Tuple[str, int]:
    if isinstance(input, memoryview):
        input = input.tobytes()
    utf8 = pdf_doc_to_utf8(input)
    return utf8, len(input)


class PdfDocCodec(codecs.Codec):
    """Implements PdfDocEncoding character map used inside PDFs"""

    def encode(self, input: str, errors: str = 'strict') -> Tuple[bytes, int]:
        return pdfdoc_encode(input, errors)

    def decode(self, input: bytes, errors: str = 'strict') -> Tuple[str, int]:
        return pdfdoc_decode(input, errors)


def find_pdfdoc(encoding: str) -> Optional[codecs.CodecInfo]:
    if encoding == 'pdfdoc':
        return codecs.CodecInfo(
            name='pdfdoc', encode=PdfDocCodec().encode, decode=PdfDocCodec().decode
        )
    return None  # pragma: no cover


codecs.register(find_pdfdoc)

__all__ = ['utf8_to_pdf_doc', 'pdf_doc_to_utf8']
