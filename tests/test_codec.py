import pytest
from hypothesis import example, given
from hypothesis.strategies import binary, characters

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


@given(characters())
def test_break_encode(c):
    try:
        encoded_bytes = c.encode('pdfdoc')
    except ValueError as e:
        allowed_errors = [
            "'pdfdoc' codec can't process Unicode surrogates",
            "'pdfdoc' codec can't encode some characters",
        ]
        if any((allowed in str(e)) for allowed in allowed_errors):
            return
        raise
    else:
        assert encoded_bytes.decode('pdfdoc') == c
