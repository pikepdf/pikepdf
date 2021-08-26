import os
from io import BytesIO
from pathlib import Path

import pytest
from hypothesis import given, reproduce_failure
from hypothesis.strategies import binary, characters, text

import pikepdf.codec


def test_encode():
    assert 'abc'.encode('pdfdoc') == b'abc'
    with pytest.raises(UnicodeEncodeError):
        '你好'.encode('pdfdoc')
    assert '你好 world'.encode('pdfdoc', 'replace') == b'?? world'
    assert '你好 world'.encode('pdfdoc', 'ignore') == b' world'


def test_decode():
    assert b'A'.decode('pdfdoc') == 'A'
    assert b'\xa0'.decode('pdfdoc') == '€'


def test_unicode_surrogate():
    with pytest.raises(UnicodeEncodeError, match=r'surrogate'):
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


# whitelist_categories ensures that the listed Unicode categories will be produced
# whitelist_characters adds further characters (everything that is pdfdoc encodable)
# We specifically add Cs, surrogates, which pybind11 needs extra help with.
pdfdoc_text = text(
    alphabet=characters(
        whitelist_categories=('N', 'L', 'M', 'P', 'Cs'),
        whitelist_characters=[chr(c) for c in pikepdf.codec.PDFDOC_ENCODABLE],
    ),
)


@pytest.mark.skipif(os.name == 'nt', reason="flakey timing on Windows")
@given(pdfdoc_text)
def test_open_encoding_pdfdoc_write(tmp_path_factory, s):
    folder = tmp_path_factory.mktemp('pdfdoc')
    txt = folder / 'pdfdoc.txt'
    with open(txt, 'w', encoding='pdfdoc') as f:
        try:
            f.write(s)
        except UnicodeEncodeError:
            return
    assert txt.read_bytes().replace(b'\r\n', b'\n') == s.encode('pdfdoc')


@pytest.mark.skipif(os.name == 'nt', reason="flakey timing on Windows")
@given(pdfdoc_text)
def test_open_encoding_pdfdoc_read(tmp_path_factory, s: str):
    s = s.replace('\r', '\n')
    folder = tmp_path_factory.mktemp('pdfdoc')
    txt: Path = folder / 'pdfdoc.txt'
    try:
        txt.write_text(s, encoding='pdfdoc')
    except UnicodeEncodeError:
        return

    with open(txt, encoding='pdfdoc') as f:
        result: str = f.read()
    assert result == s


@given(pdfdoc_text)
def test_stream_writer(s):
    bio = BytesIO()
    sw = pikepdf.codec.PdfDocStreamWriter(bio)
    try:
        sw.write(s)
    except UnicodeEncodeError:
        return
    bio.seek(0)
    data = bio.read()
    assert data == s.encode('pdfdoc')


@given(pdfdoc_text)
def test_stream_reader(s):
    try:
        bio = BytesIO(s.encode('pdfdoc_pikepdf'))
    except UnicodeEncodeError:
        return
    sr = pikepdf.codec.PdfDocStreamReader(bio)
    result = sr.read()
    assert result == s
