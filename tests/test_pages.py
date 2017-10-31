import pytest
from pikepdf import _qpdf as qpdf

import os
import platform
import shutil
from contextlib import suppress
from shutil import copy


def test_split_pdf(resources, outdir):
    q = qpdf.Pdf.open(resources / "fourpages.pdf")

    for n, page in enumerate(q.pages):
        outpdf = qpdf.Pdf.new()
        outpdf.pages.append(page)
        outpdf.save(outdir / "page{}.pdf".format(n + 1))

    assert len([f for f in outdir.iterdir() if f.name.startswith('page')]) == 4


def test_empty_pdf(outdir):
    q = qpdf.Pdf.new()
    with pytest.raises(IndexError):
        q.pages[0]
    q.save(outdir / 'empty.pdf')


def test_replace_page(resources):
    q = qpdf.Pdf.open(resources / "fourpages.pdf")
    q2 = qpdf.Pdf.open(resources / "graph.pdf")

    assert len(q.pages) == 4
    q.pages[1] = q2.pages[0]
    assert len(q.pages) == 4
    assert q.pages[1].Resources.XObject.keys() == \
        q2.pages[0].Resources.XObject.keys()


def test_reverse_pages(resources, outdir):
    q = qpdf.Pdf.open(resources / "fourpages.pdf")
    qr = qpdf.Pdf.open(resources / "fourpages.pdf")

    lengths = [int(page.Contents.stream_dict.Length) for page in q.pages]

    qr.pages.reverse()
    qr.save(outdir / "reversed.pdf")

    for n, length in enumerate(lengths):
        assert q.pages[n].Contents.stream_dict.Length == length

    for n, length in enumerate(reversed(lengths)):
        assert qr.pages[n].Contents.stream_dict.Length == length


def test_evil_page_deletion(resources, outdir):
    # str needed for py<3.6
    copy(str(resources / 'sandwich.pdf'), str(outdir / 'sandwich.pdf')) 
    
    src = qpdf.Pdf.open(outdir / 'sandwich.pdf')
    pdf = qpdf.Pdf.open(resources / 'graph.pdf')

    pdf.pages.append(src.pages[0])

    del src.pages[0]    
    (outdir / 'sandwich.pdf').unlink()
    pdf.save(outdir / 'out.pdf')

    del pdf.pages[0]
    pdf.save(outdir / 'out2.pdf')

    del pdf.pages[0]
    pdf.save(outdir / 'out_nopages.pdf')


def test_append_all(resources, outdir):
    pdf = qpdf.Pdf.open(resources / 'sandwich.pdf')
    pdf2 = qpdf.Pdf.open(resources / 'fourpages.pdf')

    for page in pdf2.pages:
        pdf.pages.append(page)

    assert len(pdf.pages) == 5
    pdf.save(outdir / 'out.pdf')


def test_extend(resources, outdir):
    pdf = qpdf.Pdf.open(resources / 'sandwich.pdf')
    pdf2 = qpdf.Pdf.open(resources / 'fourpages.pdf')
    pdf.pages.extend(pdf2.pages)

    assert len(pdf.pages) == 5
    pdf.save(outdir / 'out.pdf')


def test_slice_unequal_replacement(resources, outdir):
    pdf = qpdf.Pdf.open(resources / 'fourpages.pdf')
    pdf2 = qpdf.Pdf.open(resources / 'sandwich.pdf')

    assert len(pdf.pages[1:]) != len(pdf2.pages)
    page0_content_len = int(pdf.pages[0].Contents.stream_dict.Length)
    page1_content_len = int(pdf.pages[1].Contents.stream_dict.Length)
    pdf.pages[1:] = pdf2.pages

    assert len(pdf.pages) == 2, "number of pages must be changed"
    pdf.save(outdir / 'out.pdf')
    assert pdf.pages[0].Contents.stream_dict.Length == page0_content_len, \
        "page 0 should be unchanged"
    assert pdf.pages[1].Contents.stream_dict.Length != page1_content_len, \
        "page 1's contents should have changed"


def test_slice_with_step(resources, outdir):
    pdf = qpdf.Pdf.open(resources / 'fourpages.pdf')
    pdf2 = qpdf.Pdf.open(resources / 'sandwich.pdf')

    pdf2.pages.extend(pdf2.pages[:])
    assert len(pdf2.pages) == 2
    pdf2_content_len = int(pdf2.pages[0].Contents.stream_dict.Length)

    pdf.pages[0::2] = pdf2.pages
    pdf.save(outdir / 'out.pdf')

    assert all(page.Contents.stream_dict.Length == pdf2_content_len 
               for page in pdf.pages[0::2])


@pytest.mark.timeout(1)
def test_self_extend(resources):
    pdf = qpdf.Pdf.open(resources / 'fourpages.pdf')
    with pytest.raises(ValueError, 
            message="source page list modified during iteration"):
        pdf.pages.extend(pdf.pages)