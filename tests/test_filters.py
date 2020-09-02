import shutil
import sys
from subprocess import PIPE, run

import pytest

import pikepdf


@pytest.fixture
def pal(resources):
    return pikepdf.open(resources / 'pal-1bit-rgb.pdf')


class FilterThru(pikepdf.TokenFilter):
    def handle_token(self, token):
        return token


class FilterDrop(pikepdf.TokenFilter):
    def handle_token(self, token):
        return None


class FilterNumbers(pikepdf.TokenFilter):
    def __init__(self):
        super().__init__()

    def handle_token(self, token):
        if token.type_ in (pikepdf.TokenType.real, pikepdf.TokenType.integer):
            return [token, pikepdf.Token(pikepdf.TokenType.space, b" ")]


class FilterCollectNames(pikepdf.TokenFilter):
    def __init__(self):
        super().__init__()
        self.names = []

    def handle_token(self, token):
        if token.type_ == pikepdf.TokenType.name:
            self.names.append(token.value)
        return None


@pytest.mark.parametrize(
    'filter, expected',
    [
        (FilterThru, b'q\n144.0000 0 0 144.0000 0.0000 0.0000 cm\n/Im0 Do\nQ'),
        (FilterDrop, b''),
        (FilterNumbers, b'144.0000 0 0 144.0000 0.0000 0.0000 '),
    ],
)
def test_filter_thru(pal, filter, expected):
    page = pikepdf.Page(pal.pages[0])
    page.add_content_token_filter(filter())
    after = page.obj.Contents.read_bytes()
    assert after == expected


def test_filter_names(pal):
    page = pikepdf.Page(pal.pages[0])
    filter = FilterCollectNames()
    result = page.get_filtered_contents(filter)
    assert result == b''
    assert filter.names == ['/Im0']
    after = page.obj.Contents.read_bytes()
    assert after != b''


class FilterInvalid(pikepdf.TokenFilter):
    def handle_token(self, token):
        return 42


def test_invalid_handle_token(pal):
    page = pikepdf.Page(pal.pages[0])
    with pytest.raises(pikepdf.PdfError):
        result = page.get_filtered_contents(FilterInvalid())


def test_invalid_tokenfilter(pal):
    page = pikepdf.Page(pal.pages[0])
    with pytest.raises(TypeError):
        result = page.get_filtered_contents(list())


def test_tokenfilter_is_abstract(pal):
    page = pikepdf.Page(pal.pages[0])
    try:
        result = page.get_filtered_contents(pikepdf.TokenFilter())
    except pikepdf.PdfError:
        assert 'Tried to call pure virtual' in pal.get_warnings()[0]
