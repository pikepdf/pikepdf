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

if sys.version_info < (3, 7):
    print("Requires Python 3.7+")
    sys.exit(1)


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


skip_if_pypy = pytest.mark.skipif(
    platform.python_implementation() == 'PyPy', reason="test isn't valid for PyPy"
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
