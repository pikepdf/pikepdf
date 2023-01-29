# SPDX-FileCopyrightText: 2022 James R. Barlow
# SPDX-License-Identifier: CC0-1.0

from __future__ import annotations

import gc

import pytest

from pikepdf import DeletedObjectError, Pdf

# Try to do some things without blowing up


def test_access_image(resources):
    pdf = Pdf.open(resources / 'congress.pdf')
    im0 = pdf.pages[0].Resources.XObject['/Im0']

    del pdf
    gc.collect()
    with pytest.raises(DeletedObjectError):
        im0.read_raw_bytes()


def test_access_page(resources):
    pdf = Pdf.open(resources / 'graph.pdf')
    page0 = pdf.pages[0]
    also_page0 = pdf.pages.p(1)
    del pdf
    gc.collect()
    with pytest.raises(ValueError):
        page0.Contents.read_raw_bytes()
    del page0
    gc.collect()
    with pytest.raises(ValueError):
        also_page0.Contents.read_raw_bytes()


def test_remove_pdf_and_all_pages(resources):
    pdf = Pdf.open(resources / 'graph.pdf')
    page0 = pdf.pages[0]
    contents = page0.Contents
    del pdf
    del page0
    gc.collect()
    with pytest.raises(DeletedObjectError):
        contents.read_raw_bytes()
    gc.collect()


def test_access_pdf_metadata(resources):
    pdf = Pdf.open(resources / 'graph.pdf')
    meta = pdf.Root.Metadata
    del pdf
    gc.collect()
    with pytest.raises(DeletedObjectError):
        meta.read_raw_bytes()


def test_transfer_page(resources):
    pdf = Pdf.open(resources / 'graph.pdf')
    page0 = pdf.pages[0]
    before = page0.Contents.read_bytes()

    pdf2 = Pdf.open(resources / 'fourpages.pdf')
    pdf2.pages.insert(2, page0)
    p2p2 = pdf2.pages[2]

    del pdf
    del page0

    del pdf2.pages[2]
    assert before == p2p2.Contents.read_bytes()


def test_new_pdf():
    if not hasattr(gc, 'get_count'):
        pytest.skip(reason="implementation does not have gc.get_count()")

    before = gc.get_count()
    for _ in range(10):
        with Pdf.new() as pdf:
            pdf.add_blank_page()
    gc.collect()
    after = gc.get_count()

    for n in range(3):
        assert after[n] <= before[n]
