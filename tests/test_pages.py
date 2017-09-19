import pytest
from pikepdf import _qpdf as qpdf

import os
import platform
import shutil
from contextlib import suppress


def test_split_pdf(resources, outdir):
    q = qpdf.PDF.open(resources / "fourpages.pdf")

    for n, page in enumerate(q.pages):
        outpdf = qpdf.PDF.new()
        outpdf.pages.append(page)
        outpdf.save(outdir / "page{}.pdf".format(n + 1))

    assert len([f for f in outdir.iterdir() if f.name.startswith('page')]) == 4


def test_replace_page(resources):
    q = qpdf.PDF.open(resources / "fourpages.pdf")
    q2 = qpdf.PDF.open(resources / "graph.pdf")

    assert len(q.pages) == 4
    q.pages[1] = q2.pages[0]
    assert len(q.pages) == 4
    assert q.pages[1].Resources.XObject.keys() == \
        q2.pages[0].Resources.XObject.keys()


def test_reverse_pages(resources, outdir):
    q = qpdf.PDF.open(resources / "fourpages.pdf")
    qr = qpdf.PDF.open(resources / "fourpages.pdf")

    qr.pages.reverse()
    qr.save(outdir / "reversed.pdf")
    assert q.pages[0].Contents.stream_dict.Length == \
        qr.pages[3].Contents.stream_dict.Length
    