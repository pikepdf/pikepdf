# SPDX-FileCopyrightText: 2026 James R. Barlow
# SPDX-License-Identifier: MPL-2.0

"""Thread safety of Dictionary and Array objects that belong to no Pdf.

Such an object has no Pdf lock to take, so pikepdf protects every one of them
with a single shared lock. These tests check that the lock is taken, that a
container shared between threads survives concurrent changes, and that an
object can be added to or removed from a Pdf while other threads use it.

Keep each one short: they also run under ThreadSanitizer.
"""

from __future__ import annotations

import sys
import threading

import pytest
from test_threading import JOIN_TIMEOUT, N_THREADS, TIMEOUT, run_n, run_threads

from pikepdf import Array, Dictionary, Name, NamePath, Page, Pdf

pytestmark = TIMEOUT

# See test_threading_python_layer.py
PROBE_WAIT = 0.2


def _blocked_while(fn_in_other_thread):
    """Return a generator that, when first advanced, runs a call in another
    thread and records whether it was still waiting after PROBE_WAIT."""
    state: dict[str, object] = {}

    def gen():
        done = threading.Event()

        def other():
            fn_in_other_thread()
            done.set()

        thread = threading.Thread(target=other, daemon=True)
        thread.start()
        state['blocked'] = not done.wait(PROBE_WAIT)
        state['thread'] = thread
        yield 1

    return gen(), state


def _finish(state):
    thread = state['thread']
    assert isinstance(thread, threading.Thread)
    thread.join(JOIN_TIMEOUT)
    assert not thread.is_alive()


def test_unowned_array_is_locked_while_changed():
    a = Array([0])
    items, state = _blocked_while(lambda: a.append(99))
    a.extend(items)
    _finish(state)
    assert state['blocked']
    assert list(a) == [0, 1, 99]


def test_unowned_dictionary_is_locked_while_another_is_changed():
    # One lock covers every object that belongs to no Pdf
    a = Array()
    d = Dictionary()
    items, state = _blocked_while(lambda: d.__setitem__('/K', 1))
    a.extend(items)
    _finish(state)
    assert state['blocked']
    assert d.K == 1


def test_unowned_scalar_is_not_locked():
    # Scalars cannot be changed, so they take no lock
    a = Array()
    n = Name.Foo
    items, state = _blocked_while(lambda: str(n))
    a.extend(items)
    _finish(state)
    assert not state['blocked']


def test_owned_array_does_not_take_the_unowned_lock():
    pdf = Pdf.new()
    pdf.Root.A = Array()
    owned = pdf.Root.A
    other = Array()
    items, state = _blocked_while(lambda: other.append(1))
    owned.extend(items)
    _finish(state)
    assert not state['blocked']


def test_stress_shared_unowned_dictionary():
    d = Dictionary()

    def worker(i):
        for n in range(300):
            d[Name(f'/K{i}_{n % 20}')] = n
            if n % 3 == 0:
                try:
                    del d[Name(f'/K{i}_{(n + 10) % 20}')]
                except KeyError:
                    pass
            len(d.keys())
            repr(d)

    run_n(worker)
    assert len(d.keys()) <= N_THREADS * 20


def test_stress_shared_unowned_array():
    a = Array()

    def worker(i):
        for n in range(300):
            a.append(n)
            if len(a) > 50:
                try:
                    del a[0]
                except IndexError:
                    pass
            list(a)

    run_n(worker)
    assert len(a) <= 50 + N_THREADS


def test_stress_adopt_and_detach_while_shared():
    """Add an object to a Pdf and take it out again while threads change it."""
    pdf = Pdf.new()
    d = Dictionary(A=1)

    def inserter():
        for _ in range(200):
            pdf.Root.D = d
            del pdf.Root.D

    def changer(i):
        def run():
            for n in range(200):
                d[Name(f'/K{i}')] = n
                len(d.keys())

        return run

    run_threads(inserter, *[changer(i) for i in range(N_THREADS - 1)])
    assert int(d.A) == 1
    assert not d.is_owned_by(pdf)


def _held_by_another(pdf):
    """Return a pdf-owned array to extend with a probe, so that the probe
    runs while this thread holds pdf's lock."""
    pdf.Root.Probe = Array()
    return pdf.Root.Probe


def _pdf_and_unowned_reference():
    pdf = Pdf.new()
    pdf.add_blank_page()
    page = pdf.pages[0].obj
    box = pdf.make_indirect(Array([0, 0, 10, 10]))
    return pdf, page, box


# Operations that read objects reachable from an object that belongs to no Pdf.
# When that object holds an object of a Pdf, they must hold that Pdf's lock.
# Each entry builds its objects first, then returns the operation to probe.
def _object_list_eq(page, box):
    a = Array([Array([page])]).as_list()
    b = Array([Array([page])]).as_list()
    return lambda: a == b


def _namepath(page, box):
    d = Dictionary(A=Dictionary(P=page))

    def op():
        with pytest.raises(KeyError):
            d[NamePath.A.P.Missing]

    return op


_WALKS = {
    'repr': lambda page, box: lambda d=Dictionary(P=page): repr(d),
    'str': lambda page, box: lambda a=Array([page]): str(a),
    'eq': lambda page, box: lambda d=Dictionary(P=page), e=Dictionary(P=page): d == e,
    'contains': lambda page, box: lambda a=Array([2, page]): 1 in a,
    'index': lambda page, box: lambda a=Array([page, 1]): a.index(1),
    'count': lambda page, box: lambda a=Array([page]): a.count(1),
    'remove': lambda page, box: lambda a=Array([page, 1]): a.remove(1),
    'object_list_eq': _object_list_eq,
    'namepath': _namepath,
    'page_helper': lambda page, box: (
        lambda p=Page(Dictionary(Type=Name.Page, MediaBox=box)): p.mediabox
    ),
    'is_rectangle': lambda page, box: lambda a=Array([0, 0, 1, box]): a.is_rectangle,
    'nested': lambda page, box: (
        lambda d=Dictionary(A=Array([Dictionary(P=page)])): repr(d)
    ),
}


@pytest.mark.parametrize('walk', _WALKS.values(), ids=_WALKS.keys())
def test_walk_from_unowned_locks_referenced_pdf(walk):
    pdf, page, box = _pdf_and_unowned_reference()
    op = walk(page, box)
    items, state = _blocked_while(op)
    _held_by_another(pdf).extend(items)
    _finish(state)
    assert state['blocked']


# Cheap operations on a container that belongs to no Pdf do not walk it, so
# building a large one stays linear. They take no lock of a Pdf whose objects
# the container holds unless they read one of those objects.
_SHALLOW = {
    'len': lambda d, a: len(a),
    'append': lambda d, a: a.append(1),
    'getitem_scalar': lambda d, a: a[0],
    'setitem': lambda d, a: a.__setitem__(0, 2),
    'setattr': lambda d, a: setattr(d, 'Q', 1),
    'keys': lambda d, a: d.keys(),
    'is_indirect': lambda d, a: a.is_indirect,
}


@pytest.mark.parametrize('op', _SHALLOW.values(), ids=_SHALLOW.keys())
def test_shallow_operation_does_not_lock_referenced_pdf(op):
    pdf, page, _box = _pdf_and_unowned_reference()
    d = Dictionary(P=page)
    a = Array([1, page])
    items, state = _blocked_while(lambda: op(d, a))
    _held_by_another(pdf).extend(items)
    _finish(state)
    assert not state['blocked']


def test_stress_walk_unowned_while_pdf_loads(resources):
    """Read a file's objects through a container that belongs to no Pdf while
    other threads load the same objects through the Pdf."""
    with Pdf.open(resources / 'fourpages.pdf') as pdf:
        objects = [pdf.get_object(i, 0) for i in range(1, len(pdf.objects))]
        d = Dictionary(Items=Array(objects))

        def walker():
            for _ in range(50):
                repr(d)
                _ = d == d

        def loader():
            for _ in range(50):
                for page in pdf.pages:
                    repr(page.obj)
                    page.mediabox

        run_threads(*[walker, loader] * (N_THREADS // 2))


def test_emplace_on_unowned_dictionary_is_atomic():
    """Another thread sees a Dictionary before emplace() or after it, never
    part way through."""
    d = Dictionary(A=1, B=1)
    sources = [Dictionary(A=2, B=2), Dictionary(C=3, D=3)]
    done = threading.Event()
    seen = set()

    def emplacer():
        try:
            for i in range(3000):
                d.emplace(sources[i % 2])
        finally:
            done.set()

    def watcher():
        while not done.is_set():
            seen.add(frozenset(d.keys()))

    old_interval = sys.getswitchinterval()
    sys.setswitchinterval(1e-6)
    try:
        run_threads(emplacer, watcher)
    finally:
        sys.setswitchinterval(old_interval)
    assert seen <= {frozenset({'/A', '/B'}), frozenset({'/C', '/D'})}
