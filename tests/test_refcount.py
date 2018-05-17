import gc
import pytest
from pikepdf import Pdf

check_refcount = pytest.helpers.check_refcount

# Try to do some things without blowing up

def test_access_image(resources):
    pdf = Pdf.open(resources / 'congress.pdf')
    assert check_refcount(pdf, 2)  # refcount is always +1
    im0 = pdf.pages[0].Resources.XObject['/Im0']
    assert check_refcount(pdf, 3), "didn't acquire a reference to owner"

    del pdf
    gc.collect()
    im0.read_raw_bytes()


def test_access_page(resources):
    pdf = Pdf.open(resources / 'graph.pdf')
    page0 = pdf.pages[0]
    also_page0 = pdf.pages.p(1)
    assert check_refcount(pdf, 4), "didn't acquire a reference to owner"
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
    assert check_refcount(pdf, 4), "stream didn't acquire reference to owner"
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
