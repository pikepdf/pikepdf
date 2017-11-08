import gc
import pytest

from pikepdf import Pdf

# Try to do some things without blowing up

def test_access_image(resources):
    pdf = Pdf.open(resources / 'congress.pdf')
    im0 = pdf.pages[0].Resources.XObject['/Im0']
    del pdf
    gc.collect()
    im0.read_raw_bytes()


def test_access_page(resources):
    pdf = Pdf.open(resources / 'graph.pdf')
    page0 = pdf.pages[0]
    del pdf
    gc.collect()
    page0.Contents.read_raw_bytes()


def test_remove_pdf_and_all_pages(resources):
    pdf = Pdf.open(resources / 'graph.pdf')
    page0 = pdf.pages[0]
    contents = page0.Contents
    del pdf
    del page0
    gc.collect()
    contents.read_raw_bytes()


def test_access_pdf_metadata(resources):
    pdf = Pdf.open(resources / 'graph.pdf')
    meta = pdf.Root.Metadata
    del pdf
    gc.collect()
    meta.read_raw_bytes()