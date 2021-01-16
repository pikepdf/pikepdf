import pytest
from hypothesis import example, given
from hypothesis.strategies import binary

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
    # pdfdoc is defined for all 00-FF
    assert b.decode('pdfdoc').encode('pdfdoc') == b
