# SPDX-FileCopyrightText: 2022 James R. Barlow
# SPDX-License-Identifier: CC0-1.0

"""Test object repr."""

from __future__ import annotations

from decimal import Decimal

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
