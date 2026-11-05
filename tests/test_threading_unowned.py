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

import threading

from test_threading import JOIN_TIMEOUT, N_THREADS, TIMEOUT, run_n, run_threads

from pikepdf import Array, Dictionary, Name, Pdf

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
