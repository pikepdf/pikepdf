# SPDX-FileCopyrightText: 2026 James R. Barlow
# SPDX-License-Identifier: CC0-1.0

from __future__ import annotations

import subprocess
import sys

import pytest

import pikepdf
from pikepdf import settings

QPDF_DEFAULTS = {
    'doc_max_warnings': 0,
    'parser_max_nesting': 499,
    'parser_max_errors': 15,
    'parser_max_container_size': 2**32 - 1,
    'parser_max_container_size_damaged': 5000,
    'max_stream_filters': 25,
    'dct_max_memory': 0,
    'dct_max_progressive_scans': 0,
    'flate_max_memory': 0,
    'png_max_memory': 0,
    'run_length_max_memory': 0,
    'tiff_max_memory': 0,
    'dct_throw_on_corrupt_data': True,
}


@pytest.fixture(autouse=True)
def restore_qpdf_limits():
    saved = settings.get_qpdf_limits()
    yield
    settings.set_qpdf_limits(**saved)


@pytest.fixture
def damaged_content_page():
    # 20 syntax errors, then valid path-drawing operators.
    with pikepdf.new() as pdf:
        pdf.add_blank_page()
        page = pdf.pages[0]
        page.obj.Contents = pdf.make_stream(
            b">> 1 0 0 RG\n" * 20 + b"0 0 m 10 10 l S\n"
        )
        yield page


def test_get_qpdf_limits_defaults():
    assert settings.get_qpdf_limits() == QPDF_DEFAULTS


def test_set_qpdf_limits_returns_previous():
    previous = settings.set_qpdf_limits(parser_max_errors=3, flate_max_memory=1000)
    assert previous == {'parser_max_errors': 15, 'flate_max_memory': 0}
    limits = settings.get_qpdf_limits()
    assert limits['parser_max_errors'] == 3
    assert limits['flate_max_memory'] == 1000

    settings.set_qpdf_limits(**previous)
    assert settings.get_qpdf_limits() == QPDF_DEFAULTS


def test_set_qpdf_limits_bool_option():
    previous = settings.set_qpdf_limits(dct_throw_on_corrupt_data=False)
    assert previous == {'dct_throw_on_corrupt_data': True}
    assert settings.get_qpdf_limits()['dct_throw_on_corrupt_data'] is False


def test_set_qpdf_limits_none_is_ignored():
    assert settings.set_qpdf_limits(parser_max_errors=None) == {}
    assert settings.get_qpdf_limits() == QPDF_DEFAULTS


@pytest.mark.parametrize('value', [-1, 2**32, 1.5, '3'])
def test_set_qpdf_limits_rejects_bad_values(value):
    with pytest.raises((ValueError, TypeError)):
        settings.set_qpdf_limits(parser_max_errors=value)


def test_set_qpdf_limits_validates_before_setting():
    with pytest.raises(ValueError):
        settings.set_qpdf_limits(parser_max_errors=3, flate_max_memory=-1)
    assert settings.get_qpdf_limits() == QPDF_DEFAULTS


def test_set_qpdf_limits_unknown_name():
    with pytest.raises(TypeError):
        settings.set_qpdf_limits(no_such_limit=1)  # type: ignore[call-arg]


def test_parser_max_errors_controls_content_stream_truncation(damaged_content_page):
    page = damaged_content_page
    truncated = pikepdf.parse_content_stream(page)
    assert str(truncated[-1].operator) == 'RG'

    settings.set_qpdf_limits(parser_max_errors=0)
    complete = pikepdf.parse_content_stream(page)
    assert [str(op.operator) for op in complete[-3:]] == ['m', 'l', 'S']


def test_qpdf_limit_errors_counts(damaged_content_page):
    before = settings.qpdf_limit_errors()
    pikepdf.parse_content_stream(damaged_content_page)
    assert settings.qpdf_limit_errors() > before


def test_disable_qpdf_default_limits():
    # Irreversible and process-global, so run it in a fresh interpreter.
    code = (
        "from pikepdf import settings\n"
        "settings.set_qpdf_limits(max_stream_filters=7)\n"
        "settings.disable_qpdf_default_limits()\n"
        "limits = settings.get_qpdf_limits()\n"
        "assert limits['parser_max_errors'] == 0, limits\n"
        "assert limits['parser_max_container_size_damaged'] == 2**32 - 1, limits\n"
        "assert limits['max_stream_filters'] == 7, limits\n"
        "assert limits['parser_max_nesting'] == 499, limits\n"
    )
    subprocess.run([sys.executable, '-c', code], check=True)
