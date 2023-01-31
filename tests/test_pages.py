# SPDX-FileCopyrightText: 2022 James R. Barlow
# SPDX-License-Identifier: CC0-1.0

from __future__ import annotations

import gc
from contextlib import suppress
from shutil import copy

import pytest

from pikepdf import Array, Dictionary, Name, Page, Pdf, Stream
from pikepdf._cpphelpers import label_from_label_dict

# pylint: disable=redefined-outer-name,pointless-statement


@pytest.fixture
def graph(resources):
    with Pdf.open(resources / 'graph.pdf') as pdf:
        yield pdf


@pytest.fixture
def fourpages(resources):
    with Pdf.open(resources / 'fourpages.pdf') as pdf:
        yield pdf


@pytest.fixture
def sandwich(resources):
    with Pdf.open(resources / 'sandwich.pdf') as pdf:
        yield pdf


def test_split_pdf(fourpages, outdir):
    for n, page in enumerate(fourpages.pages):
        outpdf = Pdf.new()
        outpdf.pages.append(page)
        outpdf.save(outdir / f"page{n + 1}.pdf")

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
    with Pdf.open(resources / "fourpages.pdf") as q, Pdf.open(
        resources / "fourpages.pdf"
    ) as qr:
        lengths = [int(page.Contents.stream_dict.Length) for page in q.pages]

        qr.pages.reverse()
        qr.save(outdir / "reversed.pdf")

        for n, length in enumerate(lengths):
            assert q.pages[n].Contents.stream_dict.Length == length

        for n, length in enumerate(reversed(lengths)):
            assert qr.pages[n].Contents.stream_dict.Length == length


def test_evil_page_deletion(refcount, resources, outdir):
    copy(resources / 'sandwich.pdf', outdir / 'sandwich.pdf')

    src = Pdf.open(outdir / 'sandwich.pdf')  # no with clause
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


def test_extend_with_nonpage(sandwich):
    pdf = sandwich
    with pytest.raises(TypeError, match="only pikepdf"):
        pdf.pages.extend([42])


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
            with Pdf.open(resources / 'pal.pdf') as pdf_page:
                output_pdf.pages.extend(pdf_page.pages)
        output_pdf.save(outdir / f'{n}.pdf')

    concatenate(5)


def test_emplace(fourpages):
    p0_objgen = fourpages.pages[0].objgen
    fourpages.pages[0].SpecialKey = "This string will be deleted"
    fourpages.pages[0].Parent = Name.ParentWillBeRetained
    repr_fourpages_1 = repr(fourpages.pages[1])

    fourpages.pages[0].emplace(fourpages.pages[1])

    assert p0_objgen == fourpages.pages[0].objgen, "objgen modified"
    assert fourpages.pages[0].keys() == fourpages.pages[1].keys(), "Keys mismatched"
    for k in fourpages.pages[0].keys():
        if k != Name.Parent:
            assert fourpages.pages[0][k] == fourpages.pages[1][k], "Key not copied"
        else:
            assert (
                fourpages.pages[0][k] == Name.ParentWillBeRetained
            ), "Retained key not retained"
    assert Name.SpecialKey not in fourpages.pages[0]
    assert repr_fourpages_1 == repr(fourpages.pages[1]), "Source page was modified"


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


def test_add_twice_without_copy_foreign(graph, outpdf):
    out = Pdf.new()
    out.pages.append(graph.pages[0])
    assert len(out.pages) == 1
    out.pages.append(graph.pages[0])
    assert len(out.pages) == 2
    out.save(outpdf)


def test_repr_pagelist(fourpages):
    assert '4' in repr(fourpages.pages)


def test_foreign_copied_pages_are_true_copies(graph, outpdf):
    out = Pdf.new()
    for _ in range(4):
        out.pages.append(graph.pages[0])

    for n in [0, 2]:
        out.pages[n].rotate(180, relative=True)

    out.save(outpdf)
    with Pdf.open(outpdf) as reopened:
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
    # https://github.com/pikepdf/pikepdf/issues/114
    def pdfs():
        with Pdf.open(
            resources / "content-stream-errors.pdf"
        ) as pdf, Pdf.new() as output:
            part = 1
            for _idx, page in enumerate(pdf.pages):
                if len(output.pages) == 2:
                    part_file = tmp_path / f"part-{part}.pdf"
                    output.save(part_file)
                    yield part_file
                    output = Pdf.new()
                    part += 1
                output.pages.append(page)
            if len(output.pages) > 0:
                part_file = tmp_path / f"part-{part}.pdf"
                output.save(part_file)
                yield part_file

    for pdf in pdfs():
        print(pdf)


def test_page_index(fourpages):
    for n, page in enumerate(fourpages.pages):
        assert page.index == n
        assert fourpages.pages.index(page) == n
        assert fourpages.pages.index(page.obj) == n
    del fourpages.pages[1]
    for n, page in enumerate(fourpages.pages):
        assert page.index == n
        assert fourpages.pages.index(page.obj) == n


def test_page_index_foreign_page(fourpages, sandwich):
    with pytest.raises(ValueError, match="Page is not in this Pdf"):
        fourpages.pages.index(sandwich.pages[0])

    p3 = fourpages.pages[2]
    assert p3.index == 2
    fourpages.pages.insert(2, sandwich.pages[0])
    assert fourpages.pages[2].index == 2
    assert p3.index == 3

    assert fourpages.pages.index(p3) == 3
    assert fourpages.pages.index(Page(p3)) == 3  # Keep

    with pytest.raises(ValueError, match="Page is not in this Pdf"):
        # sandwich.pages[0] is still not "in" fourpages; it gets copied into it
        assert fourpages.pages.index(sandwich.pages[0])


@pytest.mark.parametrize(
    'd, result, exc, excmsg',
    [
        (Dictionary(), '', None, None),
        (Dictionary(St=1), '', None, None),
        (Dictionary(S=Name.D, St=1), '1', None, None),
        (Dictionary(P='foo'), 'foo', None, None),
        (Dictionary(P='A', St=2), 'A', None, None),
        (Dictionary(P='A-', S=Name.D, St=2), 'A-2', None, None),
        (Dictionary(S=Name.R, St=42), 'XLII', None, None),
        (Dictionary(S=Name.r, St=1729), 'mdccxxix', None, None),
        (Dictionary(P="Appendix-", S=Name.a, St=261), 'Appendix-ja', None, None),
        (42, '42', None, None),
        (Dictionary(S=Name.R, St=-42), None, ValueError, "Can't represent"),
        (Dictionary(S=Name.A, St=-42), None, ValueError, "Can't represent"),
        (
            Dictionary(S=Name.r, St=Name.Invalid),
            'i',
            UserWarning,
            'invalid non-integer start value',
        ),
        (Dictionary(S="invalid", St=42), '', UserWarning, 'invalid page label style'),
    ],
)
def test_page_label_dicts(d, result, exc, excmsg):
    if exc:
        if issubclass(exc, Warning):
            with pytest.warns(exc, match=excmsg):
                assert label_from_label_dict(d) == result
        elif issubclass(exc, Exception):
            with pytest.raises(exc, match=excmsg):
                label_from_label_dict(d)
    else:
        assert label_from_label_dict(d) == result


def test_externalize(resources):
    with Pdf.open(resources / 'image-mono-inline.pdf') as p:
        page = p.pages[0]
        page.contents_coalesce()
        assert b'BI' in page.obj.Contents.read_bytes(), "no inline image"

        assert Name.XObject not in page.obj.Resources, "expected no xobjs"
        page.externalize_inline_images()

        assert Name.XObject in page.obj.Resources, "image not created"

        pdfimagexobj = next(iter(p.pages[0].images.values()))
        assert pdfimagexobj.Subtype == Name.Image

        assert page.label == '1'


def test_page_labels():
    p = Pdf.new()
    d = Dictionary(Type=Name.Page, MediaBox=[0, 0, 612, 792], Resources=Dictionary())
    for n in range(5):
        p.pages.append(d)
        p.pages[n].Contents = Stream(p, b"BT (Page %s) Tj ET" % str(n).encode())

    p.Root.PageLabels = p.make_indirect(
        Dictionary(
            Nums=Array(
                [
                    0,  # new label rules begin at index 0
                    Dictionary(S=Name.r),  # use lowercase roman numerals, until...
                    2,  # new label rules begin at index 2
                    Dictionary(
                        S=Name.D, St=42, P='Prefix-'
                    ),  # label pages as 'Prefix-42', 'Prefix-43', ...
                ]
            )
        )
    )

    labels = ['i', 'ii', 'Prefix-42', 'Prefix-43', 'Prefix-44']
    for n in range(5):
        page = p.pages[n]
        assert page.label == labels[n]


def test_unattached_page():
    rawpage = Dictionary(
        Type=Name.Page, MediaBox=[0, 0, 612, 792], Resources=Dictionary()
    )
    page = Page(rawpage)

    with pytest.raises(ValueError, match='not attached'):
        page.index
    with pytest.raises(ValueError, match='not attached'):
        page.label


def test_unindexed_page(graph):
    page = graph.pages[0]
    del graph.pages[0]
    with pytest.raises(ValueError, match='not consistently registered'):
        page.index


def test_page_from_objgen(graph):
    assert graph.pages.from_objgen(graph.pages[0].objgen) == graph.pages[0]
    assert (
        graph.pages.from_objgen(graph.pages[0].objgen[0], graph.pages[0].objgen[1])
        == graph.pages[0]
    )
    with pytest.raises(ValueError):
        graph.pages.from_objgen(graph.pages[0].Contents.objgen)
