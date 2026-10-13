# SPDX-FileCopyrightText: 2024 James R. Barlow
# SPDX-License-Identifier: MPL-2.0

"""Thread safety tests for pikepdf under free-threaded Python.

These tests verify that concurrent operations on pikepdf objects do not
crash or corrupt state. On GIL-enabled builds, the per-QPDF locks are
no-ops, so these tests exercise the code paths without contention.

The stress tests in the second half of this file start their threads from a
common barrier so that the operations overlap, and assert on invariants that
must hold however the threads interleave. They are the tests that the
ThreadSanitizer CI job (.github/workflows/tsan.yml) runs, so keep each one
short: TSan slows the interpreter by roughly an order of magnitude.
"""

from __future__ import annotations

import queue
import sys
import sysconfig
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from io import BytesIO
from pathlib import Path

import pytest

import pikepdf
from pikepdf import (
    Annotation,
    Array,
    AttachedFileSpec,
    Dictionary,
    Name,
    NameTree,
    NumberTree,
    Object,
    Pdf,
    Stream,
    String,
    Token,
    TokenFilter,
    TokenType,
)
from pikepdf._core import StreamParser

RESOURCES = Path(__file__).parent / "resources"

# A deadlock must fail the test rather than hang the run. method='thread' is
# used because a deadlocked thread never returns to the interpreter to service
# a signal.
pytestmark = pytest.mark.timeout(120, method='thread')

N_THREADS = 8
JOIN_TIMEOUT = 60
# Whether the per-Pdf locks do anything. They are compiled in on a free-threaded
# build, and stay in force there even if an extension module that does not
# support free threading has switched the GIL back on at import.
LOCKS_ENABLED = bool(sysconfig.get_config_var('Py_GIL_DISABLED'))


@pytest.fixture
def sample_pdf():
    return Pdf.open(RESOURCES / "graph.pdf")


def test_concurrent_page_reads(sample_pdf):
    """Multiple threads reading pages from the same Pdf concurrently."""
    errors = []
    n_pages = len(sample_pdf.pages)

    def read_pages():
        try:
            for _ in range(50):
                for i in range(n_pages):
                    page = sample_pdf.pages[i]
                    _ = page.mediabox
        except Exception as e:
            errors.append(e)

    threads = [threading.Thread(target=read_pages) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors, f"Errors during concurrent reads: {errors}"


def test_concurrent_object_access(sample_pdf):
    """Multiple threads reading object properties concurrently."""
    errors = []
    root = sample_pdf.Root

    def read_root():
        try:
            for _ in range(100):
                _ = repr(root)
                _ = len(root.keys())
                if Name.Pages in root:
                    _ = root.Pages
        except Exception as e:
            errors.append(e)

    threads = [threading.Thread(target=read_root) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors, f"Errors during concurrent object access: {errors}"


def test_concurrent_page_add_remove():
    """Concurrent page additions to the same Pdf."""
    pdf = Pdf.new()
    errors = []

    def add_pages():
        try:
            for _ in range(20):
                pdf.add_blank_page()
        except Exception as e:
            errors.append(e)

    threads = [threading.Thread(target=add_pages) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors, f"Errors during concurrent page add: {errors}"
    assert len(pdf.pages) == 80


def test_concurrent_cross_pdf_page_copy():
    """Concurrent page copies between independent Pdf pairs."""
    errors = []

    def copy_between():
        try:
            src = Pdf.new()
            src.add_blank_page()
            dst = Pdf.new()
            for _ in range(20):
                dst.pages.append(src.pages[0])
        except Exception as e:
            errors.append(e)

    threads = [threading.Thread(target=copy_between) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors, f"Errors during concurrent cross-pdf page copy: {errors}"


def test_concurrent_copy_foreign():
    """Concurrent copy_foreign of objects between Pdfs."""
    errors = []

    def do_copy_foreign():
        try:
            src = Pdf.new()
            # Create a non-trivial indirect object tree in src
            src_dict = src.make_indirect(
                Dictionary(
                    Key1=Array([1, 2, 3]),
                    Key2=Dictionary(Nested=Name.Value),
                )
            )
            src_stream = src.make_stream(b"hello world")

            dst = Pdf.new()
            for _ in range(20):
                copied_dict = dst.copy_foreign(src_dict)
                copied_stream = dst.copy_foreign(src_stream)
                assert Name.Key1 in copied_dict
                assert bytes(copied_stream) == b"hello world"
        except Exception as e:
            errors.append(e)

    threads = [threading.Thread(target=do_copy_foreign) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors, f"Errors during concurrent copy_foreign: {errors}"


def test_concurrent_with_same_owner_as():
    """Concurrent with_same_owner_as across Pdfs."""
    errors = []

    def do_with_same_owner():
        try:
            pdf_a = Pdf.new()
            pdf_b = Pdf.new()
            obj_a = pdf_a.make_indirect(Dictionary(Source=Name.A))
            obj_b = pdf_b.make_indirect(Dictionary(Source=Name.B))

            for _ in range(20):
                # Copy obj_a into pdf_b's ownership
                in_b = obj_a.with_same_owner_as(obj_b)
                assert in_b.Source == Name.A
                assert in_b.is_owned_by(pdf_b)

                # Copy obj_b into pdf_a's ownership
                in_a = obj_b.with_same_owner_as(obj_a)
                assert in_a.Source == Name.B
                assert in_a.is_owned_by(pdf_a)

                # Same owner is a no-op
                same = obj_a.with_same_owner_as(obj_a)
                assert same.Source == Name.A
        except Exception as e:
            errors.append(e)

    threads = [threading.Thread(target=do_with_same_owner) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors, f"Errors during concurrent with_same_owner_as: {errors}"


def test_lock_context_manager():
    """Test that the Pdf.lock() context manager works correctly."""
    pdf = Pdf.new()

    # Basic lock/unlock
    with pdf.lock():
        pdf.add_blank_page()
    assert len(pdf.pages) == 1

    # Re-entrant locking
    with pdf.lock():
        with pdf.lock():
            pdf.add_blank_page()
    assert len(pdf.pages) == 2


def test_concurrent_metadata_access():
    """Concurrent reads and writes to docinfo."""
    pdf = Pdf.new()
    errors = []

    def write_metadata(thread_id):
        try:
            for i in range(20):
                pdf.docinfo[Name(f"/Thread{thread_id}_{i}")] = f"value_{i}"
        except Exception as e:
            errors.append(e)

    threads = [threading.Thread(target=write_metadata, args=(i,)) for i in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors, f"Errors during concurrent metadata: {errors}"


def test_concurrent_save(tmp_path):
    """Concurrent saves of independent Pdfs."""
    errors = []

    def save_pdf(thread_id):
        try:
            pdf = Pdf.new()
            pdf.add_blank_page()
            pdf.save(tmp_path / f"thread_{thread_id}.pdf")
        except Exception as e:
            errors.append(e)

    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = [executor.submit(save_pdf, i) for i in range(8)]
        for f in as_completed(futures):
            f.result()

    assert not errors
    assert len(list(tmp_path.glob("*.pdf"))) == 8


# ---------------------------------------------------------------------------
# Stress tests
# ---------------------------------------------------------------------------


def run_threads(*targets):
    """Run each target in its own thread, released together from a barrier.

    Re-raises the first exception raised by any target, and fails if a thread
    has not finished within JOIN_TIMEOUT seconds, which indicates a deadlock.
    """
    barrier = threading.Barrier(len(targets))
    errors = []

    def runner(target):
        try:
            barrier.wait(JOIN_TIMEOUT)
            target()
        except BaseException as e:  # pylint: disable=broad-exception-caught
            errors.append(e)

    # Daemon threads, so that a deadlocked thread cannot also hang interpreter
    # shutdown after the test has been reported as failed.
    threads = [
        threading.Thread(target=runner, args=(target,), daemon=True)
        for target in targets
    ]
    for t in threads:
        t.start()
    deadline = time.monotonic() + JOIN_TIMEOUT
    for t in threads:
        t.join(max(0.0, deadline - time.monotonic()))
    stuck = sum(t.is_alive() for t in threads)
    assert not stuck, f"{stuck} thread(s) still running after {JOIN_TIMEOUT}s"
    if errors:
        raise errors[0]


def run_n(target, n=N_THREADS):
    """Run target(thread_index) in n threads."""
    run_threads(*[lambda i=i: target(i) for i in range(n)])


def describe(pdf):
    """Read most of a Pdf through a variety of accessors, as plain values."""
    result = []
    for page in pdf.pages:
        result.append(
            (
                [float(v) for v in page.mediabox],
                sorted(page.obj.keys()),
                page.obj.objgen,
                page.obj.unparse(resolved=True),
                page.Contents.read_bytes(),
                page.Contents.read_raw_bytes(),
                repr(page.Resources),
                page.index,
            )
        )
    result.append(repr(pdf.Root))
    result.append(sorted(pdf.trailer.keys()))
    result.append(
        [obj.unparse() if isinstance(obj, Object) else obj for obj in pdf.objects]
    )
    return result


@pytest.mark.parametrize('filename', ['fourpages.pdf', 'graph.pdf', 'sandwich.pdf'])
def test_stress_cold_reads_match_serial(filename):
    """Threads reading a freshly opened Pdf all see what a serial reader sees.

    qpdf resolves objects lazily, so the first reads of a Pdf mutate its object
    cache. The expected value is taken from a second copy so that the shared
    Pdf is still cold when the threads start.
    """
    with Pdf.open(RESOURCES / filename) as reference:
        expected = describe(reference)

    for _ in range(3):
        with Pdf.open(RESOURCES / filename) as pdf:
            results = [None] * N_THREADS

            def read(i, pdf=pdf, results=results):
                results[i] = describe(pdf)

            run_n(read)
            for result in results:
                assert result == expected


def decoded_or_none(stream):
    """Decoded stream data, or None for a filter that pikepdf cannot decode."""
    try:
        return stream.read_bytes()
    except pikepdf.PdfError:
        return None


def test_stress_stream_reads():
    """Concurrent decoding of the same streams yields the same bytes."""
    with Pdf.open(RESOURCES / 'sandwich.pdf') as reference:
        expected = {
            obj.objgen: (decoded_or_none(obj), obj.read_raw_bytes())
            for obj in reference.objects
            if isinstance(obj, Stream)
        }
    assert sum(cooked is not None for cooked, _raw in expected.values()) >= 3

    with Pdf.open(RESOURCES / 'sandwich.pdf') as pdf:
        streams = [obj for obj in pdf.objects if isinstance(obj, Stream)]

        def read(i):
            for _ in range(3):
                # Each thread starts at a different stream
                for n in range(len(streams)):
                    stream = streams[(n + i) % len(streams)]
                    cooked, raw = expected[stream.objgen]
                    assert decoded_or_none(stream) == cooked
                    assert bytes(stream.get_raw_stream_buffer()) == raw
                    if cooked is not None:
                        assert bytes(stream.get_stream_buffer()) == cooked
                    assert int(stream.Length) == len(raw)

        run_n(read)


def test_stress_stream_write_and_read():
    """A stream being rewritten is always read as one whole version."""
    pdf = Pdf.new()
    versions = [bytes([65 + n]) * (1000 + n) for n in range(N_THREADS)]
    stream = pdf.make_stream(versions[0])

    def work(i):
        for _ in range(100):
            stream.write(versions[i])
            data = stream.read_bytes()
            assert data in versions, (len(data), data[:1])

    run_n(work)
    assert stream.read_bytes() in versions


def test_stress_same_dictionary_distinct_keys():
    """Threads adding their own keys to one dictionary lose no updates."""
    pdf = Pdf.new()
    d = pdf.make_indirect(Dictionary())
    per_thread = 150

    def work(i):
        for n in range(per_thread):
            d[f'/T{i}_{n}'] = n
            assert d[f'/T{i}_{n}'] == n
            if n % 3 == 0:
                # A key that is added and then removed again
                d[f'/Tmp{i}'] = Array([i, n])
                del d[f'/Tmp{i}']
            assert f'/T{i}_0' in d
            len(d)
            d.keys()

    run_n(work)
    assert len(d) == N_THREADS * per_thread
    assert set(d.keys()) == {
        f'/T{i}_{n}' for i in range(N_THREADS) for n in range(per_thread)
    }
    for i in range(N_THREADS):
        for n in range(per_thread):
            assert d[f'/T{i}_{n}'] == n


def test_stress_same_key_never_torn():
    """Threads overwriting one key always read back a complete value."""
    pdf = Pdf.new()
    d = pdf.make_indirect(Dictionary(Value=Array([0, 0, 0])))
    pdf.Root.Shared = d

    def work(i):
        for _ in range(200):
            d.Value = Array([i, i, i])
            a, b, c = (int(v) for v in d.Value)
            assert a == b == c
            assert 0 <= a < N_THREADS
            # The same object reached by another route
            assert len(pdf.Root.Shared.Value) == 3

    run_n(work)
    assert len(d) == 1


def test_stress_same_array():
    """Threads appending to and reading one array lose no items."""
    pdf = Pdf.new()
    a = pdf.make_indirect(Array())
    per_thread = 150

    def work(i):
        for n in range(per_thread):
            a.append(i * 1000 + n)
            length = len(a)
            assert length >= n + 1
            # Arrays only grow in this test, so any index below a length that
            # was observed stays valid.
            assert 0 <= int(a[length - 1]) < N_THREADS * 1000
            if n % 10 == 0:
                seen = [int(v) for v in a]
                assert len(seen) >= length

    run_n(work)
    values = sorted(int(v) for v in a)
    assert values == sorted(
        i * 1000 + n for i in range(N_THREADS) for n in range(per_thread)
    )


def test_stress_different_objects_same_pdf():
    """Threads each creating and mutating their own objects in one Pdf."""
    pdf = Pdf.new()
    created = [[] for _ in range(N_THREADS)]

    def work(i):
        for n in range(40):
            d = pdf.make_indirect(Dictionary(Owner=i, Seq=n, Items=Array()))
            s = pdf.make_stream(f'{i}:{n}'.encode(), Owner=i)
            for k in range(5):
                d.Items.append(k)
            d.Stream = s
            pdf.Root[f'/Obj{i}_{n}'] = d
            created[i].append((d, s))

    run_n(work)

    objgens = set()
    for i, items in enumerate(created):
        assert len(items) == 40
        for n, (d, s) in enumerate(items):
            assert d.Owner == i and d.Seq == n
            assert [int(v) for v in d.Items] == list(range(5))
            assert s.read_bytes() == f'{i}:{n}'.encode()
            assert d.Stream.objgen == s.objgen
            assert pdf.Root[f'/Obj{i}_{n}'].objgen == d.objgen
            objgens.add(d.objgen)
            objgens.add(s.objgen)
    # Every object got its own object number
    assert len(objgens) == N_THREADS * 40 * 2

    out = BytesIO()
    pdf.save(out)
    out.seek(0)
    with Pdf.open(out) as reopened:
        for i in range(N_THREADS):
            for n in range(40):
                assert reopened.Root[f'/Obj{i}_{n}'].Seq == n


def test_stress_lock_makes_compound_operation_atomic():
    """Pdf.lock() serializes a read-modify-write, and is re-entrant.

    On a GIL-enabled build Pdf.lock() is documented to be a no-op and the
    interpreter may switch threads between the read and the write, so the exact
    total is only guaranteed on a free-threaded build.
    """
    pdf = Pdf.new()
    pdf.Root.Counter = 0
    per_thread = 200

    def work(i):
        for n in range(per_thread):
            with pdf.lock():
                value = int(pdf.Root.Counter)
                if n % 2:
                    with pdf.lock():
                        pdf.Root.Counter = value + 1
                else:
                    pdf.Root.Counter = value + 1

    run_n(work)
    total = int(pdf.Root.Counter)
    assert 0 < total <= N_THREADS * per_thread
    if LOCKS_ENABLED:
        assert total == N_THREADS * per_thread

    # The lock was fully released: another thread can take it.
    acquired = []

    def take():
        with pdf.lock():
            acquired.append(True)

    run_threads(take)
    assert acquired == [True]


def test_stress_lock_released_after_exception():
    """An exception raised inside a locked method does not leave it locked."""
    pdf = Pdf.new()
    pdf.add_blank_page()

    def provoke(i):
        for _ in range(50):
            with pytest.raises(IndexError):
                pdf.pages[100 + i]
            with pytest.raises((KeyError, AttributeError)):
                pdf.Root.NoSuchKey
            with pytest.raises(TypeError):
                pdf.pages.append(Dictionary())
            with pytest.raises(ValueError):
                with pdf.lock():
                    raise ValueError('inside lock')
            assert len(pdf.pages) == 1

    run_n(provoke)


def test_stress_page_list_insert_delete():
    """Concurrent page insertion, deletion and iteration keep the tree whole."""
    pdf = Pdf.new()
    rounds = 15
    stop = threading.Event()

    def mutate(i):
        for n in range(rounds):
            # Two pages in, one page out: the list can never be empty when a
            # thread deletes.
            page = pdf.add_blank_page(page_size=(100 + i, 100 + n))
            page.obj.Marker = i
            other = Pdf.new()
            other.add_blank_page(page_size=(300 + i, 300 + n))
            pdf.pages.insert(0, other.pages[0])
            del pdf.pages[0]

    def observe():
        while not stop.is_set():
            count = len(pdf.pages)
            assert 0 <= count <= 2 * N_THREADS * rounds
            for page in pdf.pages:
                box = page.mediabox
                assert len(box) == 4
            try:
                pdf.pages[count - 1]
            except IndexError:
                pass  # Deleted since len() was called

    # The observers run until the last mutator has finished
    remaining = [N_THREADS]
    remaining_lock = threading.Lock()

    def mutator(i):
        try:
            mutate(i)
        finally:
            with remaining_lock:
                remaining[0] -= 1
                if remaining[0] == 0:
                    stop.set()

    run_threads(*[lambda i=i: mutator(i) for i in range(N_THREADS)], observe, observe)

    assert len(pdf.pages) == N_THREADS * rounds
    assert int(pdf.Root.Pages.Count) == N_THREADS * rounds
    objgens = {page.obj.objgen for page in pdf.pages}
    assert len(objgens) == N_THREADS * rounds
    for index, page in enumerate(pdf.pages):
        assert page.index == index
        assert len(page.mediabox) == 4

    out = BytesIO()
    pdf.save(out)
    out.seek(0)
    with Pdf.open(out) as reopened:
        assert len(reopened.pages) == N_THREADS * rounds


def pdf_with_indirect_page_attributes(n_pages=8):
    """A saved Pdf whose page boxes and rotation are separate indirect objects.

    Such objects are not resolved when the file is opened, so the first read
    of a page attribute makes qpdf load them and update its object cache.
    """
    pdf = Pdf.new()
    for n in range(n_pages):
        page = pdf.add_blank_page(page_size=(100 + n, 200 + n))
        for box in ('/MediaBox', '/CropBox', '/TrimBox'):
            page.obj[box] = pdf.make_indirect(Array([0, 0, 100 + n, 200 + n]))
        page.obj.Rotate = pdf.make_indirect(Object.parse(b'90'))
        page.obj.Resources = pdf.make_indirect(
            Dictionary(XObject=pdf.make_indirect(Dictionary()))
        )
        page.Contents = pdf.make_stream(f'{n} 0 0 {n} 0 0 cm'.encode())
    out = BytesIO()
    pdf.save(out)
    return out.getvalue()


def test_stress_cold_page_attributes():
    """Page attribute accessors on different pages of a freshly opened Pdf."""
    data = pdf_with_indirect_page_attributes()
    for _ in range(4):
        with Pdf.open(BytesIO(data)) as pdf:
            pages = list(pdf.pages)

            def read(i, pages=pages):
                for k in range(len(pages)):
                    # Each thread starts at a different page
                    n = (i + k) % len(pages)
                    page = pages[n]
                    box = [0.0, 0.0, 100.0 + n, 200.0 + n]
                    assert [float(v) for v in page.mediabox] == box
                    assert [float(v) for v in page.cropbox] == box
                    assert [float(v) for v in page.trimbox] == box
                    assert [float(v) for v in page.artbox] == box
                    assert page.rotation == 90
                    assert len(page.get_images()) == 0
                    assert page.form_xobjects == {}
                    assert page.resources is not None
                    assert page.label == str(n + 1)
                    assert page.index == n
                    stream = page.as_form_xobject()
                    assert stream.read_bytes() == f'{n} 0 0 {n} 0 0 cm'.encode()

            run_n(read)


def test_stress_page_attributes_same_page():
    """Reading and writing the boxes and rotation of one page."""
    pdf = Pdf.new()
    page = pdf.add_blank_page(page_size=(100, 100))
    boxes = [[0.0, 0.0, 100.0 + i, 100.0 + i] for i in range(N_THREADS)]

    def work(i):
        for n in range(60):
            page.mediabox = boxes[i]
            page.cropbox = boxes[i]
            assert [float(v) for v in page.mediabox] in boxes
            assert [float(v) for v in page.cropbox] in boxes
            assert [float(v) for v in page.trimbox] in boxes
            page.rotate(90, relative=True)
            assert page.rotation % 90 == 0
            page.contents_add(b'q Q', prepend=bool(n % 2))
            if n % 20 == 0:
                page.contents_coalesce()

    run_n(work)
    # Every relative rotation was applied: 8 threads * 60 quarter turns
    assert page.rotation == (N_THREADS * 60 * 90) % 360
    page.contents_coalesce()
    assert page.Contents.read_bytes().count(b'q Q') == N_THREADS * 60


def pdf_with_indirect_values(n_objects=24):
    """A saved Pdf of dictionaries whose every value is its own indirect object.

    Nothing below the catalog is resolved when the file is opened, so almost
    any accessor makes qpdf load objects and update its object cache.
    """
    pdf = Pdf.new()
    pdf.add_blank_page()
    items = Array()
    for n in range(n_objects):
        d = Dictionary(
            Int=pdf.make_indirect(Object.parse(str(n).encode())),
            Real=pdf.make_indirect(Object.parse(b'1.5')),
            Bool=pdf.make_indirect(Object.parse(b'true')),
            Name=pdf.make_indirect(Name(f'/N{n}')),
            Str=pdf.make_indirect(String(f's{n}')),
            Rect=pdf.make_indirect(Array([0, 0, n, n])),
            Sub=pdf.make_indirect(Dictionary(Leaf=pdf.make_indirect(Array([n])))),
            Data=pdf.make_stream(f'data {n}'.encode()),
        )
        items.append(pdf.make_indirect(d))
    pdf.Root.Items = pdf.make_indirect(items)
    out = BytesIO()
    pdf.save(out)
    return out.getvalue()


def test_stress_cold_object_accessors():
    """A broad sweep of Object accessors on distinct objects of a cold Pdf."""
    data = pdf_with_indirect_values()
    for _ in range(3):
        with Pdf.open(BytesIO(data)) as pdf:
            items = pdf.Root.Items
            count = len(items)

            def read(i, items=items, count=count):
                for k in range(count):
                    n = (i * 3 + k) % count
                    d = items[n]
                    assert d.get('/Int') == n
                    assert d.get(Name.Missing, 'default') == 'default'
                    assert d.get_int('/Int') == n
                    assert d.get_float('/Real') == 1.5
                    assert d.get_bool('/Bool') is True
                    assert d.Name == Name(f'/N{n}')
                    assert d.get_bytes('/Str') == f's{n}'.encode()
                    assert len(d.get_dict('/Sub')) == 1
                    assert len(d.get_list('/Rect')) == 4
                    assert d.get_decimal('/Real') == 1.5
                    assert d.get_str('/Str') == f's{n}'
                    assert d.get_raw('/Int') == n
                    assert d.Rect.is_rectangle
                    assert [int(v) for v in d.Rect.as_list()] == [0, 0, n, n]
                    assert d.Sub.Leaf[0] == n
                    assert d[pikepdf.NamePath.Sub.Leaf][0] == n
                    assert set(d.keys()) == {
                        '/Int',
                        '/Real',
                        '/Bool',
                        '/Name',
                        '/Str',
                        '/Rect',
                        '/Sub',
                        '/Data',
                    }
                    assert len(list(d.items())) == 8
                    assert len(list(d.values())) == 8
                    assert len(d.as_dict()) == 8
                    assert '/Int' in d and Name.Sub in d
                    assert d.Data.read_bytes() == f'data {n}'.encode()
                    assert bytes(d.Data.get_stream_buffer()) == f'data {n}'.encode()
                    assert d.Data.stream_dict.Length > 0
                    assert d == d and d != items[(n + 1) % count]
                    assert d.is_indirect and d.objgen[0] > 0
                    assert d.is_owned_by(pdf) and d.same_owner_as(items)
                    assert b'/Int' in d.unparse(resolved=True) and b'/Int' in d.to_json(
                        dereference=True
                    )
                    assert repr(d).startswith('<pikepdf.Dictionary')
                    assert len(d.Rect.wrap_in_array()) == 4
                    copy = d.copy()
                    assert copy.Int == n and not copy.is_indirect
                    merged = Dictionary(Extra=1)
                    merged.update(d)
                    assert merged.Int == n and len(merged) == 9

            run_n(read)


def test_stress_object_handoff_between_threads():
    """Objects built in one thread are finished and attached in another."""
    pdf = Pdf.new()
    q = queue.Queue()
    per_producer = 60
    producers = N_THREADS // 2
    attached = []
    attached_lock = threading.Lock()

    def produce(i):
        for n in range(per_producer):
            d = Dictionary(Producer=i, Seq=n, Items=Array([n]))
            d.Text = String(f'{i}/{n}')
            q.put(d)
        q.put(None)

    def consume():
        finished = 0
        while finished < 1:
            d = q.get(timeout=JOIN_TIMEOUT)
            if d is None:
                finished += 1
                continue
            # Mutate an object another thread created, then give it to the Pdf
            d.Items.append(int(d.Seq) + 1)
            d.Consumer = threading.get_ident() % 1000
            ind = pdf.make_indirect(d)
            pdf.Root[f'/P{int(d.Producer)}_{int(d.Seq)}'] = ind
            with attached_lock:
                attached.append(ind)

    run_threads(
        *[lambda i=i: produce(i) for i in range(producers)],
        *[consume for _ in range(producers)],
    )

    assert len(attached) == producers * per_producer
    for i in range(producers):
        for n in range(per_producer):
            d = pdf.Root[f'/P{i}_{n}']
            assert d.Producer == i and d.Seq == n
            assert [int(v) for v in d.Items] == [n, n + 1]
            assert str(d.Text) == f'{i}/{n}'
            assert d.is_owned_by(pdf)


def test_stress_unowned_scalars_shared_between_pdfs():
    """Module-level scalars inserted into many Pdfs at once stay reusable."""
    shared_name = Name.SharedValue
    shared_string = String('shared')
    pdfs = [Pdf.new() for _ in range(N_THREADS)]

    def work(i):
        pdf = pdfs[i]
        for n in range(100):
            pdf.Root[f'/N{n}'] = shared_name
            pdf.Root[f'/S{n}'] = shared_string
            pdf.Root[f'/A{n}'] = Array([shared_name, shared_string, n])
            assert pdf.Root[f'/N{n}'] == Name.SharedValue
            assert str(pdf.Root[f'/S{n}']) == 'shared'

    run_n(work)
    assert shared_name == Name.SharedValue
    assert str(shared_string) == 'shared'
    for pdf in pdfs:
        assert len(pdf.Root.keys()) == 300 + 2  # /Type and /Pages
        assert pdf.Root.A99[2] == 99


def test_stress_two_pdfs_copy_pages_both_ways():
    """Two threads copying pages between the same two Pdfs do not deadlock."""
    a = Pdf.new()
    b = Pdf.new()
    for n in range(3):
        a.add_blank_page(page_size=(100, 100 + n))
        b.add_blank_page(page_size=(200, 200 + n))
    rounds = 25

    def a_to_b():
        for n in range(rounds):
            b.pages.append(a.pages[n % 3])

    def b_to_a():
        for n in range(rounds):
            a.pages.append(b.pages[n % 3])

    run_threads(a_to_b, b_to_a, a_to_b, b_to_a)

    assert len(a.pages) == 3 + 2 * rounds
    assert len(b.pages) == 3 + 2 * rounds
    for pdf in (a, b):
        for page in pdf.pages:
            assert page.obj.is_owned_by(pdf)
            assert float(page.mediabox[2]) in (100.0, 200.0)
        out = BytesIO()
        pdf.save(out)


def test_stress_two_pdfs_extend_both_ways():
    """pages.extend() in opposite directions takes the two locks in one order."""
    a = Pdf.new()
    b = Pdf.new()
    a.add_blank_page()
    b.add_blank_page()
    rounds = 4  # Each whole-document extend can double the page count

    def all_of_a_into_b():
        for _ in range(rounds):
            b.pages.extend(a.pages)

    def all_of_b_into_a():
        for _ in range(rounds):
            a.pages.extend(b.pages)

    def some_of_a_into_b():
        for _ in range(rounds):
            b.pages.extend(a.pages[0:1])
            b.pages[0:0] = a.pages[0:1]

    def some_of_b_into_a():
        for _ in range(rounds):
            a.pages.extend(b.pages[0:1])
            a.pages[0:0] = b.pages[0:1]

    run_threads(all_of_a_into_b, all_of_b_into_a, some_of_a_into_b, some_of_b_into_a)

    for pdf in (a, b):
        assert len(pdf.pages) == int(pdf.Root.Pages.Count) >= 1 + 2 * rounds
        assert all(page.obj.is_owned_by(pdf) for page in pdf.pages)
        assert len({page.obj.objgen for page in pdf.pages}) == len(pdf.pages)


def test_stress_two_pdfs_copy_foreign_and_compare_both_ways():
    """Opposite-direction copy_foreign, equality and with_same_owner_as."""
    a = Pdf.new()
    b = Pdf.new()
    obj_a = a.make_indirect(Dictionary(Source=Name.A, Items=Array([1, 2, 3])))
    obj_b = b.make_indirect(Dictionary(Source=Name.B, Items=Array([1, 2, 3])))
    stream_a = a.make_stream(b'from a')
    stream_b = b.make_stream(b'from b')

    def forwards(_i):
        for _ in range(40):
            copied = b.copy_foreign(obj_a)
            assert copied.Source == Name.A
            assert copied.is_owned_by(b)
            assert b.copy_foreign(stream_a).read_bytes() == b'from a'
            assert obj_a != obj_b
            assert obj_a.Items == obj_b.Items
            assert obj_a.with_same_owner_as(obj_b).is_owned_by(b)

    def backwards(_i):
        for _ in range(40):
            copied = a.copy_foreign(obj_b)
            assert copied.Source == Name.B
            assert copied.is_owned_by(a)
            assert a.copy_foreign(stream_b).read_bytes() == b'from b'
            assert obj_b != obj_a
            assert obj_b.Items == obj_a.Items
            assert obj_b.with_same_owner_as(obj_a).is_owned_by(a)

    run_threads(
        *[lambda i=i: (forwards if i % 2 else backwards)(i) for i in range(N_THREADS)]
    )
    assert obj_a.Source == Name.A and obj_b.Source == Name.B
    assert obj_a.is_owned_by(a) and obj_b.is_owned_by(b)


def test_stress_source_pdf_mutated_while_copied_from():
    """Copying from a Pdf while another thread mutates it gives whole objects."""
    src = Pdf.new()
    src_obj = src.make_indirect(Dictionary(Items=Array(), Count=0))
    rounds = 150
    stop = threading.Event()

    def mutate():
        try:
            for n in range(rounds):
                with src.lock():
                    src_obj.Items.append(n)
                    src_obj.Count = n + 1
        finally:
            stop.set()

    def copy():
        dst = Pdf.new()
        while not stop.is_set():
            copied = dst.copy_foreign(src_obj)
            count = int(copied.Count)
            # The copy was taken under the source's lock, so it is consistent
            assert len(copied.Items) == count
            assert [int(v) for v in copied.Items] == list(range(count))

    run_threads(mutate, copy, copy, copy)
    assert int(src_obj.Count) == rounds


def test_stress_pdf_dropped_while_objects_in_use():
    """Objects outliving their Pdf in another thread fail cleanly, if at all."""
    gone = (pikepdf.PdfError, pikepdf.DeletedObjectError, ValueError, RuntimeError)
    for _ in range(20):
        pdf = Pdf.open(RESOURCES / 'fourpages.pdf')
        page_objs = [page.obj for page in pdf.pages]
        root = pdf.Root
        holder = [pdf]
        del pdf

        def read(page_objs=page_objs, root=root):
            for _ in range(30):
                for obj in page_objs:
                    try:
                        obj.keys()
                        repr(obj)
                        obj.get('/MediaBox')
                    except gone:
                        pass  # The Pdf is gone; an exception is acceptable
                try:
                    repr(root)
                except gone:
                    pass

        def drop(holder=holder):
            holder.pop()

        run_threads(read, read, drop, read)


class ReenteringFilter(TokenFilter):
    """Token filter that calls back into the Pdf being filtered."""

    def __init__(self, pdf, page_index):
        super().__init__()
        self.pdf = pdf
        self.page_index = page_index
        self.tokens = 0

    def handle_token(self, token):
        self.tokens += 1
        if self.tokens % 8 == 0:
            # Re-enter pikepdf on the Pdf whose lock the filtering call holds
            assert len(self.pdf.pages) == 4
            page = self.pdf.pages[self.page_index]
            assert len(page.mediabox) == 4
            with self.pdf.lock():
                assert '/Contents' in page.obj
        if token.type_ == TokenType.integer:
            return [token, Token(TokenType.space, b' ')]
        return token


def test_stress_token_filter_reenters_pdf():
    """Token filters on several pages of one Pdf, each re-entering the Pdf."""
    with Pdf.open(RESOURCES / 'fourpages.pdf') as reference:
        expected = [
            page.get_filtered_contents(ReenteringFilter(reference, n))
            for n, page in enumerate(reference.pages)
        ]
    assert all(expected)

    with Pdf.open(RESOURCES / 'fourpages.pdf') as pdf:

        def work(i):
            for n in range(6):
                index = (i + n) % 4
                tf = ReenteringFilter(pdf, index)
                assert pdf.pages[index].get_filtered_contents(tf) == expected[index]
                assert tf.tokens > 0

        run_n(work)


class ReenteringParser(StreamParser):
    """Stream parser that calls back into the Pdf being parsed."""

    def __init__(self, pdf):
        super().__init__()
        self.pdf = pdf
        self.objects = []
        self.eof = False

    def handle_object(self, obj, offset, length):
        self.objects.append(obj.unparse() if isinstance(obj, Object) else repr(obj))
        if len(self.objects) % 8 == 0:
            assert len(self.pdf.pages) == 4
            assert self.pdf.Root.Pages.Count == 4
            self.pdf.Root.ParseTicks = len(self.objects)

    def handle_eof(self):
        self.eof = True


def test_stress_stream_parser_reenters_pdf():
    """Stream parsers on several pages of one Pdf, each re-entering the Pdf."""

    def parse(pdf, index):
        parser = ReenteringParser(pdf)
        Object._parse_stream(pdf.pages[index].Contents, parser)
        assert parser.eof
        return parser.objects

    with Pdf.open(RESOURCES / 'fourpages.pdf') as reference:
        expected = [parse(reference, n) for n in range(4)]
        instructions = [
            len(pikepdf.parse_content_stream(page)) for page in reference.pages
        ]
    assert all(expected)

    with Pdf.open(RESOURCES / 'fourpages.pdf') as pdf:

        def work(i):
            for n in range(6):
                index = (i + n) % 4
                assert parse(pdf, index) == expected[index]
                parsed = pikepdf.parse_content_stream(pdf.pages[index])
                assert len(parsed) == instructions[index]

        run_n(work)
        assert int(pdf.Root.ParseTicks) > 0


class CrossPdfFilter(TokenFilter):
    """Token filter that reads a different Pdf from the one being filtered."""

    def __init__(self, other, rendezvous):
        super().__init__()
        self.other = other
        self.rendezvous = rendezvous
        self.seen = 0

    def handle_token(self, token):
        self.seen += 1
        if self.seen == 1:
            # Wait until the other thread is inside its own filter too, so
            # that each thread holds the lock of the Pdf it is filtering.
            self.rendezvous.wait(JOIN_TIMEOUT)
        assert len(self.other.pages) == 4
        return token


@pytest.mark.xfail(
    LOCKS_ENABLED,
    strict=True,
    reason="Known limitation: a callback that holds one Pdf's lock and touches "
    "another Pdf can deadlock against a thread doing the opposite",
)
def test_stress_token_filters_cross_two_pdfs(monkeypatch):
    """Filters on two Pdfs, each reading the other Pdf from its callback.

    Thread 1 holds a's lock and wants b's; thread 2 holds b's and wants a's.
    The per-Pdf locks are only ever taken in a consistent order when a single
    call needs both, so this deadlocks on a free-threaded build.
    """
    # When this deadlocks the Pdfs stay locked by the stuck daemon threads, so
    # they are deliberately not closed, and the wait is kept short.
    monkeypatch.setattr(sys.modules[__name__], 'JOIN_TIMEOUT', 5)
    a = Pdf.open(RESOURCES / 'fourpages.pdf')
    b = Pdf.open(RESOURCES / 'fourpages.pdf')
    rendezvous = threading.Barrier(2)
    results = {}

    def filter_a_reading_b():
        tf = CrossPdfFilter(b, rendezvous)
        results['a'] = a.pages[0].get_filtered_contents(tf)

    def filter_b_reading_a():
        tf = CrossPdfFilter(a, rendezvous)
        results['b'] = b.pages[0].get_filtered_contents(tf)

    run_threads(filter_a_reading_b, filter_b_reading_a)
    assert results['a'] == results['b'] != b''


def test_stress_conversion_mode_is_per_thread():
    """explicit_conversion() in one thread does not leak into another."""
    pdf = Pdf.new()
    pdf.Root.Number = 42

    def explicit(_i):
        for _ in range(100):
            with pikepdf.explicit_conversion():
                value = pdf.Root.Number
                assert isinstance(value, pikepdf.Integer), type(value)
                with pikepdf.implicit_conversion():
                    assert type(pdf.Root.Number) is int
                assert isinstance(pdf.Root.Number, pikepdf.Integer)

    def implicit(_i):
        for _ in range(100):
            value = pdf.Root.Number
            assert type(value) is int, type(value)
            with pikepdf.implicit_conversion():
                assert type(pdf.Root.Number) is int

    run_threads(
        *[lambda i=i: (explicit if i % 2 else implicit)(i) for i in range(N_THREADS)]
    )
    assert type(pdf.Root.Number) is int


def test_stress_global_settings():
    """Module-level settings changed from several threads stay well formed."""
    from pikepdf import settings

    precision = settings.get_decimal_precision()
    limits = settings.get_qpdf_limits()
    mmap_default = pikepdf._core.get_access_default_mmap()
    nesting_values = (100, 200, 300)
    try:

        def work(i):
            pdf = Pdf.new()
            pdf.Root.Real = Array([1.5])
            for n in range(60):
                settings.set_decimal_precision(10 + (i + n) % 6)
                assert 10 <= settings.get_decimal_precision() <= 15
                # 1.5 is exact at any of these precisions
                assert float(pdf.Root.Real[0]) == 1.5
                assert pdf.Root.Real.unparse() in (b'[ 1.5 ]', b'[ 1.500000 ]')

                settings.set_qpdf_limits(parser_max_nesting=nesting_values[(i + n) % 3])
                assert settings.get_qpdf_limits()['parser_max_nesting'] in (
                    *nesting_values,
                    limits['parser_max_nesting'],
                )

                pikepdf._core.set_access_default_mmap(bool((i + n) % 2))
                assert pikepdf._core.get_access_default_mmap() in (True, False)
                with Pdf.open(RESOURCES / 'graph.pdf') as opened:
                    assert len(opened.pages) == 1

        run_n(work)
    finally:
        settings.set_decimal_precision(precision)
        settings.set_qpdf_limits(parser_max_nesting=limits['parser_max_nesting'])
        pikepdf._core.set_access_default_mmap(mmap_default)
    assert settings.get_decimal_precision() == precision
    assert settings.get_qpdf_limits() == limits


def test_stress_open_save_close_many_pdfs(tmp_path):
    """Pdfs opened, modified, saved and closed in parallel do not interfere.

    This exercises the global QPDF registry: every Pdf registers on creation
    and unregisters on destruction.
    """

    def work(i):
        for n in range(8):
            with Pdf.open(RESOURCES / 'fourpages.pdf') as pdf:
                pdf.Root.Thread = i
                del pdf.pages[n % 4]
                pdf.docinfo['/Title'] = f'thread {i} round {n}'
                path = tmp_path / f'{i}_{n}.pdf'
                pdf.save(path)
            with Pdf.open(path) as check:
                assert len(check.pages) == 3
                assert check.Root.Thread == i
                assert str(check.docinfo['/Title']) == f'thread {i} round {n}'

    run_n(work)


N_TREE_KEYS = 200


def name_tree_key(n):
    return f'key{n:04d}'


@pytest.fixture(scope='module')
def name_tree_pdf_bytes():
    """A saved Pdf with a name tree of N_TREE_KEYS entries at /Root/Names/Dests."""
    pdf = Pdf.new()
    pdf.add_blank_page()
    tree = NameTree.new(pdf)
    for n in range(N_TREE_KEYS):
        tree[name_tree_key(n)] = pdf.make_indirect(Dictionary(N=n))
    pdf.Root.Names = pdf.make_indirect(Dictionary(Dests=tree.obj))
    out = BytesIO()
    pdf.save(out)
    return out.getvalue()


def test_stress_name_tree_cold_reads(name_tree_pdf_bytes):
    """Threads sharing one NameTree of a cold file all read the same tree.

    Nothing has been resolved when the threads start, so every lookup makes
    qpdf read the file and fill the tree's cache.
    """
    expected = [name_tree_key(n) for n in range(N_TREE_KEYS)]
    for _ in range(5):
        with Pdf.open(BytesIO(name_tree_pdf_bytes)) as pdf:
            tree = NameTree(pdf.Root.Names.Dests)

            def read(i, tree=tree):
                for n in range(i, N_TREE_KEYS, 7):
                    assert name_tree_key(n) in tree
                    assert tree[name_tree_key(n)].N == n
                assert 'absent' not in tree
                assert len(tree) == N_TREE_KEYS
                assert list(tree) == expected
                assert list(tree.keys()) == expected

            run_n(read)


def test_stress_name_tree_insert_while_reading(name_tree_pdf_bytes):
    """Inserting into a NameTree while other threads read it loses nothing."""
    per_thread = 40
    with Pdf.open(BytesIO(name_tree_pdf_bytes)) as pdf:
        tree = NameTree(pdf.Root.Names.Dests)

        def work(i):
            if i % 2:
                for n in range(per_thread):
                    tree[f'new{i}_{n:03d}'] = Dictionary(T=i, N=n)
            else:
                for _ in range(per_thread):
                    for key in tree:
                        assert key.startswith(('key', 'new'))
                    assert len(tree) >= N_TREE_KEYS
                    assert tree[name_tree_key(i)].N == i

        run_n(work)
        writers = [i for i in range(N_THREADS) if i % 2]
        assert len(tree) == N_TREE_KEYS + per_thread * len(writers)
        for i in writers:
            for n in range(per_thread):
                item = tree[f'new{i}_{n:03d}']
                assert (item.T, item.N) == (i, n)


@pytest.fixture(scope='module')
def number_tree_pdf_bytes():
    """A saved Pdf with a number tree of N_TREE_KEYS entries at /Root/Numbers."""
    pdf = Pdf.new()
    pdf.add_blank_page()
    tree = NumberTree.new(pdf)
    for n in range(N_TREE_KEYS):
        tree[n] = pdf.make_indirect(Dictionary(N=n))
    pdf.Root.Numbers = tree.obj
    out = BytesIO()
    pdf.save(out)
    return out.getvalue()


def test_stress_number_tree_cold_reads(number_tree_pdf_bytes):
    """Threads sharing one NumberTree of a cold file all read the same tree."""
    expected = list(range(N_TREE_KEYS))
    for _ in range(5):
        with Pdf.open(BytesIO(number_tree_pdf_bytes)) as pdf:
            tree = NumberTree(pdf.Root.Numbers)

            def read(i, tree=tree):
                for n in range(i, N_TREE_KEYS, 7):
                    assert n in tree
                    assert tree[n].N == n
                assert -1 not in tree
                assert len(tree) == N_TREE_KEYS
                assert list(tree) == expected
                assert list(tree.keys()) == expected

            run_n(read)


def test_stress_number_tree_insert_while_reading(number_tree_pdf_bytes):
    """Inserting into a NumberTree while other threads read it loses nothing."""
    per_thread = 40
    with Pdf.open(BytesIO(number_tree_pdf_bytes)) as pdf:
        tree = NumberTree(pdf.Root.Numbers)

        def work(i):
            if i % 2:
                for n in range(per_thread):
                    tree[1000 * i + n] = Dictionary(T=i, N=n)
            else:
                for _ in range(per_thread):
                    for key in tree:
                        assert isinstance(key, int)
                    assert len(tree) >= N_TREE_KEYS
                    assert tree[i].N == i

        run_n(work)
        writers = [i for i in range(N_THREADS) if i % 2]
        assert len(tree) == N_TREE_KEYS + per_thread * len(writers)
        for i in writers:
            for n in range(per_thread):
                item = tree[1000 * i + n]
                assert (item.T, item.N) == (i, n)


def describe_form(pdf, acroform=None):
    """Read an interactive form through the AcroForm helper classes."""
    if acroform is None:
        acroform = pdf.acroform
    result = [acroform.exists, acroform.needs_appearances]
    for field in acroform.fields:
        result.append(
            (
                field.fully_qualified_name,
                field.partial_name,
                field.alternate_name,
                field.field_type,
                field.flags,
                field.is_text,
                field.is_checkbox,
                field.is_radio_button,
                field.value_as_string,
                field.default_appearance,
                str(field.get_inheritable_field_value_as_name('/FT')),
                field.top_level_field.fully_qualified_name,
                len(acroform.get_annotations_for_field(field)),
            )
        )
    for page in pdf.pages:
        result.append(len(acroform.get_widget_annotations_for_page(page)))
        result.append(
            [f.fully_qualified_name for f in acroform.get_form_fields_for_page(page)]
        )
    return result


def test_stress_acroform_cold_reads():
    """Threads reading the form of a cold file all see the same form."""
    with Pdf.open(RESOURCES / 'form.pdf') as reference:
        expected = describe_form(reference)
    assert len(expected) > 4
    for _ in range(5):
        with Pdf.open(RESOURCES / 'form.pdf') as pdf:
            # One helper for all the threads: it builds its index of the
            # form's fields the first time it is asked for them.
            acroform = pdf.acroform

            def read(i, pdf=pdf, acroform=acroform):
                assert describe_form(pdf, acroform) == expected
                assert describe_form(pdf) == expected

            run_n(read)


def test_stress_acroform_shared_helper_set_values():
    """Threads setting different fields through one AcroForm lose no update."""
    with Pdf.open(RESOURCES / 'form.pdf') as pdf:
        acroform = pdf.acroform
        text_fields = [f for f in acroform.fields if f.is_text]
        assert text_fields
        field = text_fields[0]

        def work(i):
            for n in range(50):
                if i == 0:
                    field.value_as_string = f'value {n}'
                else:
                    assert field.value_as_string.startswith(('value ', ''))
                    assert field.fully_qualified_name == 'Text1'
                    assert len(acroform.fields) == 5

        run_n(work)
        assert field.value_as_string == 'value 49'


def describe_annotation(obj):
    annot = Annotation(obj)
    stream = annot.get_appearance_stream(Name.N)
    return (
        str(annot.subtype),
        [float(v) for v in annot.rect.as_array()],
        annot.flags,
        repr(annot.appearance_state),
        repr(annot.appearance_dict),
        stream.read_bytes() if isinstance(stream, Stream) else None,
        annot.get_page_content_for_appearance(Name.XYZ, 0),
    )


def test_stress_annotations_cold_reads():
    """Threads reading the annotations of a cold file all see the same ones."""
    with Pdf.open(RESOURCES / 'form.pdf') as reference:
        expected = [describe_annotation(a) for a in reference.pages[0].Annots]
    assert len(expected) == 5
    for _ in range(5):
        with Pdf.open(RESOURCES / 'form.pdf') as pdf:
            annots = list(pdf.pages[0].Annots)

            def read(i, annots=annots):
                for _ in range(5):
                    for annot, want in zip(annots, expected, strict=True):
                        assert describe_annotation(annot) == want

            run_n(read)


N_ATTACHMENTS = 12


@pytest.fixture(scope='module')
def attachments_pdf_bytes():
    pdf = Pdf.new()
    pdf.add_blank_page()
    for n in range(N_ATTACHMENTS):
        pdf.attachments[f'file{n:02d}.txt'] = AttachedFileSpec(
            pdf,
            f'contents of file {n}'.encode() * 50,
            description=f'description {n}',
            mime_type='text/plain',
        )
    out = BytesIO()
    pdf.save(out)
    return out.getvalue()


def test_stress_attachments_cold_reads(attachments_pdf_bytes):
    """Threads reading the attachments of a cold file all read the same files."""
    names = [f'file{n:02d}.txt' for n in range(N_ATTACHMENTS)]
    for _ in range(5):
        with Pdf.open(BytesIO(attachments_pdf_bytes)) as pdf:
            attachments = pdf.attachments

            def read(i, attachments=attachments):
                assert len(attachments) == N_ATTACHMENTS
                assert list(attachments) == names
                for n in range(i % 3, N_ATTACHMENTS, 3):
                    spec = attachments[names[n]]
                    assert spec.description == f'description {n}'
                    assert spec.filename == names[n]
                    assert Name.F in spec.get_all_filenames()
                    file = spec.get_file()
                    data = f'contents of file {n}'.encode() * 50
                    assert file.read_bytes() == data
                    assert file.size == len(data)
                    assert file.mime_type == 'text/plain'
                    assert len(file.md5) == 16

            run_n(read)


def test_stress_attachments_added_from_many_threads(attachments_pdf_bytes):
    """Attachments added to one Pdf by several threads are all kept."""
    per_thread = 10
    with Pdf.open(BytesIO(attachments_pdf_bytes)) as pdf:
        attachments = pdf.attachments

        def work(i):
            for n in range(per_thread):
                name = f'new{i}_{n:02d}.bin'
                if n % 2:
                    attachments[name] = f'{i}/{n}'.encode()
                else:
                    attachments[name] = AttachedFileSpec(
                        pdf, f'{i}/{n}'.encode(), description=name
                    )
                assert attachments[name].get_file().read_bytes() == f'{i}/{n}'.encode()
                assert len(attachments) > N_ATTACHMENTS

        run_n(work)
        assert len(attachments) == N_ATTACHMENTS + per_thread * N_THREADS
        assert len(pdf.Root.AF) == len(attachments)
        out = BytesIO()
        pdf.save(out)
    with Pdf.open(out) as check:
        for i in range(N_THREADS):
            for n in range(per_thread):
                file = check.attachments[f'new{i}_{n:02d}.bin'].get_file()
                assert file.read_bytes() == f'{i}/{n}'.encode()
