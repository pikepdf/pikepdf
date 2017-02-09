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
TEST_OUTPUT = os.path.join(TEST_OUTPUT_ROOT, 'split')


def _infile(input_basename):
    return os.path.join(TEST_RESOURCES, input_basename)


def _outfile(output_basename):
    return os.path.join(TEST_OUTPUT, os.path.basename(output_basename))


def setup_module():
    with suppress(FileNotFoundError):
        shutil.rmtree(TEST_OUTPUT)
    with suppress(FileExistsError):
        os.makedirs(TEST_OUTPUT)


def test_split_pdf():
    q = pike.QPDF.open(_infile("fourpages.pdf"))

    for n, page in enumerate(q.pages):
        outpdf = pike.QPDF.new()
        outpdf.add_page(page, False)
        outpdf.save(_outfile("page%i.pdf" % (n + 1)))

    assert len([f for f in os.listdir(TEST_OUTPUT) if f.startswith('page')]) == 4
