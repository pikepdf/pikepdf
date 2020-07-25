import gc
from contextlib import suppress
from shutil import copy
from sys import getrefcount as refcount

import pytest

from pikepdf import Array, Dictionary, Name, Pdf, PdfMatrix, Stream

# pylint: disable=redefined-outer-name,pointless-statement


@pytest.fixture
def graph(resources):
    return Pdf.open(resources / 'graph.pdf')


@pytest.fixture
def fourpages(resources):
    return Pdf.open(resources / 'fourpages.pdf')


@pytest.fixture
def sandwich(resources):
    return Pdf.open(resources / 'sandwich.pdf')


def test_split_pdf(fourpages, outdir):
    for n, page in enumerate(fourpages.pages):
        outpdf = Pdf.new()
        outpdf.pages.append(page)
        outpdf.save(outdir / "page{}.pdf".format(n + 1))

    assert len([f for f in outdir.iterdir() if f.name.startswith('page')]) == 4


def test_empty_pdf(outdir):
    q = Pdf.new()
    with pytest.raises(IndexError):
        q.pages[0]
    q.save(outdir / 'empty.pdf')


def test_delete_last_page(graph, outdir):
    q = graph
    del q.pages[0]
    q.save(outdir / 'empty.pdf')


def test_replace_page(graph, fourpages):
    q = fourpages
    q2 = graph
    q2.pages[0].CropBox = [0, 0, 500, 500]

    # Ensure the page keys are different, not subsets
    assert q.pages[1].keys() - q2.pages[0].keys()
    assert q2.pages[0].keys() - q.pages[1].keys()

    assert len(q.pages) == 4
    q.pages[1] = q2.pages[0]
    assert len(q.pages) == 4
    assert q.pages[1].keys() == q2.pages[0].keys()
    assert q.pages[1].Resources.XObject.keys() == q2.pages[0].Resources.XObject.keys()


def test_hard_replace_page(fourpages, graph, sandwich, outdir):
    q = fourpages
    q2 = graph

    q2_page = q2.pages[0]
    del q2
    q.pages[1] = q2_page

    q2 = sandwich
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
    assert refcount(src) == 2

    del src.pages[0]
    gc.collect()
    assert refcount(src) == 2

    with suppress(PermissionError):  # Fails on Windows
        (outdir / 'sandwich.pdf').unlink()
    pdf.save(outdir / 'out.pdf')

    del pdf.pages[0]
    pdf.save(outdir / 'out2.pdf')

    del pdf.pages[0]
    pdf.save(outdir / 'out_nopages.pdf')
    del pdf
    gc.collect()


def test_append_all(sandwich, fourpages, outdir):
    pdf = sandwich
    pdf2 = fourpages

    for page in pdf2.pages:
        pdf.pages.append(page)

    assert len(pdf.pages) == 5
    pdf.save(outdir / 'out.pdf')


def test_extend_delete(sandwich, fourpages, outdir):
    pdf = sandwich
    pdf2 = fourpages
    pdf.pages.extend(pdf2.pages)

    assert len(pdf.pages) == 5

    del pdf.pages[2:4]

    pdf.save(outdir / 'out.pdf')


def test_slice_unequal_replacement(fourpages, sandwich, outdir):
    pdf = fourpages
    pdf2 = sandwich

    assert len(pdf.pages[1:]) != len(pdf2.pages)
    page0_content_len = int(pdf.pages[0].Contents.Length)
    page1_content_len = int(pdf.pages[1].Contents.Length)
    pdf.pages[1:] = pdf2.pages

    assert len(pdf.pages) == 2, "number of pages must be changed"
    pdf.save(outdir / 'out.pdf')
    assert (
        pdf.pages[0].Contents.Length == page0_content_len
    ), "page 0 should be unchanged"
    assert (
        pdf.pages[1].Contents.Length != page1_content_len
    ), "page 1's contents should have changed"


def test_slice_with_step(fourpages, sandwich, outdir):
    pdf = fourpages
    pdf2 = sandwich

    pdf2.pages.extend(pdf2.pages[:])
    assert len(pdf2.pages) == 2
    pdf2_content_len = int(pdf2.pages[0].Contents.Length)

    pdf.pages[0::2] = pdf2.pages
    pdf.save(outdir / 'out.pdf')

    assert all(page.Contents.Length == pdf2_content_len for page in pdf.pages[0::2])


def test_slice_differing_lengths(fourpages, sandwich):
    pdf = fourpages
    pdf2 = sandwich

    with pytest.raises(ValueError, match="attempt to assign"):
        pdf.pages[0::2] = pdf2.pages[0:1]


@pytest.mark.timeout(1)
def test_self_extend(fourpages):
    pdf = fourpages
    with pytest.raises(ValueError, match="source page list modified during iteration"):
        pdf.pages.extend(pdf.pages)


def test_one_based_pages(fourpages):
    pdf = fourpages
    assert pdf.pages.p(1) == pdf.pages[0]
    assert pdf.pages.p(4) == pdf.pages[-1]
    with pytest.raises(IndexError):
        pdf.pages.p(5)
    with pytest.raises(IndexError):
        pdf.pages.p(0)
    with pytest.raises(IndexError):
        pdf.pages.p(-1)


def test_page_contents_add(graph, outdir):
    pdf = graph

    mat = PdfMatrix().rotated(45)

    stream1 = Stream(pdf, b'q ' + mat.encode() + b' cm')
    stream2 = Stream(pdf, b'Q')

    pdf.pages[0].page_contents_add(stream1, True)
    pdf.pages[0].page_contents_add(stream2, False)
    pdf.save(outdir / 'out.pdf')


def test_bad_access(fourpages):
    pdf = fourpages
    with pytest.raises(IndexError):
        pdf.pages[-100]
    with pytest.raises(IndexError):
        pdf.pages[500]


def test_bad_insert(fourpages):
    pdf = fourpages
    with pytest.raises(TypeError):
        pdf.pages.insert(0, 'this is a string not a page')
    with pytest.raises(TypeError):
        pdf.pages.insert(0, Dictionary(Type=Name.NotAPage, Value="Not a page"))


def test_negative_indexing(fourpages, graph):
    fourpages.pages[-1]
    fourpages.pages[-1] = graph.pages[-1]
    del fourpages.pages[-1]
    fourpages.pages.insert(-2, graph.pages[-1])
    with pytest.raises(IndexError):
        fourpages.pages[-42]
    with pytest.raises(IndexError):
        fourpages.pages[-42] = graph.pages[0]
    with pytest.raises(IndexError):
        del fourpages.pages[-42]


def test_concatenate(resources, outdir):
    # Issue #22
    def concatenate(n):
        output_pdf = Pdf.new()
        for i in range(n):
            print(i)
            pdf_page = Pdf.open(resources / 'pal.pdf')
            output_pdf.pages.extend(pdf_page.pages)
        output_pdf.save(outdir / '{}.pdf'.format(n))

    concatenate(5)


def test_emplace(fourpages):
    p0_objgen = fourpages.pages[0].objgen
    fourpages.pages[0].emplace(fourpages.pages[1])
    assert p0_objgen == fourpages.pages[0].objgen
    assert fourpages.pages[0].keys() == fourpages.pages[1].keys()
    for k in fourpages.pages[0].keys():
        assert fourpages.pages[0][k] == fourpages.pages[1][k]


def test_emplace_foreign(fourpages, sandwich):
    with pytest.raises(TypeError):
        fourpages.pages[0].emplace(sandwich.pages[0])


def test_duplicate_page(sandwich, outpdf):
    sandwich.pages.append(sandwich.pages[0])
    assert len(sandwich.pages) == 2
    sandwich.save(outpdf)


def test_repeat_using_intermediate(graph, outpdf):
    def _repeat_page(pdf_in, page, count, pdf_out):
        for _duplicate in range(count):
            pdf_new = Pdf.new()
            pdf_new.pages.append(pdf_in.pages[page])
            pdf_out.pages.extend(pdf_new.pages)
        return pdf_out

    with Pdf.new() as out:
        _repeat_page(graph, 0, 3, out)
        assert len(out.pages) == 3
        out.save(outpdf)


def test_repeat(graph, outpdf):
    def _repeat_page(pdf, page, count):
        for _duplicate in range(count):
            pdf.pages.append(pdf.pages[page])
        return pdf

    _repeat_page(graph, 0, 3)
    assert len(graph.pages) == 4
    graph.save(outpdf)


def test_add_foreign_twice(graph, outpdf):
    out = Pdf.new()
    out.pages.append(out.copy_foreign(graph.pages[0]))
    assert len(out.pages) == 1
    out.pages.append(out.copy_foreign(graph.pages[0]))
    assert len(out.pages) == 2
    out.save(outpdf)


def test_repr_pagelist(fourpages):
    assert '4' in repr(fourpages.pages)


def test_foreign_copied_pages_are_true_copies(graph, outpdf):
    out = Pdf.new()
    for n in range(4):
        out.pages.append(out.copy_foreign(graph.pages[0]))

    for n in [0, 2]:
        out.pages[n].Rotate = 180

    out.save(outpdf)
    reopened = Pdf.open(outpdf)
    assert reopened.pages[0].Rotate == 180
    assert reopened.pages[1].get(Name.Rotate, 0) == 0


def test_remove_onebased(fourpages):
    second_page = fourpages.pages.p(2)
    assert second_page == fourpages.pages[1]
    fourpages.pages.remove(p=2)
    assert second_page not in fourpages.pages
    assert len(fourpages.pages) == 3
    with pytest.raises(IndexError):
        fourpages.pages.remove(p=0)
    with pytest.raises(IndexError):
        fourpages.pages.remove(p=4)
    with pytest.raises(IndexError):
        fourpages.pages.remove(p=-1)


def test_pages_wrong_type(fourpages):
    with pytest.raises(TypeError):
        fourpages.pages.insert(3, {})
    with pytest.raises(TypeError):
        fourpages.pages.insert(3, Array([42]))


def test_page_splitting_generator(resources, tmp_path):
    def pdfs():
        pdf = Pdf.open(resources / "content-stream-errors.pdf")
        output = Pdf.new()
        part = 1
        for _idx, page in enumerate(pdf.pages):
            if len(output.pages) == 2:
                part_file = tmp_path / "part-{0}.pdf".format(part)
                output.save(part_file)
                yield part_file
                output = Pdf.new()
                part += 1
            output.pages.append(page)
        if len(output.pages) > 0:
            part_file = tmp_path / "part-{0}.pdf".format(part)
            output.save(part_file)
            yield part_file
        output.close()

    for pdf in pdfs():
        print(pdf)
