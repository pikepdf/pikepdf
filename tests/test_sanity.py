import pytest
import pikepdf as pike

import os
import platform
import shutil
from contextlib import suppress


TESTS_ROOT = os.path.abspath(os.path.dirname(__file__))
SPOOF_PATH = os.path.join(TESTS_ROOT, 'spoof')
PROJECT_ROOT = os.path.dirname(TESTS_ROOT)
TEST_RESOURCES = os.path.join(PROJECT_ROOT, 'tests', 'resources')
TEST_OUTPUT_ROOT = os.environ.get(
    'PIKEPDF_TEST_OUTPUT',
    default=os.path.join(PROJECT_ROOT, 'tests', 'output'))
TEST_OUTPUT = os.path.join(TEST_OUTPUT_ROOT, 'sanity')


def running_in_docker():
    # Docker creates a file named /.dockerinit
    return os.path.exists('/.dockerinit')


def is_linux():
    return platform.system() == 'Linux'


def setup_module():
    with suppress(FileNotFoundError):
        shutil.rmtree(TEST_OUTPUT)
    with suppress(FileExistsError):
        os.makedirs(TEST_OUTPUT)


def _infile(input_basename):
    return os.path.join(TEST_RESOURCES, input_basename)


def _outfile(output_basename):
    return os.path.join(TEST_OUTPUT, os.path.basename(output_basename))


def test_minimum_qpdf_version():
    assert pike.qpdf_version() >= '6.0.0'


def test_open_pdf():
    pdf = pike.QPDF.open(_infile('graph.pdf'))
    assert '1.3' <= pdf.pdf_version <= '1.7'

    assert pdf.root['/Pages']['/Count'].as_int() == 1

