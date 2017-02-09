import pytest
import pikepdf as pike
import os

TESTS_ROOT = os.path.abspath(os.path.dirname(__file__))
SPOOF_PATH = os.path.join(TESTS_ROOT, 'spoof')
PROJECT_ROOT = os.path.dirname(TESTS_ROOT)
TEST_RESOURCES = os.path.join(PROJECT_ROOT, 'tests', 'resources')
TEST_OUTPUT_ROOT = os.environ.get(
    'PIKEPDF_TEST_OUTPUT',
    default=os.path.join(PROJECT_ROOT, 'tests', 'output'))
TEST_OUTPUT = os.path.join(TEST_OUTPUT_ROOT, 'parsers')


def _infile(input_basename):
    return os.path.join(TEST_RESOURCES, input_basename)


class PrintParser(pike.StreamParser):
    def __init__(self):
        super().__init__()

    def handle_object(self, obj):
        print(repr(obj))

    def handle_eof(self):
        print("--EOF--")


class ExceptionParser(pike.StreamParser):
    def __init__(self):
        super().__init__()

    def handle_object(self, obj):
        raise ValueError("I take exception to this")

    def handle_eof(self):
        print("--EOF--")


def test_open_pdf():
    pdf = pike.QPDF.open(_infile('graph.pdf'))
    stream = pdf.pages[0]['/Contents']
    pike.Object.parse_stream(stream, PrintParser())


def test_parser_exception():
    pdf = pike.QPDF.open(_infile('graph.pdf'))
    stream = pdf.pages[0]['/Contents']
    with pytest.raises(ValueError):
        pike.Object.parse_stream(stream, ExceptionParser())

