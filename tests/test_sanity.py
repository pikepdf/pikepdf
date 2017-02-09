import pytest
from pikepdf import qpdf

import os
import platform
import shutil
from contextlib import suppress


def test_minimum_qpdf_version():
    assert qpdf.qpdf_version() >= '6.0.0'


def test_open_pdf(resources):
    pdf = qpdf.QPDF.open(resources / 'graph.pdf')
    assert '1.3' <= pdf.pdf_version <= '1.7'

    assert pdf.root['/Pages']['/Count'].as_int() == 1

