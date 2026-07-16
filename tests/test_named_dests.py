# SPDX-FileCopyrightText: 2026 James R. Barlow
# SPDX-License-Identifier: CC0-1.0

from __future__ import annotations

from pikepdf import Array, Dictionary, Name, NameTree, Pdf
from pikepdf._named_dests import (
    lookup_named_destination_entry,
    resolve_named_destination,
)


def test_lookup_string_kind_hit():
    pdf = Pdf.new()
    page = pdf.add_blank_page()
    nt = NameTree.new(pdf)
    pdf.Root.Names = pdf.make_indirect(Dictionary(Dests=nt.obj))
    NameTree(pdf.Root.Names.Dests)['sec.1'] = pdf.make_indirect(
        Dictionary(D=Array([page.obj, Name.Fit]))
    )
    entry = lookup_named_destination_entry(pdf, 'sec.1', 'string')
    assert entry is not None
    assert entry.D == [page.obj, Name.Fit]


def test_lookup_name_kind_hit():
    pdf = Pdf.new()
    page = pdf.add_blank_page()
    pdf.Root.Dests = pdf.make_indirect(Dictionary())
    pdf.Root.Dests[Name.Chap1] = pdf.make_indirect(
        Dictionary(D=Array([page.obj, Name.Fit]))
    )
    entry = lookup_named_destination_entry(pdf, '/Chap1', 'name')
    assert entry is not None
    assert entry.D == [page.obj, Name.Fit]


def test_lookup_missing_returns_none():
    pdf = Pdf.new()
    pdf.add_blank_page()
    assert lookup_named_destination_entry(pdf, 'nope', 'string') is None
    assert lookup_named_destination_entry(pdf, '/Nope', 'name') is None


def test_lookup_missing_names_or_dests_dict_returns_none():
    # No /Names at all, and no /Dests at all.
    pdf = Pdf.new()
    pdf.add_blank_page()
    assert lookup_named_destination_entry(pdf, 'sec.1', 'string') is None
    assert lookup_named_destination_entry(pdf, '/Chap1', 'name') is None


def test_resolve_string_kind_dict_entry():
    pdf = Pdf.new()
    page = pdf.add_blank_page()
    nt = NameTree.new(pdf)
    pdf.Root.Names = pdf.make_indirect(Dictionary(Dests=nt.obj))
    NameTree(pdf.Root.Names.Dests)['sec.1'] = pdf.make_indirect(
        Dictionary(D=Array([page.obj, Name.Fit]))
    )
    arr = resolve_named_destination(pdf, 'sec.1', 'string')
    assert arr == [page.obj, Name.Fit]


def test_resolve_direct_array_entry():
    # A /Dests entry may be a bare destination array, not a dict with /D.
    pdf = Pdf.new()
    page = pdf.add_blank_page()
    pdf.Root.Dests = pdf.make_indirect(Dictionary())
    pdf.Root.Dests[Name.Chap1] = Array([page.obj, Name.Fit])
    arr = resolve_named_destination(pdf, '/Chap1', 'name')
    assert arr == [page.obj, Name.Fit]


def test_resolve_malformed_non_array_d_returns_none():
    pdf = Pdf.new()
    pdf.add_blank_page()
    pdf.Root.Dests = pdf.make_indirect(Dictionary())
    pdf.Root.Dests[Name.Bad] = pdf.make_indirect(Dictionary(D=Name.NotAnArray))
    assert resolve_named_destination(pdf, '/Bad', 'name') is None


def test_resolve_malformed_non_indirect_page_returns_none():
    pdf = Pdf.new()
    pdf.add_blank_page()
    pdf.Root.Dests = pdf.make_indirect(Dictionary())
    pdf.Root.Dests[Name.Bad] = pdf.make_indirect(Dictionary(D=Array([0, Name.Fit])))
    assert resolve_named_destination(pdf, '/Bad', 'name') is None


def test_resolve_missing_returns_none():
    pdf = Pdf.new()
    pdf.add_blank_page()
    assert resolve_named_destination(pdf, 'nope', 'string') is None
