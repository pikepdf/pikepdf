# SPDX-FileCopyrightText: 2022 James R. Barlow
# SPDX-License-Identifier: CC0-1.0

from __future__ import annotations

import pytest

from pikepdf import Pdf, PdfError, Token, TokenFilter, TokenType


@pytest.fixture
def pal(resources):
    return Pdf.open(resources / 'pal-1bit-rgb.pdf')


class FilterThru(TokenFilter):
    def handle_token(self, token):
        return token


class FilterDrop(TokenFilter):
    def handle_token(self, token):
        return None


class FilterNumbers(TokenFilter):
    def __init__(self):
        super().__init__()

    def handle_token(self, token):
        if token.type_ in (TokenType.real, TokenType.integer):
            return [token, Token(TokenType.space, b" ")]


class FilterCollectNames(TokenFilter):
    def __init__(self):
        super().__init__()
        self.names = []
        self.rawnames = []

    def handle_token(self, token):
        if token.type_ == TokenType.name_:
            self.names.append(token.value)
            self.rawnames.append(token.raw_value)
        return None


def test_token_eq_token():
    token_42 = Token(TokenType.integer, b'42')
    assert Token(TokenType.space, b' ') != token_42
    assert Token(TokenType.integer, b'42') == token_42
    assert token_42 != 42
    assert repr(token_42) == "pikepdf.Token(TokenType.integer, b'42')"


@pytest.mark.parametrize(
    'filter, expected',
    [
        (FilterThru, b'q\n144.0000 0 0 144.0000 0.0000 0.0000 cm\n/Im0 Do\nQ'),
        (FilterDrop, b''),
        (FilterNumbers, b'144.0000 0 0 144.0000 0.0000 0.0000 '),
    ],
)
def test_filter_thru(pal, filter, expected):
    page = pal.pages[0]
    page.add_content_token_filter(filter())
    after = page.obj.Contents.read_bytes()
    assert after == expected


def test_filter_names(pal):
    page = pal.pages[0]
    filter = FilterCollectNames()
    result = page.get_filtered_contents(filter)
    assert result == b''
    assert filter.names == ['/Im0']
    after = page.obj.Contents.read_bytes()
    assert after != b''


class FilterInvalid(TokenFilter):
    def handle_token(self, token):
        return 42


def test_invalid_handle_token(pal):
    page = pal.pages[0]
    with pytest.raises((TypeError, PdfError)):
        page.get_filtered_contents(FilterInvalid())


def test_invalid_tokenfilter(pal):
    page = pal.pages[0]
    with pytest.raises(TypeError):
        page.get_filtered_contents(list())


def test_tokenfilter_is_abstract(pal):
    page = pal.pages[0]
    with pytest.raises((RuntimeError, PdfError)):
        page.get_filtered_contents(TokenFilter())


def test_issue160_tokenfilter_refcounting(resources, outpdf):
    # Ensure that add_content_token_filter properly "remembers" token filters
    # that are not needed until .save()
    class MyFilter(TokenFilter):
        def __init__(self, replace):
            super().__init__()
            self.replace = bytes(replace, 'ascii')

        def handle_token(self, tok):
            if tok.type_ == TokenType.string:
                tok_len = len(tok.raw_value)
                s = self.replace * tok_len
                return Token(TokenType.string, s)
            return tok

    with Pdf.open(resources / 'outlines.pdf') as pdf:
        pages = pdf.pages
        num = 0
        for page in pages:
            f = MyFilter(('%d' % num)[-1])
            page.add_content_token_filter(f)
            num += 1
        pdf.save(outpdf)
