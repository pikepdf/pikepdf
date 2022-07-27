# SPDX-FileCopyrightText: 2022 James R. Barlow
# SPDX-License-Identifier: CC0-1.0

from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis.strategies import binary, sampled_from

from pikepdf import DataDecodingError, Name, Pdf, PdfError, Stream, _qpdf


@pytest.fixture
def vera(resources):
    # A file that is not linearized
    with Pdf.open(resources / 'veraPDF test suite 6-2-10-t02-pass-a.pdf') as pdf:
        yield pdf


def test_foreign_linearization(vera):
    assert not vera.is_linearized
    with pytest.raises(RuntimeError, match="not linearized"):
        vera.check_linearization()


@pytest.mark.parametrize('msg, expected', [('QPDF', 'pikepdf.Pdf')])
def test_translate_qpdf_logic_error(msg, expected):
    assert _qpdf._translate_qpdf_logic_error(msg) == expected


@pytest.mark.parametrize(
    'filter_,data,msg',
    [
        ('/ASCII85Decode', b'\xba\xad', 'character out of range'),
        ('/ASCII85Decode', b'fooz', 'unexpected z'),
        ('/ASCIIHexDecode', b'1g', 'character out of range'),
        ('/FlateDecode', b'\xba\xad', 'incorrect header check'),
    ],
)
def test_data_decoding_errors(filter_: str, data: bytes, msg: str):
    p = Pdf.new()
    st = Stream(p, data, Filter=Name(filter_))
    with pytest.raises(DataDecodingError, match=msg):
        st.read_bytes()
