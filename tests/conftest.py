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


@pytest.helpers.register
def check_refcount(thing, count):
    "Test that the reference count of thing is exactly 'count' in caller"
    try:
        from sys import refcount  # pypy doesn't haven't refcount
    except ImportError:
        return True  # ...so for pypy say it's okay

    # count + 1 because this function holds a reference, and its caller holds 
    # a reference, and we're writing this from the caller's perspective
    return refcount(thing) == count + 1


@pytest.fixture
def resources():
    return Path(TESTS_ROOT) / 'resources'


@pytest.fixture(scope="function")
def outdir(tmpdir):
    return Path(str(tmpdir))
