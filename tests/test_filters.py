import shutil
from subprocess import PIPE, run
import sys

import pytest

import pikepdf


@pytest.fixture
def pal(resources):
    return pikepdf.open(resources / 'pal-1bit-rgb.pdf')


class FilterThru(pikepdf._qpdf.TokenFilter):
    def handle_token(self, token):
        return token


class FilterDrop(pikepdf._qpdf.TokenFilter):
    def handle_token(self, token):
        return None


class FilterDouble(pikepdf._qpdf.TokenFilter):
    def handle_token(self, token):
        return [token, token]


@pytest.mark.parametrize(
    'filter, expected',
    [
        (FilterThru, b'q\n144.0000 0 0 144.0000 0.0000 0.0000 cm\n/Im0 Do\nQ'),
        (FilterDrop, b''),
        (
            FilterDouble,
            (
                b'qq\n\n144.0000144.0000  00  00  144.0000144.0000  0.00000.0000  0.00000.00'
                b'00  cmcm\n\n/Im0/Im0  DoDo\n\nQQ'
            ),
        ),
    ],
)
def test_filter_thru(pal, filter, expected):
    page = pikepdf.Page(pal.pages[0])
    page._filter_page_contents(filter())
    after = page.obj.Contents.read_bytes()
    assert after == expected
