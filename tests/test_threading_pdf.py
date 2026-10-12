# SPDX-FileCopyrightText: 2026 James R. Barlow
# SPDX-License-Identifier: MPL-2.0

"""Thread safety stress tests for the Pdf and PageList bindings.

These follow the conventions of the stress tests in test_threading.py: threads
start together from a barrier, and the assertions are invariants that hold
however the threads interleave. Keep each test short, since ThreadSanitizer
slows the interpreter by roughly an order of magnitude.
"""

from __future__ import annotations

import itertools
import threading
from io import BytesIO

import pytest
from test_threading import RESOURCES, run_n, run_threads

from pikepdf import Dictionary, Name, Pdf

pytestmark = pytest.mark.timeout(120, method='thread')

N_THREADS = 8


def pdf_with_pages(n_pages, width=100):
    pdf = Pdf.new()
    for n in range(n_pages):
        pdf.add_blank_page(page_size=(width, 100 + n))
    return pdf


def churn_pages(pdf, rounds, key='/Scratch'):
    """Keep changing the first two pages of pdf, leaving them as they were.

    Threads that churn the same Pdf each need a key of their own.
    """
    for n in range(rounds):
        page = pdf.pages[n % 2]
        page.obj[key] = Dictionary(N=n, Kind=Name.Churn)
        page.obj[key].More = [n, n + 1]
        del page.obj[key]


def assert_page_tree_sound(pdf, n_pages=None):
    if n_pages is not None:
        assert len(pdf.pages) == n_pages
    assert int(pdf.Root.Pages.Count) == len(pdf.pages)
    assert all(page.obj.is_owned_by(pdf) for page in pdf.pages)
    assert len({page.obj.objgen for page in pdf.pages}) == len(pdf.pages)
    for index, page in enumerate(pdf.pages):
        assert page.index == index
    pdf.save(BytesIO())


def test_stress_shared_page_iterator_yields_each_page_once():
    """Threads drawing from one page iterator get every page exactly once."""
    pdf = pdf_with_pages(240)
    expected = sorted(page.obj.objgen for page in pdf.pages)
    it = iter(pdf.pages)
    seen = [[] for _ in range(N_THREADS)]

    def draw(i):
        while True:
            try:
                page = next(it)
            except StopIteration:
                return
            seen[i].append(page.obj.objgen)

    run_n(draw)

    assert sorted(itertools.chain.from_iterable(seen)) == expected
    with pytest.raises(StopIteration):
        next(it)


def test_stress_add_page_from_pdf_that_is_changing():
    """Pdf._add_page() of another Pdf's page holds that Pdf's lock too."""
    src = pdf_with_pages(4, width=200)
    rounds = 12
    copies = []

    def copy(i):
        dst = Pdf.new()
        for n in range(rounds):
            dst._add_page(src.pages[(i + n) % 4].obj, first=bool(n % 2))
        copies.append(dst)

    run_threads(
        *[lambda i=i: copy(i) for i in range(4)],
        lambda: churn_pages(src, 150, '/ScratchA'),
        lambda: churn_pages(src, 150, '/ScratchB'),
    )

    assert_page_tree_sound(src, 4)
    assert all(
        '/ScratchA' not in page.obj and '/ScratchB' not in page.obj
        for page in src.pages
    )
    assert len(copies) == 4
    for dst in copies:
        assert len(dst.pages) == rounds
        assert int(dst.Root.Pages.Count) == rounds
        for page in dst.pages:
            assert page.obj.is_owned_by(dst)
            assert float(page.mediabox[2]) == 200.0
        dst.save(BytesIO())


def test_stress_index_and_remove_with_pages_of_another_pdf():
    """index() and remove() given a page of another, changing, Pdf."""
    a = Pdf.new()
    b = Pdf.new()
    # Give the pages of the two Pdfs different object numbers, so that a page
    # of one cannot be mistaken for the page of the other with its number.
    for n in range(3):
        a.add_blank_page(page_size=(100, 100 + n))
        a.make_indirect(Dictionary(Padding=n))
    for n in range(3):
        b.make_indirect(Dictionary(Padding=n))
        b.add_blank_page(page_size=(200, 100 + n))
    assert not {page.obj.objgen for page in a.pages} & {
        page.obj.objgen for page in b.pages
    }
    rounds = 30

    def look_up(mine, theirs):
        for n in range(rounds):
            own = mine.pages[n % 3]
            foreign = theirs.pages[n % 3]
            assert mine.pages.index(own) == n % 3
            assert mine.pages.index(own.obj) == n % 3
            with pytest.raises(ValueError):
                mine.pages.index(foreign)
            with pytest.raises(ValueError):
                mine.pages.index(foreign.obj)
            with pytest.raises(ValueError):
                mine.pages.remove(foreign)

    run_threads(
        lambda: look_up(a, b),
        lambda: look_up(b, a),
        lambda: look_up(a, b),
        lambda: look_up(b, a),
        lambda: churn_pages(a, 150),
        lambda: churn_pages(b, 150),
    )

    assert_page_tree_sound(a, 3)
    assert_page_tree_sound(b, 3)


def test_stress_two_pdfs_assign_pages_both_ways():
    """pages[i] = page of the other Pdf, in opposite directions at once."""
    a = pdf_with_pages(3, width=100)
    b = pdf_with_pages(3, width=200)
    rounds = 20

    def assign(dst, src):
        for n in range(rounds):
            dst.pages[n % 3] = src.pages[(n + 1) % 3]
            with pytest.raises(TypeError, match='only pikepdf pages'):
                dst.pages[n % 3] = 42
            dst.pages.insert(0, src.pages[n % 3])
            dst.pages.remove(p=1)

    run_threads(
        lambda: assign(a, b),
        lambda: assign(b, a),
        lambda: assign(a, b),
        lambda: assign(b, a),
    )

    for pdf in (a, b):
        assert_page_tree_sound(pdf, 3)
        for page in pdf.pages:
            assert float(page.mediabox[2]) in (100.0, 200.0)


def test_stress_extend_from_iterables_spanning_pdfs():
    """extend() and slice assignment from iterables that run code as they go.

    The iterable yields pages of several Pdfs and uses the destination while
    it is being unpacked. An iterable with an item that is not a page raises
    before any of its pages is inserted.
    """
    sources = [pdf_with_pages(2, width=200 + 10 * k) for k in range(3)]
    dst = pdf_with_pages(1, width=100)
    rounds = 5

    def pages_of_sources(i):
        for source in sources:
            assert len(dst.pages) >= 1  # Runs while the iterable is unpacked
            yield source.pages[i % 2]

    def extend(i):
        for _ in range(rounds):
            dst.pages.extend(pages_of_sources(i))
            dst.pages[0:0] = pages_of_sources(i)
            with pytest.raises(TypeError, match='only pikepdf pages'):
                dst.pages.extend(itertools.chain(pages_of_sources(i), [42]))
            with pytest.raises(TypeError, match='only pikepdf pages'):
                dst.pages[0:0] = itertools.chain(pages_of_sources(i), [None])

    def other_direction(k):
        # Each source also takes pages from the destination, so that the
        # locks of the same Pdfs are wanted in the opposite order.
        for _ in range(rounds):
            sources[k].pages.extend(page for page in dst.pages[0:1])
            del sources[k].pages[-1]

    run_threads(
        *[lambda i=i: extend(i) for i in range(4)],
        *[lambda k=k: other_direction(k) for k in range(3)],
        lambda: churn_pages(sources[0], 100),
    )

    assert_page_tree_sound(dst, 1 + 4 * rounds * 2 * len(sources))
    for source in sources:
        assert_page_tree_sound(source, 2)


def introspect(pdf):
    """Read a Pdf through the bindings of the Pdf class itself."""
    xref = pdf.get_xref_table()
    first_page = pdf.pages[0].obj.objgen
    return (
        pdf.pdf_version,
        pdf.extension_level,
        pdf.is_encrypted,
        pdf.is_linearized,
        pdf.user_password_matched,
        pdf.owner_password_matched,
        pdf.conversion_mode,
        sorted(pdf._encryption_data),
        pdf._allow_extract,
        pdf._allow_print_highres,
        sorted(
            (objgen, entry.type, entry.offset, entry.obj_stream_number, repr(entry))
            for objgen, entry in xref.items()
        ),
        len(pdf.objects),
        pdf.get_object(first_page).objgen,
        pdf.get_object(*first_page).unparse(resolved=True),
        repr(pdf.pages),
        pdf.pages.from_objgen(first_page).obj.objgen,
        pdf.pages.from_objgen(*first_page).index,
        pdf.pages.p(1).obj.objgen,
        [page.obj.objgen for page in pdf.pages[::-1]],
        [page.obj.objgen for page in pdf.pages],
        pdf.pages.index(pdf.pages[-1]),
        pdf._count_orphaned_widgets(),
        sorted(pdf.trailer.keys()),
        pdf.Root.objgen,
        pdf.get_warnings(),
    )


@pytest.mark.parametrize('filename', ['fourpages.pdf', 'sandwich.pdf', 'form.pdf'])
def test_stress_pdf_introspection_cold(filename):
    """Threads using the Pdf class's own bindings on a freshly opened Pdf."""
    with Pdf.open(RESOURCES / filename) as serial:
        expected = introspect(serial)

    for _ in range(3):
        with Pdf.open(RESOURCES / filename) as pdf:
            results = [None] * N_THREADS

            def read(i, pdf=pdf, results=results):
                results[i] = introspect(pdf)

            run_n(read)
            assert all(result == expected for result in results)


def test_stress_save_check_and_json_while_reading():
    """Whole-document operations that call back into Python, with readers."""
    pdf = Pdf.open(RESOURCES / 'fourpages.pdf')
    expected = introspect(pdf)
    outputs = []
    progress = []
    rounds = 3

    def save(i):
        for _ in range(rounds):
            out = BytesIO()
            pdf.save(out, progress=progress.append, linearize=bool(i % 2))
            outputs.append(out)

    def check():
        for _ in range(rounds):
            assert pdf.check_pdf_syntax(progress=progress.append) == []

    def json():
        for _ in range(rounds):
            out = BytesIO()
            pdf.write_qpdf_json(out)
            assert out.getvalue().startswith(b'{')

    def read():
        for _ in range(rounds):
            assert introspect(pdf) == expected

    run_threads(lambda: save(0), lambda: save(1), check, json, read, read)

    assert len(outputs) == 2 * rounds
    assert progress and all(0 <= percent <= 100 for percent in progress)
    for out in outputs:
        out.seek(0)
        with Pdf.open(out) as reopened:
            assert len(reopened.pages) == 4


def test_stress_make_indirect_from_python_values():
    """make_indirect() of Python values and of objects, from many threads."""
    pdf = Pdf.new()
    rounds = 30
    made = [[] for _ in range(N_THREADS)]

    def make(i):
        for n in range(rounds):
            from_dict = pdf.make_indirect({'/Thread': i, '/N': n})
            from_list = pdf.make_indirect([i, n])
            from_object = pdf.make_indirect(Dictionary(Thread=i, N=n))
            again = pdf.make_indirect(from_object)
            assert again.objgen == from_object.objgen
            made[i].append((n, from_dict, from_list, from_object))
            assert pdf.get_object(from_list.objgen)[1] == n

    run_n(make)

    objgens = set()
    for i, items in enumerate(made):
        assert len(items) == rounds
        for n, from_dict, from_list, from_object in items:
            assert from_dict.Thread == i and from_dict.N == n
            assert list(from_list) == [i, n]
            assert from_object.Thread == i and from_object.N == n
            for obj in (from_dict, from_list, from_object):
                assert obj.is_indirect and obj.is_owned_by(pdf)
                objgens.add(obj.objgen)
    assert len(objgens) == 3 * N_THREADS * rounds


def test_stress_conversion_mode_property():
    """Pdf.conversion_mode is set and read from many threads."""
    pdf = Pdf.new()
    modes = ['implicit', 'explicit', None]
    stop = threading.Event()

    def flip(i):
        for n in range(200):
            pdf.conversion_mode = modes[(i + n) % 3]
            assert pdf.conversion_mode in modes
            with pytest.raises(ValueError):
                pdf.conversion_mode = 'neither'
        stop.set()

    def read():
        while not stop.is_set():
            assert pdf.conversion_mode in modes
            assert len(pdf.pages) == 0

    run_threads(*[lambda i=i: flip(i) for i in range(4)], read, read)
