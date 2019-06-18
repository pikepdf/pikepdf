import pytest

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
