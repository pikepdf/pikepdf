import pytest
from pikepdf import Pdf, Stream, PdfMatrix

from contextlib import suppress
from shutil import copy
import gc

from sys import getrefcount as refcount


def test_split_pdf(resources, outdir):
    q = Pdf.open(resources / "fourpages.pdf")

    for n, page in enumerate(q.pages):
        outpdf = Pdf.new()
        outpdf.pages.append(page)
        outpdf.save(outdir / "page{}.pdf".format(n + 1))

    assert len([f for f in outdir.iterdir() if f.name.startswith('page')]) == 4


def test_empty_pdf(outdir):
    q = Pdf.new()
    with pytest.raises(IndexError):
        q.pages[0]
    q.save(outdir / 'empty.pdf')


def test_delete_last_page(resources, outdir):
    q = Pdf.open(resources / 'graph.pdf')
    del q.pages[0]
    q.save(outdir / 'empty.pdf')


def test_replace_page(resources):
    q = Pdf.open(resources / "fourpages.pdf")
    q2 = Pdf.open(resources / "graph.pdf")

    assert len(q.pages) == 4
    q.pages[1] = q2.pages[0]
    assert len(q.pages) == 4
    assert q.pages[1].Resources.XObject.keys() == \
        q2.pages[0].Resources.XObject.keys()


def test_hard_replace_page(resources, outdir):
    q = Pdf.open(resources / "fourpages.pdf")
    q2 = Pdf.open(resources / "graph.pdf")

    q2_page = q2.pages[0]
    del q2
    q.pages[1] = q2_page

    q2 = Pdf.open(resources / 'sandwich.pdf')
    q2_page = q2.pages[0]
    q.pages[2] = q2_page
    del q2
    del q2_page
    gc.collect()

    q.save(outdir / 'out.pdf')


def test_reverse_pages(resources, outdir):
    q = Pdf.open(resources / "fourpages.pdf")
    qr = Pdf.open(resources / "fourpages.pdf")

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

    src = Pdf.open(outdir / 'sandwich.pdf')
    pdf = Pdf.open(resources / 'graph.pdf')

    assert refcount(src) == 2
    pdf.pages.append(src.pages[0])
    assert refcount(src) == 3

    del src.pages[0]
    gc.collect()
    assert refcount(src) == 3

    with suppress(PermissionError):  # Fails on Windows
        (outdir / 'sandwich.pdf').unlink()
    pdf.save(outdir / 'out.pdf')

    del pdf.pages[0]
    pdf.save(outdir / 'out2.pdf')

    del pdf.pages[0]
    pdf.save(outdir / 'out_nopages.pdf')
    del pdf
    gc.collect()
    # Ideally we'd see the check_refcount(src, 2) at this point, but we don't
    # have a way to find out when a PDF can be closed if a page was copied out
    # of it to another PDF


def test_append_all(resources, outdir):
    pdf = Pdf.open(resources / 'sandwich.pdf')
    pdf2 = Pdf.open(resources / 'fourpages.pdf')

    for page in pdf2.pages:
        pdf.pages.append(page)

    assert len(pdf.pages) == 5
    pdf.save(outdir / 'out.pdf')


def test_extend_delete(resources, outdir):
    pdf = Pdf.open(resources / 'sandwich.pdf')
    pdf2 = Pdf.open(resources / 'fourpages.pdf')
    pdf.pages.extend(pdf2.pages)

    assert len(pdf.pages) == 5

    del pdf.pages[2:4]

    pdf.save(outdir / 'out.pdf')


def test_slice_unequal_replacement(resources, outdir):
    pdf = Pdf.open(resources / 'fourpages.pdf')
    pdf2 = Pdf.open(resources / 'sandwich.pdf')

    assert len(pdf.pages[1:]) != len(pdf2.pages)
    page0_content_len = int(pdf.pages[0].Contents.Length)
    page1_content_len = int(pdf.pages[1].Contents.Length)
    pdf.pages[1:] = pdf2.pages

    assert len(pdf.pages) == 2, "number of pages must be changed"
    pdf.save(outdir / 'out.pdf')
    assert pdf.pages[0].Contents.Length == page0_content_len, \
        "page 0 should be unchanged"
    assert pdf.pages[1].Contents.Length != page1_content_len, \
        "page 1's contents should have changed"


def test_slice_with_step(resources, outdir):
    pdf = Pdf.open(resources / 'fourpages.pdf')
    pdf2 = Pdf.open(resources / 'sandwich.pdf')

    pdf2.pages.extend(pdf2.pages[:])
    assert len(pdf2.pages) == 2
    pdf2_content_len = int(pdf2.pages[0].Contents.Length)

    pdf.pages[0::2] = pdf2.pages
    pdf.save(outdir / 'out.pdf')

    assert all(page.Contents.Length == pdf2_content_len
               for page in pdf.pages[0::2])


def test_slice_differing_lengths(resources):
    pdf = Pdf.open(resources / 'fourpages.pdf')
    pdf2 = Pdf.open(resources / 'sandwich.pdf')

    with pytest.raises(ValueError,
            message="attempt to assign"):
        pdf.pages[0::2] = pdf2.pages[0:1]


@pytest.mark.timeout(1)
def test_self_extend(resources):
    pdf = Pdf.open(resources / 'fourpages.pdf')
    with pytest.raises(ValueError,
            message="source page list modified during iteration"):
        pdf.pages.extend(pdf.pages)


def test_one_based_pages(resources):
    pdf = Pdf.open(resources / 'fourpages.pdf')
    assert pdf.pages.p(1) == pdf.pages[0]
    assert pdf.pages.p(4) == pdf.pages[-1]
    with pytest.raises(IndexError):
        pdf.pages.p(5)
    with pytest.raises(IndexError):
        pdf.pages.p(0)


def test_page_contents_add(resources, outdir):
    pdf = Pdf.open(resources / 'graph.pdf')

    mat = PdfMatrix().rotated(45)

    stream1 = Stream(pdf, b'q ' + mat.encode() + b' cm')
    stream2 = Stream(pdf, b'Q')

    pdf.pages[0].page_contents_add(stream1, True)
    pdf.pages[0].page_contents_add(stream2, False)
    pdf.save(outdir / 'out.pdf')
