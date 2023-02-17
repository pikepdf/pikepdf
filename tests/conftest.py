# SPDX-FileCopyrightText: 2022 James R. Barlow
# SPDX-License-Identifier: CC0-1.0

from __future__ import annotations

import os
import platform
import sys
from pathlib import Path

from packaging.version import Version

try:
    from pikepdf import __libqpdf_version__
except ImportError:
    __libqpdf_version__ = '0.0.0'


import pytest

TESTS_ROOT = os.path.abspath(os.path.dirname(__file__))
PROJECT_ROOT = os.path.dirname(TESTS_ROOT)


@pytest.fixture(scope="session")
def resources():
    return Path(TESTS_ROOT) / 'resources'


@pytest.fixture(scope="function")
def outdir(tmp_path):
    return tmp_path


@pytest.fixture(scope="function")
def outpdf(tmp_path):
    return tmp_path / 'out.pdf'


@pytest.fixture
def refcount():
    if platform.python_implementation() == 'PyPy':
        pytest.skip(reason="test isn't valid for PyPy")
    return sys.getrefcount


skip_if_slow_cpu = pytest.mark.skipif(
    platform.processor() != 'x86_64', reason="test too slow for rasppi arm"
)
skip_if_pypy = pytest.mark.skipif(
    platform.python_implementation() == 'PyPy', reason="test isn't valid for PyPy"
)
fails_if_pypy = pytest.mark.xfail(
    platform.python_implementation() == 'PyPy', reason="test known to fail on PyPy"
)


def needs_libqpdf_v(version: str, *, reason=None):
    if reason is None:
        reason = "installed libqpdf is too old for this test"
    return pytest.mark.skipif(
        Version(__libqpdf_version__) <= Version(version),
        reason=reason,
    )


def needs_python_v(version: str, *, reason=None):
    if reason is None:
        reason = "only works on newer Python versions"
    return pytest.mark.skipif(
        Version(platform.python_version()) <= Version(version), reason=reason
    )
