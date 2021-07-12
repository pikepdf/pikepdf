from io import BytesIO
from pathlib import Path

import pytest
from hypothesis import assume, given
from hypothesis.strategies import binary, characters, text

import pikepdf.codec


def test_encode():
    assert 'abc'.encode('pdfdoc') == b'abc'
    with pytest.raises(ValueError):
        '你好'.encode('pdfdoc')
    assert '你好 world'.encode('pdfdoc', 'replace') == b'?? world'
    assert '你好 world'.encode('pdfdoc', 'ignore') == b' world'


def test_decode():
    assert b'A'.decode('pdfdoc') == 'A'
    assert b'\xa0'.decode('pdfdoc') == '€'


def test_unicode_surrogate():
    with pytest.raises(ValueError, match=r'surrogate'):
        '\ud800'.encode('pdfdoc')


@given(binary())
def test_codec_involution(b):
    # For all binary strings, there is a pdfdoc decoding. The encoding of that
    # decoding recovers the initial string. (However, not all str have a pdfdoc
    # encoding.)
    assert b.decode('pdfdoc').encode('pdfdoc') == b


@given(text())
def test_break_encode(s):
    try:
        encoded_bytes = s.encode('pdfdoc')
    except ValueError as e:
        allowed_errors = [
            "'pdfdoc' codec can't encode character",
            "'pdfdoc' codec can't process Unicode surrogates",
            "'pdfdoc' codec can't encode some characters",
        ]
        if any((allowed in str(e)) for allowed in allowed_errors):
            return
        raise
    else:
        assert encoded_bytes.decode('pdfdoc') == s


@given(text())
def test_open_encoding_pdfdoc_write(tmp_path_factory, s):
    folder = tmp_path_factory.mktemp('pdfdoc')
    txt = folder / 'pdfdoc.txt'
    with open(txt, 'w', encoding='pdfdoc') as f:
        try:
            f.write(s)
        except UnicodeEncodeError:
            return
    assert txt.read_bytes() == s.encode('pdfdoc')


pdfdoc_text = text(
    alphabet=characters(
        whitelist_categories=(),
        whitelist_characters=[chr(c) for c in pikepdf.codec.PDFDOC_ENCODABLE],
    ),
)


@given(pdfdoc_text)
def test_open_encoding_pdfdoc_read(tmp_path_factory, s: str):
    s = s.replace('\r', '\n')
    folder = tmp_path_factory.mktemp('pdfdoc')
    txt: Path = folder / 'pdfdoc.txt'
    txt.write_text(s, encoding='pdfdoc')

    with open(txt, 'r', encoding='pdfdoc') as f:
        result: str = f.read()
    assert result == s


@given(pdfdoc_text)
def test_stream_writer(s):
    bio = BytesIO()
    sw = pikepdf.codec.PdfDocStreamWriter(bio)
    sw.write(s)
    bio.seek(0)
    data = bio.read()
    assert data == s.encode('pdfdoc')


@given(pdfdoc_text)
def test_stream_reader(s):
    bio = BytesIO(s.encode('pdfdoc_pikepdf'))
    sr = pikepdf.codec.PdfDocStreamReader(bio)
    result = sr.read()
    assert result == s
