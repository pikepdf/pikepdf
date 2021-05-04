import os
import platform
import sys
from distutils.version import LooseVersion
from pathlib import Path

try:
    from pikepdf import __libqpdf_version__
except ImportError:
    __libqpdf_version__ = '0.0.0'


import pytest

if sys.version_info < (3, 6):
    print("Requires Python 3.6+")
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


def needs_libqpdf_v(version, *, reason=None):
    if reason is None:
        reason = "installed libqpdf is too old for this test"
    return pytest.mark.skipif(
        LooseVersion(__libqpdf_version__) <= LooseVersion(version),
        reason=reason,
    )
