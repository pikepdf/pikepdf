import sys
import os
import platform

pytest_plugins = ['helpers_namespace']

import pytest
from pathlib import Path
from subprocess import Popen, PIPE


if sys.version_info < (3, 4):
    print("Requires Python 3.4+")
    sys.exit(1)


TESTS_ROOT = os.path.abspath(os.path.dirname(__file__))
PROJECT_ROOT = os.path.dirname(TESTS_ROOT)


@pytest.fixture
def resources():
    return Path(TESTS_ROOT) / 'resources'


@pytest.fixture(scope="function")
def outdir(tmpdir):
    return Path(str(tmpdir))
