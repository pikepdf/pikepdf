import gc
from sys import getrefcount as refcount

import pytest

from pikepdf import Pdf

# Try to do some things without blowing up


def test_access_image(resources):
    pdf = Pdf.open(resources / 'congress.pdf')
    assert refcount(pdf) == 2  # refcount is always +1
    im0 = pdf.pages[0].Resources.XObject['/Im0']
    assert refcount(pdf) == 3, "didn't acquire a reference to owner"

    del pdf
    gc.collect()
    im0.read_raw_bytes()


def test_access_page(resources):
    pdf = Pdf.open(resources / 'graph.pdf')
    page0 = pdf.pages[0]
    also_page0 = pdf.pages.p(1)
    assert refcount(pdf) == 4, "didn't acquire a reference to owner"
    del pdf
    gc.collect()
    page0.Contents.read_raw_bytes()
    del page0
    gc.collect()
    also_page0.Contents.read_raw_bytes()


def test_remove_pdf_and_all_pages(resources):
    pdf = Pdf.open(resources / 'graph.pdf')
    page0 = pdf.pages[0]
    contents = page0.Contents
    assert refcount(pdf) == 4, "stream didn't acquire reference to owner"
    del pdf
    del page0
    gc.collect()
    contents.read_raw_bytes()
    del contents
    gc.collect()


def test_access_pdf_metadata(resources):
    pdf = Pdf.open(resources / 'graph.pdf')
    meta = pdf.Root.Metadata
    del pdf
    gc.collect()
    meta.read_raw_bytes()


def test_transfer_page(resources):
    pdf = Pdf.open(resources / 'graph.pdf')
    page0 = pdf.pages[0]
    before = page0.Contents.read_bytes()

    assert refcount(pdf) == 3  # this, pdf, page0->pdf
    assert refcount(page0) == 2

    pdf2 = Pdf.open(resources / 'fourpages.pdf')
    pdf2.pages.insert(2, page0)
    p2p2 = pdf2.pages[2]

    assert refcount(pdf) == 3  # this, pdf, page0->pdf

    assert refcount(p2p2) == 2
    del pdf
    del page0
    assert refcount(p2p2) == 2

    del pdf2.pages[2]
    assert before == p2p2.Contents.read_bytes()
