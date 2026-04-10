# SPDX-FileCopyrightText: 2024 James R. Barlow
# SPDX-License-Identifier: MPL-2.0

"""Thread safety tests for pikepdf under free-threaded Python.

These tests verify that concurrent operations on pikepdf objects do not
crash or corrupt state. On GIL-enabled builds, the per-QPDF locks are
no-ops, so these tests exercise the code paths without contention.
"""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import pytest

from pikepdf import Array, Dictionary, Name, Pdf

RESOURCES = Path(__file__).parent / "resources"


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
