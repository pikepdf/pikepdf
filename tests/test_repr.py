# SPDX-FileCopyrightText: 2022 James R. Barlow
# SPDX-License-Identifier: CC0-1.0

"""Test object repr."""

from __future__ import annotations

from decimal import Decimal

from hypothesis import example, given
from hypothesis.strategies import binary, text

import pikepdf
from pikepdf import Array, Dictionary, Name, Operator, String


def test_repr_dict():
    d = Dictionary(
        {
            '/Boolean': True,
            '/Integer': 42,
            '/Real': Decimal('42.42'),
            '/String': String('hi'),
            '/Array': Array([1, 2, 3.14]),
            '/Operator': Operator('q'),
            '/Dictionary': Dictionary({'/Color': 'Red'}),
            '/None': None,
        }
    )
    short_pi = '3.14'
    expected = (
        """\
        pikepdf.Dictionary({
            "/Array": [ 1, 2, Decimal('%s') ],
            "/Boolean": True,
            "/Dictionary": {
                "/Color": "Red"
            },
            "/Integer": 42,
            "/None": None,
            "/Operator": pikepdf.Operator("q"),
            "/Real": Decimal('42.42'),
            "/String": "hi"
        })
    """
        % short_pi
    )

    def strip_all_whitespace(s):
        return ''.join(s.split())

    assert strip_all_whitespace(repr(d)) == strip_all_whitespace(expected)
    assert eval(repr(d)) == d


def test_repr_scalar():
    scalars = [
        False,
        666,
        Decimal('3.14'),
        String('scalar'),
        Name('/Bob'),
        Operator('Q'),
    ]
    for s in scalars:
        assert eval(repr(s)) == s


def test_repr_indirect(resources):
    with pikepdf.open(resources / 'graph.pdf') as graph:
        repr_page0 = repr(graph.pages[0])
        assert repr_page0[0] == '<', 'should not be constructible'


def test_repr_circular():
    with pikepdf.new() as pdf:
        pdf.Root.Circular = pdf.make_indirect(Dictionary())
        pdf.Root.Circular.Parent = pdf.make_indirect(Dictionary())
        pdf.Root.Circular.Parent = pdf.make_indirect(pdf.Root.Circular)
        assert '.get_object' in repr(pdf.Root.Circular)


def test_repr_indirect_page(resources):
    with pikepdf.open(resources / 'outlines.pdf') as outlines:
        assert 'from_objgen' in repr(outlines.Root.Pages.Kids)
        # An indirect page reference in the Dests name tree
        assert 'from_objgen' in repr(outlines.Root.Names.Dests.Kids[0].Names[1])


def test_array_direct_object_preserved():
    wide = Array([1, 2, 3, 4, 5, 6, 7, 8, 9, 10] * 5)
    assert '...' not in repr(wide)
    wide_wrapper = Array([wide])
    assert '...' in repr(wide_wrapper)


def test_array_indirect_truncation():
    wide = Array([1, 2, 3, 4, 5, 6, 7, 8, 9, 10] * 5)
    pdf = pikepdf.new()
    pdf.Root.Wide = pdf.make_indirect([wide])
    assert '...' in repr(pdf.Root.Wide)
    assert '...' not in repr(pdf.Root.Wide[0])


def test_array_depth_truncation():
    a = [42]
    for _ in range(100):
        a = [a]
    deep = Array([a])
    assert '...' in repr(deep)
    pdf = pikepdf.new()
    pdf.Root.Deep = pdf.make_indirect(deep)
    assert '...' in repr(pdf.Root.Deep)


def dequote(s):
    # Elide the difference between b"" and b''
    return s.replace('"', '').replace("'", '')


@given(binary(min_size=0, max_size=300))
@example(b'hi')
@example(b'\x00\x00\x00\t \'\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00"')
def test_repr_stream(data):
    with pikepdf.new() as pdf:
        pdf.Root.Stream = pikepdf.Stream(pdf, data, {'/Type': '/Example', '/Length': 2})
        assert '/Example' in repr(pdf.Root.Stream)

        if len(data) <= 20:
            assert dequote(repr(data)) in dequote(repr(pdf.Root.Stream))
        else:
            assert dequote(repr(data)[:18]) in dequote(repr(pdf.Root.Stream))
