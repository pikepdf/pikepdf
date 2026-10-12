# SPDX-FileCopyrightText: 2026 James R. Barlow
# SPDX-License-Identifier: MPL-2.0

"""Thread safety stress tests for the bindings of pikepdf.Object.

A companion to test_threading.py, in the same style and with the same helpers.
The tests here are aimed at the Object methods and module-level functions that
used to take no lock of their own, and at calls that involve the objects of two
Pdfs, where each Pdf is locked for the whole call.

On a GIL-enabled build the per-Pdf locks are no-ops, and these tests only
exercise the code paths. Keep each one short: they also run under
ThreadSanitizer, which slows the interpreter by roughly an order of magnitude.
"""

from __future__ import annotations

import operator
from decimal import Decimal
from io import BytesIO

import pytest
from test_threading import N_THREADS, run_n, run_threads

import pikepdf
from pikepdf import (
    Array,
    Boolean,
    Dictionary,
    Integer,
    Name,
    NamePath,
    ObjectType,
    Pdf,
    Real,
    String,
)
from pikepdf._core import unparse

# A deadlock must fail the test rather than hang the run. See test_threading.py
pytestmark = pytest.mark.timeout(120, method='thread')


def pdf_with_indirect_scalars(n_objects=24):
    """A saved Pdf of dictionaries whose every value is its own indirect object.

    That includes the numbers and booleans, which are made indirect in
    explicit conversion mode so that they are not converted to native values,
    and stored directly, on the way. Nothing below the catalog is resolved
    when the file is opened.
    """
    pdf = Pdf.new()
    pdf.add_blank_page()
    items = Array()
    with pikepdf.explicit_conversion():
        for n in range(n_objects):
            d = Dictionary(
                Int=pdf.make_indirect(Integer(n)),
                Real=pdf.make_indirect(Real('1.5')),
                Bool=pdf.make_indirect(Boolean(True)),
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


def in_unowned_array(value):
    """Read an integer back out of an Array that no Pdf owns."""
    holder = Dictionary(A=Array())
    holder.A.append(value)
    return holder.get_int(NamePath.A[0])


def in_unowned_dictionary(value):
    """Read an integer back out of a Dictionary that no Pdf owns."""
    holder = Dictionary()
    holder.K = value
    holder['/K2'] = value
    holder[Name.K3] = value
    return holder.get_int('/K') + holder.get_int(Name.K2) + holder.get_int('/K3')


def updated_from(value):
    """Copy the keys of a dictionary into one that no Pdf owns."""
    merged = Dictionary(Extra=1)
    merged.update(value)
    return merged


def cold_checks(n):
    """Checks that each read one value of dictionary *n* through one binding.

    Each is a key and a predicate for the value of that key as get_raw()
    returns it: an Object that refers to an indirect object which, until
    something reads it, qpdf has not loaded from the file.
    """
    return [
        ('/Int', lambda v: v._type_code == ObjectType.integer),
        ('/Int', lambda v: v._type_name == 'integer'),
        ('/Int', lambda v: v.as_int() == n),
        ('/Int', lambda v: v.as_int(None) == n),
        ('/Int', lambda v: operator.index(v) == n),
        ('/Int', lambda v: float(v) == n),
        ('/Int', lambda v: int(v) == n),
        ('/Int', lambda v: v + 1 == n + 1),
        ('/Int', lambda v: 1 + v == n + 1),
        ('/Int', lambda v: v < n + 1),
        ('/Int', lambda v: round(v) == n),
        ('/Int', lambda v: round(v, 1) == n),
        ('/Int', lambda v: -v == -n and abs(v) == n),
        ('/Int', lambda v: f'{v:d}' == str(n)),
        ('/Int', lambda v: pikepdf.as_int(v) == n),
        ('/Int', lambda v: pikepdf.as_float(v, coerce=True) == n),
        ('/Int', lambda v: pikepdf.unbox(v) == n),
        ('/Int', lambda v: v.unparse(resolved=True) == str(n).encode()),
        ('/Int', lambda v: v.is_indirect and unparse(v).endswith(b' R')),
        ('/Int', lambda v: in_unowned_array(v) == n),
        ('/Int', lambda v: in_unowned_dictionary(v) == 3 * n),
        ('/Real', lambda v: v._get_real_value() == '1.5'),
        ('/Real', lambda v: v.as_float() == 1.5),
        ('/Real', lambda v: v.as_decimal() == Decimal('1.5')),
        ('/Real', lambda v: v.as_decimal(None) == Decimal('1.5')),
        ('/Real', lambda v: pikepdf.as_float(v) == 1.5),
        ('/Real', lambda v: pikepdf.as_decimal(v) == Decimal('1.5')),
        ('/Real', lambda v: pikepdf.unbox(v) == Decimal('1.5')),
        ('/Real', lambda v: v * 2 == 3),
        ('/Bool', lambda v: v.as_bool() is True),
        ('/Bool', lambda v: v.as_bool(None) is True),
        ('/Bool', lambda v: pikepdf.as_bool(v) is True),
        ('/Bool', lambda v: pikepdf.unbox(v) is True),
        ('/Bool', lambda v: bool(v)),
        ('/Name', lambda v: v._type_code == ObjectType.name_),
        ('/Name', lambda v: v == f'/N{n}'),
        ('/Name', lambda v: str(v) == f'/N{n}'),
        ('/Str', lambda v: v.as_str() == f's{n}'),
        ('/Str', lambda v: v.as_bytes(None) == f's{n}'.encode()),
        ('/Str', lambda v: pikepdf.as_str(v) == f's{n}'),
        ('/Str', lambda v: pikepdf.as_bytes(v) == f's{n}'.encode()),
        ('/Str', lambda v: pikepdf.as_int(v, coerce=True) is None),
        ('/Rect', lambda v: v.is_rectangle),
        ('/Rect', lambda v: len(v.wrap_in_array()) == 4),
        ('/Rect', lambda v: len(v.as_list(None)) == 4),
        ('/Rect', lambda v: len(pikepdf.as_list(v)) == 4),
        ('/Rect', lambda v: v.copy()[3] == n),
        ('/Rect', lambda v: [int(x) for x in v] == [0, 0, n, n]),
        ('/Sub', lambda v: len(v.as_dict(None)) == 1),
        ('/Sub', lambda v: len(pikepdf.as_dict(v)) == 1),
        ('/Sub', lambda v: len(updated_from(v)) == 2),
        ('/Sub', lambda v: '/Leaf' in v.copy()),
        ('/Sub', lambda v: v.get_list(NamePath.Leaf)[0] == n),
        ('/Sub', lambda v: [int(x) for x in v.get(NamePath.Leaf)] == [n]),
        ('/Data', lambda v: v._type_name == 'stream'),
        ('/Data', lambda v: len(bytes(v.get_raw_stream_buffer())) > 0),
        ('/Data', lambda v: len(v.read_raw_bytes()) == int(v.Length)),
        ('/Data', lambda v: int(v.stream_dict.Length) > 0),
        ('/Data', lambda v: bytes(v) == f'data {n}'.encode()),
    ]


def test_stress_cold_object_first_reads():
    """The first read of an object, through each binding that can make it.

    Whichever binding touches an indirect object first makes qpdf load it from
    the file and enter it in the object cache of the Pdf. Every binding has to
    hold the lock of the Pdf while it does that. Each thread starts at a
    different check, so that between them they make each binding the first to
    read some object while the other threads are loading others.
    """
    data = pdf_with_indirect_scalars()
    n_checks = len(cold_checks(0))
    for round_ in range(4):
        with Pdf.open(BytesIO(data)) as pdf:
            items = pdf.Root.Items
            count = len(items)

            def read(i, items=items, count=count, round_=round_):
                for k in range(count):
                    n = (i * 3 + k) % count
                    d = items[n]
                    checks = cold_checks(n)
                    first = (i * 7 + n * 5 + round_ * 11) % n_checks
                    for c in range(n_checks):
                        key, check = checks[(first + c) % n_checks]
                        assert check(d.get_raw(key)), (key, (first + c) % n_checks)

            run_n(read)


def test_stress_update_from_dictionary_of_another_pdf():
    """Dictionaries of two Pdfs updated from each other while both change.

    update() holds the lock of both Pdfs, so it copies the other dictionary as
    it stood between two of the changes that its own Pdf makes under its lock.
    """
    a = Pdf.new()
    b = Pdf.new()
    src_a = a.make_indirect(Dictionary(Count=0))
    src_b = b.make_indirect(Dictionary(Count=0))
    rounds = 120

    def grow(pdf, src):
        for n in range(rounds):
            with pdf.lock():
                src[f'/K{n}'] = n
                src.Count = n + 1

    def copy(src, into):
        owned = into.make_indirect(Dictionary())
        for _ in range(rounds // 2):
            owned.update(src)
            assert len(owned) == int(owned.Count) + 1
            unowned = Dictionary()
            unowned.update(src)
            assert len(unowned) == int(unowned.Count) + 1

    run_threads(
        lambda: grow(a, src_a),
        lambda: grow(b, src_b),
        *[lambda: copy(src_a, b) for _ in range(N_THREADS // 2 - 1)],
        *[lambda: copy(src_b, a) for _ in range(N_THREADS // 2 - 1)],
    )
    assert int(src_a.Count) == int(src_b.Count) == rounds
    assert len(src_a) == len(src_b) == rounds + 1


def test_stress_search_array_for_object_of_another_pdf():
    """Membership tests on an Array for an object another Pdf is changing.

    The object looked for is compared with the items of the array, so its Pdf
    has to be locked as well as the array's. It is changed and restored under
    its Pdf's lock, so a search that holds that lock always finds it equal.
    """
    a = Pdf.new()
    b = Pdf.new()
    needle_a = a.make_indirect(Dictionary(Items=Array([1, 2, 3])))
    needle_b = b.make_indirect(Dictionary(Items=Array([1, 2, 3])))
    rounds = 80

    def flicker(pdf, needle):
        for _ in range(rounds * 2):
            with pdf.lock():
                needle.Items.append(4)
                needle.Items.pop()

    def search(pdf, needle):
        haystack = pdf.make_indirect(
            Array([Dictionary(Items=Array([n])) for n in range(4)])
        )
        haystack.append(Dictionary(Items=Array([1, 2, 3])))
        for _ in range(rounds):
            assert needle in haystack
            assert haystack.index(needle) == 4
            assert haystack.count(needle) == 1
            assert haystack[4] == needle
            assert not haystack[4].is_same_object_as(needle)
            assert not haystack.same_owner_as(needle)
            haystack.remove(needle)
            assert needle not in haystack
            haystack.append(Dictionary(Items=Array([1, 2, 3])))

    run_threads(
        lambda: flicker(a, needle_a),
        lambda: flicker(b, needle_b),
        *[lambda: search(a, needle_b) for _ in range(N_THREADS // 2 - 1)],
        *[lambda: search(b, needle_a) for _ in range(N_THREADS // 2 - 1)],
    )
    assert [int(v) for v in needle_a.Items] == [1, 2, 3]
    assert [int(v) for v in needle_b.Items] == [1, 2, 3]


def test_stress_compare_helpers_of_two_pdfs():
    """Pages of two Pdfs compared in both orders while both pages change."""
    a = Pdf.new()
    b = Pdf.new()
    page_a = a.add_blank_page()
    page_b = b.add_blank_page()
    assert page_a == page_b
    rounds = 80

    def flicker(pdf, page):
        for n in range(rounds * 2):
            with pdf.lock():
                page.obj.Flicker = n
                del page.obj.Flicker

    def compare(left, right):
        for _ in range(rounds):
            assert left == right
            assert left.obj == right.obj
            assert not left.obj.is_same_object_as(right)

    run_threads(
        lambda: flicker(a, page_a),
        lambda: flicker(b, page_b),
        *[lambda: compare(page_a, page_b) for _ in range(N_THREADS // 2 - 1)],
        *[lambda: compare(page_b, page_a) for _ in range(N_THREADS // 2 - 1)],
    )
    assert '/Flicker' not in page_a.obj and '/Flicker' not in page_b.obj


def test_stress_assign_values_of_another_pdf_both_ways():
    """Values that belong to one Pdf stored in the other, in both directions.

    Each call locks the Pdf of the container and the Pdf of the value in one
    consistent order, so opposite assignments cannot deadlock. That includes
    assigning to a slice from an Array of the other Pdf, which is iterated
    while the container is locked.
    """
    a = Pdf.new()
    b = Pdf.new()
    source_a = a.make_indirect(Dictionary(S=String('from a'), Items=Array([1, 2, 3])))
    source_b = b.make_indirect(Dictionary(S=String('from b'), Items=Array([1, 2, 3])))
    rounds = 60

    def assign(pdf, source, text):
        d = pdf.make_indirect(Dictionary(Sub=Dictionary(), List=Array([0])))
        arr = pdf.make_indirect(Array([0]))
        stream = pdf.make_stream(b'')
        for n in range(rounds):
            value = source.get_raw('/S')
            d.Attr = value
            d['/Key'] = value
            d[Name.Named] = value
            d[NamePath.Sub.Deep] = value
            d[NamePath.List[0]] = value
            arr[0] = value
            arr.append(value)
            arr.insert(0, value)
            assert [str(v) for v in arr] == [text] * 3
            assert arr.index(value) == 0 and arr.count(value) == 3
            arr[1:] = source.Items
            assert [str(v) for v in arr] == [text, '1', '2', '3']
            arr[1:] = []
            assert all(
                str(v) == text
                for v in (d.Attr, d.Key, d.Named, d.Sub.Deep, d.List[0], arr[0])
            )
            assert d.Attr.is_owned_by(pdf) and not value.is_owned_by(pdf)
            stream.write(f'{n}'.encode(), filter=None, decode_parms=None)
            stream.Marker = value
            assert stream.read_bytes() == f'{n}'.encode()

    run_threads(
        *[lambda: assign(a, source_b, 'from b') for _ in range(N_THREADS // 2)],
        *[lambda: assign(b, source_a, 'from a') for _ in range(N_THREADS // 2)],
    )
    assert str(source_a.S) == 'from a' and str(source_b.S) == 'from b'
    assert source_a.S.is_owned_by(a) and source_b.S.is_owned_by(b)
