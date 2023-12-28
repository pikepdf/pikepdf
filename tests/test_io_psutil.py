# SPDX-FileCopyrightText: 2022 James R. Barlow
# SPDX-License-Identifier: CC0-1.0

from __future__ import annotations

import os
import os.path
import sys
from time import sleep

import pytest

from pikepdf import Pdf

psutil = pytest.importorskip('psutil')


def _file_descriptor_is_open(
    path, retry_until: bool, retries: int = 3, delay: float = 1.0
):
    process = psutil.Process()
    for _ in range(retries):
        is_open = any((f.path == str(path.resolve())) for f in process.open_files())
        if is_open == retry_until:
            return is_open
        sleep(delay)

    return is_open


def _skip_file_descriptor_checks_if_not_supported():
    if sys.platform == 'win32' or sys.platform.startswith('freebsd'):
        pytest.skip(
            "psutil documentation warns that .open_files() has problems on these"
        )
    elif sys.implementation.name == 'pypy' or os.environ.get('CI', 'false') == 'true':
        pytest.skip("fails randomly on CI, not worth it")


@pytest.fixture
def file_descriptor_is_open():
    _skip_file_descriptor_checks_if_not_supported()

    def _wait_till_open(path):
        return _file_descriptor_is_open(path, retry_until=True)

    return _wait_till_open


@pytest.fixture
def file_descriptor_is_closed():
    _skip_file_descriptor_checks_if_not_supported()

    def _wait_till_closed(path):
        return not _file_descriptor_is_open(path, retry_until=False)

    return _wait_till_closed


def test_open_named_file_closed(
    resources, file_descriptor_is_open, file_descriptor_is_closed
):
    path = resources / 'pal.pdf'
    pdf = Pdf.open(path)  # no with clause
    assert file_descriptor_is_open(path)

    pdf.close()
    assert file_descriptor_is_closed(path), "pikepdf did not close a stream it opened"


def test_streamed_file_not_closed(resources, file_descriptor_is_open):
    path = resources / 'pal.pdf'
    stream = path.open('rb')
    pdf = Pdf.open(stream)  # no with clause
    assert file_descriptor_is_open(path)

    pdf.close()
    assert file_descriptor_is_open(path), "pikepdf closed a stream it did not open"


@pytest.mark.parametrize('branch', ['success', 'failure'])
def test_save_named_file_closed(
    resources, outdir, file_descriptor_is_open, file_descriptor_is_closed, branch
):
    with Pdf.open(resources / 'pal.pdf') as pdf:
        path = outdir / "pal.pdf"

        def confirm_opened(progress_percent):
            if progress_percent == 0:
                assert file_descriptor_is_open(path)
            if progress_percent > 0 and branch == 'failure':
                raise ValueError('failure branch')

        try:
            pdf.save(path, progress=confirm_opened)
        except ValueError:
            pass
        assert file_descriptor_is_closed(
            path
        ), "pikepdf did not close a stream it opened"


def test_save_streamed_file_not_closed(resources, outdir, file_descriptor_is_open):
    with Pdf.open(resources / 'pal.pdf') as pdf:
        path = outdir / "pal.pdf"
        stream = path.open('wb')

        def confirm_opened(progress_percent):
            if progress_percent == 0:
                assert file_descriptor_is_open(path)

        pdf.save(stream, progress=confirm_opened)
        assert file_descriptor_is_open(path), "pikepdf closed a stream it did not open"
