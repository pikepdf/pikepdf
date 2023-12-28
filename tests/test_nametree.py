# SPDX-FileCopyrightText: 2022 James R. Barlow
# SPDX-License-Identifier: CC0-1.0

from __future__ import annotations

import pytest

from pikepdf import Array, Dictionary, Name, NameTree, Object, Pdf

# pylint: disable=redefined-outer-name


@pytest.fixture
def outline(resources):
    with Pdf.open(resources / 'outlines.pdf') as pdf:
        yield pdf


def test_nametree_crud(outline):
    nt = NameTree(outline.Root.Names.Dests)
    assert nt.obj == outline.Root.Names.Dests
    assert '0' in nt
    assert isinstance(nt['0'], Object)
    assert 'foo' not in nt

    assert '3' in nt
    del nt['3']
    assert '3' not in nt

    nt['3'] = Dictionary(Entry=3)
    assert nt['3'].Entry == 3

    nt['newentry'] = Array([42])
    assert nt['newentry'] == Array([42])

    nt['py_newentry'] = 42

    nt.update(foo='bar')


def test_nametree_missing(outline):
    nt = NameTree(outline.Root.Names.Dests)
    with pytest.raises(KeyError):
        nt['does_not_exist']  # pylint: disable=pointless-statement
    with pytest.raises(KeyError):
        del nt['does_not_exist']


def test_nametree_iter(outline):
    count = 0
    nt = NameTree(outline.Root.Names.Dests)
    for name in nt:
        count += 1
        assert name in nt
    assert count == len(nt)

    assert '1' in nt.keys()
    assert len(nt.keys()) == len(nt.values()) == len(nt.items())
    assert nt == NameTree(outline.Root.Names.Dests)


def test_nametree_without_pdf():
    d = Dictionary()
    with pytest.raises(ValueError, match="owned"):
        _nt = NameTree(d)


def test_nametree_scratch(outline, outpdf, key='brand new name tree', val='yup'):
    nt = NameTree.new(outline)
    outline.Root.RandomNameTree = nt.obj
    nt[key] = val
    outline.save(outpdf)

    with Pdf.open(outpdf) as pdf:
        assert Name.Names in pdf.Root.RandomNameTree
        assert pdf.Root.RandomNameTree.Names[1] == val


def test_nametree_assign_setitem(outline):
    nt = NameTree.new(outline)
    with pytest.raises(
        TypeError,
        match=r"Can't convert ObjectHelper",
    ):
        outline.Root.RandomNameTree = nt
