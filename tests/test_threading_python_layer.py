# SPDX-FileCopyrightText: 2026 James R. Barlow
# SPDX-License-Identifier: MPL-2.0

"""Locking in the methods that pikepdf implements in Python.

A method implemented in Python is a sequence of calls to bindings, each of
which locks the Pdf only for its own duration. The methods tested here change
a Pdf in several dependent steps, so they hold the Pdf's lock across all of
them. Each test interrupts one of these methods part way through, at a call
it makes between steps, and checks from another thread that the lock is held
at that point.
"""

from __future__ import annotations

import threading

import pytest
from test_threading import JOIN_TIMEOUT, RESOURCES, TIMEOUT, run_threads

import pikepdf
from pikepdf import Dictionary, Name, Object, OutlineItem, Page, Pdf, sanitize
from pikepdf._core import AcroFormField, _OwnerLock
from pikepdf.form import Form
from pikepdf.models.metadata import PdfMetadata
from pikepdf.models.outlines import Outline

pytestmark = TIMEOUT

# How long a probe waits to take a lock before deciding that it is held. A
# probe that is slow to start on a busy machine makes a free lock look held,
# so a test may pass when it should fail, but never fails when it should pass.
PROBE_WAIT = 0.2


class LockProbe:
    """Check, from another thread, whether the locks of some Pdfs are held."""

    def __init__(self, *pdfs: Pdf):
        self.pdfs = pdfs
        self.held: list[bool] | None = None
        self._threads: list[threading.Thread] = []

    def probe(self) -> list[bool]:
        held = []
        for pdf in self.pdfs:
            taken = threading.Event()

            def take(pdf=pdf, taken=taken):
                with pdf.lock():
                    taken.set()

            thread = threading.Thread(target=take, daemon=True)
            thread.start()
            self._threads.append(thread)
            held.append(not taken.wait(PROBE_WAIT))
        return held

    def wrap(self, fn):
        """Return fn, changed to probe the locks the first time it is called."""

        def wrapper(*args, **kwargs):
            if self.held is None:
                self.held = self.probe()
            return fn(*args, **kwargs)

        return wrapper

    def join(self):
        for thread in self._threads:
            thread.join(JOIN_TIMEOUT)
            assert not thread.is_alive()

    def assert_held(self):
        self.join()
        assert self.held == [True] * len(self.pdfs)


def test_probe_sees_free_and_held_locks():
    pdf = Pdf.new()
    probe = LockProbe(pdf)
    assert probe.probe() == [False]
    with pdf.lock():
        assert probe.probe() == [True]
    probe.join()


def test_owner_lock_locks_the_owner_of_each_item():
    pdf_a, pdf_b, pdf_c = Pdf.new(), Pdf.new(), Pdf.new()
    pdf_c.add_blank_page()
    obj_b = pdf_b.make_indirect(Dictionary())
    probe = LockProbe(pdf_a, pdf_b, pdf_c)
    items = [pdf_a, obj_b, pdf_c.pages[0], Dictionary(), None, b'not pikepdf']
    with _OwnerLock(items):
        assert probe.probe() == [True, True, True]
    assert probe.probe() == [False, False, False]
    probe.join()


def test_owner_lock_is_reentrant():
    pdf = Pdf.new()
    with _OwnerLock([pdf]), pdf.lock(), _OwnerLock([pdf, pdf]):
        pdf.make_indirect(Dictionary())
    assert LockProbe(pdf).probe() == [False]


def test_owner_lock_takes_locks_in_a_consistent_order():
    """Threads naming the same Pdfs in opposite orders do not deadlock."""
    pdf_a, pdf_b = Pdf.new(), Pdf.new()
    obj_a = pdf_a.make_indirect(Dictionary(A=1))
    obj_b = pdf_b.make_indirect(Dictionary(B=1))

    def a_then_b():
        for _ in range(200):
            with _OwnerLock([pdf_a, pdf_b]):
                pdf_a.copy_foreign(obj_b)

    def b_then_a():
        for _ in range(200):
            with _OwnerLock([pdf_b, pdf_a]):
                pdf_b.copy_foreign(obj_a)

    run_threads(a_then_b, b_then_a)


def test_object_emplace_holds_lock(monkeypatch):
    pdf = Pdf.new()
    target = pdf.make_indirect(Dictionary(A=1, B=2))
    source = pdf.make_indirect(Dictionary(B=3, C=4))
    probe = LockProbe(pdf)
    monkeypatch.setattr(Object, 'keys', probe.wrap(Object.keys))
    target.emplace(source)
    probe.assert_held()
    assert set(target.keys()) == {'/B', '/C'}


def test_page_add_resource_holds_lock(monkeypatch):
    pdf = Pdf.new()
    pdf.add_blank_page()
    probe = LockProbe(pdf)
    monkeypatch.setattr(Object, 'as_dict', probe.wrap(Object.as_dict))
    name = pdf.pages[0].add_resource(Dictionary(), Name.ExtGState)
    probe.assert_held()
    assert name in pdf.pages[0].Resources.ExtGState


def test_page_add_overlay_holds_both_locks(monkeypatch):
    pdf = Pdf.new()
    pdf.add_blank_page()
    other = Pdf.new()
    other.add_blank_page()
    probe = LockProbe(pdf, other)
    monkeypatch.setattr(Page, 'contents_add', probe.wrap(Page.contents_add))
    pdf.pages[0].add_overlay(other.pages[0])
    probe.assert_held()


def test_add_pages_from_holds_both_locks(monkeypatch):
    import pikepdf._page_copy

    pdf = Pdf.new()
    src = Pdf.new()
    src.add_blank_page()
    probe = LockProbe(pdf, src)
    monkeypatch.setattr(
        pikepdf._page_copy, 'copy_pages', probe.wrap(pikepdf._page_copy.copy_pages)
    )
    pdf.add_pages_from(src)
    probe.assert_held()
    assert len(pdf.pages) == 1


def test_add_pages_from_in_opposite_directions():
    """Two Pdfs copying pages from each other at once do not deadlock."""
    pdf_a, pdf_b = Pdf.new(), Pdf.new()
    pdf_a.add_blank_page()
    pdf_b.add_blank_page()

    def copy(dst, src):
        for _ in range(20):
            dst.add_pages_from(src, pages=[0])

    run_threads(lambda: copy(pdf_a, pdf_b), lambda: copy(pdf_b, pdf_a))
    assert len(pdf_a.pages) >= 21
    assert len(pdf_b.pages) >= 21


@pytest.mark.parametrize(
    'apply',
    [
        sanitize.remove_javascript,
        lambda pdf: sanitize.Sanitizer().remove_javascript().apply(pdf),
    ],
    ids=['remove_javascript', 'Sanitizer.apply'],
)
def test_sanitize_holds_lock(monkeypatch, apply):
    pdf = Pdf.new()
    probe = LockProbe(pdf)
    monkeypatch.setattr(
        sanitize, '_drop_named_javascript', probe.wrap(sanitize._drop_named_javascript)
    )
    apply(pdf)
    probe.assert_held()


def test_form_text_value_holds_lock(monkeypatch):
    with Pdf.open(RESOURCES / 'form.pdf') as pdf:
        field = Form(pdf)['Text1']
        probe = LockProbe(pdf)
        monkeypatch.setattr(
            AcroFormField, 'set_value', probe.wrap(AcroFormField.set_value)
        )
        field.value = 'Stuff'
        probe.assert_held()
        assert field.value == 'Stuff'


def test_outline_save_holds_lock(monkeypatch):
    pdf = Pdf.new()
    pdf.add_blank_page()
    probe = LockProbe(pdf)
    monkeypatch.setattr(
        Outline, '_save_level_outline', probe.wrap(Outline._save_level_outline)
    )
    with pdf.open_outline() as outline:
        outline.root.append(OutlineItem('Title', 0))
    probe.assert_held()


def test_metadata_apply_holds_lock(monkeypatch):
    pdf = Pdf.new()
    probe = LockProbe(pdf)
    monkeypatch.setattr(
        PdfMetadata, '_update_docinfo', probe.wrap(PdfMetadata._update_docinfo)
    )
    with pdf.open_metadata() as meta:
        meta['dc:title'] = 'Title'
    probe.assert_held()
    assert pdf.docinfo.Title == 'Title'


def test_metadata_in_threads_keeps_every_title():
    """Each thread's metadata edit is applied as a whole."""
    pdf = Pdf.new()

    def edit(i):
        for _ in range(10):
            with pdf.open_metadata() as meta:
                meta['dc:title'] = f'Title {i}'
            assert str(pdf.docinfo.Title).startswith('Title ')

    run_threads(*[lambda i=i: edit(i) for i in range(4)])
    with pikepdf.open(pdf._quick_save()) as reopened:
        with reopened.open_metadata() as meta:
            assert meta['dc:title'] == str(reopened.docinfo.Title)
