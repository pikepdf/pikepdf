# SPDX-FileCopyrightText: 2022 James R. Barlow
# SPDX-License-Identifier: CC0-1.0

from __future__ import annotations

import pytest

import pikepdf
from pikepdf import Array, Dictionary, Name, NameTree, Object, Pdf, String

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


def test_nametree_contains_other_types(outline):
    nt = NameTree(outline.Root.Names.Dests)
    assert 5 not in nt
    assert None not in nt
    assert b'0' not in nt
    with pytest.raises(TypeError):
        nt[b'0']


def test_nametree_names_are_decoded_text():
    # qpdf reads each name as a PDF text string and orders and compares names
    # by that text, so names come back as str however the file encodes them.
    pdf = Pdf.new()
    names = [
        (b'caf\xe9', 'café'),  # PDFDocEncoding
        (b'plain', 'plain'),
        (b'\xfe\xff\x4e\x2d', '中'),  # UTF-16BE with a byte order mark
    ]
    items = []
    for n, (raw, _text) in enumerate(names):
        items.extend([String(raw), pdf.make_indirect(Dictionary(N=n))])
    nt = NameTree(pdf.make_indirect(Dictionary(Names=Array(items))))
    assert list(nt) == [text for _raw, text in names]
    assert all(isinstance(name, str) for name in nt.keys())
    for n, (_raw, text) in enumerate(names):
        assert nt[text].N == n


def test_nametree_iteration_is_a_snapshot(outline):
    nt = NameTree.new(outline)
    for name in 'abc':
        nt[name] = Dictionary()
    seen = []
    for name in nt:
        seen.append(name)
        nt[name + name] = Dictionary()
    assert seen == ['a', 'b', 'c']
    assert len(nt) == 6


def test_nametree_set_python_values(outline):
    nt = NameTree.new(outline)
    nt['list'] = [1, 'two', Name.Three]
    nt['dict'] = {'/A': 1}
    assert nt['list'] == Array([1, 'two', Name.Three])
    assert nt['dict'].A == 1
    with pytest.raises(ValueError, match='NaN'):
        nt['nan'] = float('nan')
    with pytest.raises(RuntimeError, match="don't know how to encode"):
        nt['object'] = object()
    assert 'nan' not in nt
    assert 'object' not in nt


def test_nametree_refuses_object_of_another_pdf(outline):
    other = Pdf.new()
    foreign = other.make_indirect(Dictionary(A=1))
    nt = NameTree.new(outline)
    with pytest.raises(pikepdf.ForeignObjectError):
        nt['foreign'] = foreign
    assert 'foreign' not in nt
    nt['copied'] = outline.copy_foreign(foreign)
    assert nt['copied'].A == 1
