import pytest
from pikepdf import qpdf
import os


class PrintParser(qpdf.StreamParser):
    def __init__(self):
        super().__init__()

    def handle_object(self, obj):
        print(repr(obj))

    def handle_eof(self):
        print("--EOF--")


class ExceptionParser(qpdf.StreamParser):
    def __init__(self):
        super().__init__()

    def handle_object(self, obj):
        raise ValueError("I take exception to this")

    def handle_eof(self):
        print("--EOF--")


def test_open_pdf(resources):
    pdf = qpdf.QPDF.open(resources / 'graph.pdf')
    stream = pdf.pages[0]['/Contents']
    qpdf.Object.parse_stream(stream, PrintParser())


def test_parser_exception(resources):
    pdf = qpdf.QPDF.open(resources / 'graph.pdf')
    stream = pdf.pages[0]['/Contents']
    with pytest.raises(ValueError):
        qpdf.Object.parse_stream(stream, ExceptionParser())

