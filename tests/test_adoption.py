# SPDX-FileCopyrightText: 2025 James R. Barlow
# SPDX-License-Identifier: CC0-1.0

"""Robustness of object adoption.

A direct object inserted into a Pdf is tagged with that document as its owner.
These tests cover what happens when the document dies while the object lives on,
when the object is detached from the document, and when an object that already
belongs to one document is offered to another.
"""

from __future__ import annotations

import gc

import pytest

import pikepdf
from pikepdf import Array, Dictionary, ForeignObjectError, Name, NameTree, Pdf


class TestOwnerDeathDisconnects:
    """The Pdf's destructor must disconnect every object it adopted."""

    def test_detached_dict_survives_owner(self):
        pdf = pikepdf.new()
        d = Dictionary(A=1)
        pdf.Root.D = d
        del pdf.Root['/D']
        pdf.close()
        del pdf
        gc.collect()

        assert repr(d)  # would segfault if d still pointed at the freed QPDF
        assert int(d.A) == 1

    def test_replaced_dict_survives_owner(self):
        pdf = pikepdf.new()
        d = Dictionary(A=1)
        pdf.Root.D = d
        pdf.Root.D = Dictionary(B=2)
        del pdf
        gc.collect()

        assert repr(d)
        assert int(d.A) == 1

    def test_scalar_survives_owner(self):
        pdf = pikepdf.new()
        pdf.Root.N = 42
        scalar = pdf.Root.get_raw('/N')
        assert scalar.is_owned_by(pdf)
        del pdf.Root['/N']
        del pdf
        gc.collect()

        assert repr(scalar)
        assert int(scalar) == 42

    def test_nested_children_survive_owner(self):
        pdf = pikepdf.new()
        d = Dictionary(A=Dictionary(B=Array([1, 2, 3])))
        pdf.Root.D = d
        inner = d.A.B
        del pdf.Root['/D']
        del pdf
        gc.collect()

        assert repr(inner)
        assert len(inner) == 3

    def test_many_adoptions_are_pruned(self):
        # Exercise the amortised pruning path: adopt far more objects than the
        # prune threshold, letting most of them expire.
        pdf = pikepdf.new()
        for n in range(500):
            pdf.Root.Temp = Dictionary(N=n)
        keep = Dictionary(Last=1)
        pdf.Root.Temp = keep
        del pdf
        gc.collect()
        assert repr(keep)


class TestDetachmentDisconnects:
    """Removing an object from a Pdf must release its claim on the object."""

    def test_del_key_releases(self):
        a, b = pikepdf.new(), pikepdf.new()
        d = Dictionary(A=1)
        a.Root.T = d
        del a.Root.T
        b.Root.T = d
        assert d.is_owned_by(b)

    def test_del_key_via_namepath_releases(self):
        a, b = pikepdf.new(), pikepdf.new()
        d = Dictionary(A=1)
        a.Root.T = d
        del a.Root[pikepdf.NamePath.T]
        b.Root.T = d
        assert d.is_owned_by(b)

    def test_replace_key_releases(self):
        a, b = pikepdf.new(), pikepdf.new()
        d = Dictionary(A=1)
        a.Root.T = d
        a.Root.T = Dictionary()
        b.Root.T = d
        assert d.is_owned_by(b)

    def test_setting_same_value_keeps_ownership(self):
        a = pikepdf.new()
        d = Dictionary(A=1)
        a.Root.T = d
        a.Root.T = d
        assert d.is_owned_by(a)
        assert int(a.Root.T.A) == 1

    def test_array_delitem_releases(self):
        a, b = pikepdf.new(), pikepdf.new()
        d = Dictionary(A=1)
        a.Root.Arr = Array([d])
        del a.Root.Arr[0]
        b.Root.T = d
        assert d.is_owned_by(b)

    def test_array_del_slice_releases(self):
        a, b = pikepdf.new(), pikepdf.new()
        d = Dictionary(A=1)
        a.Root.Arr = Array([d, Dictionary()])
        del a.Root.Arr[0:2]
        b.Root.T = d
        assert d.is_owned_by(b)

    def test_array_setitem_releases(self):
        a, b = pikepdf.new(), pikepdf.new()
        d = Dictionary(A=1)
        a.Root.Arr = Array([d])
        a.Root.Arr[0] = Dictionary(Z=1)
        b.Root.T = d
        assert d.is_owned_by(b)

    def test_array_setitem_slice_releases(self):
        a, b = pikepdf.new(), pikepdf.new()
        d = Dictionary(A=1)
        a.Root.Arr = Array([d, Dictionary()])
        a.Root.Arr[0:1] = [Dictionary(Z=1)]
        b.Root.T = d
        assert d.is_owned_by(b)

    def test_array_pop_releases(self):
        a, b = pikepdf.new(), pikepdf.new()
        d = Dictionary(A=1)
        a.Root.Arr = Array([d])
        popped = a.Root.Arr.pop()
        assert not popped.is_owned_by(a)
        b.Root.T = d
        assert d.is_owned_by(b)

    def test_array_remove_releases(self):
        a, b = pikepdf.new(), pikepdf.new()
        d = Dictionary(A=1)
        a.Root.Arr = Array([d])
        a.Root.Arr.remove(d)
        b.Root.T = d
        assert d.is_owned_by(b)

    def test_array_clear_releases(self):
        a, b = pikepdf.new(), pikepdf.new()
        d = Dictionary(A=1)
        a.Root.Arr = Array([d])
        a.Root.Arr.clear()
        b.Root.T = d
        assert d.is_owned_by(b)

    def test_namepath_index_setitem_releases(self):
        a, b = pikepdf.new(), pikepdf.new()
        d = Dictionary(A=1)
        a.Root.Arr = Array([d])
        a.Root[pikepdf.NamePath.Arr[0]] = Dictionary(Z=1)
        b.Root.T = d
        assert d.is_owned_by(b)

    def test_indirect_object_is_not_disconnected(self):
        a = pikepdf.new()
        i = a.make_indirect(Dictionary(A=1))
        a.Root.T = i
        del a.Root.T
        assert i.is_owned_by(a)
        assert int(i.A) == 1

    def test_aliased_object_is_disconnected_but_readable(self):
        # Known edge case: an object reachable under two keys is disconnected
        # when either key is removed. The value is untouched and still reads.
        a = pikepdf.new()
        d = Dictionary(X=1)
        a.Root.A = d
        a.Root.B = d
        del a.Root.A
        assert int(a.Root.B.X) == 1


class TestRefusesToSteal:
    def test_with_same_owner_as_refuses(self):
        a, b = pikepdf.new(), pikepdf.new()
        d = Dictionary(A=1)
        a.Root.Kid = d
        with pytest.raises(ForeignObjectError, match='another Pdf'):
            d.with_same_owner_as(b.Root)

    def test_make_indirect_refuses(self):
        a, b = pikepdf.new(), pikepdf.new()
        d = Dictionary(A=1)
        a.Root.Kid = d
        with pytest.raises(ForeignObjectError, match='another Pdf'):
            b.make_indirect(d)

    def test_succeeds_after_removal(self):
        a, b = pikepdf.new(), pikepdf.new()
        d = Dictionary(A=1)
        a.Root.Kid = d
        del a.Root.Kid
        assert d.with_same_owner_as(b.Root).is_owned_by(b)

        e = Dictionary(A=1)
        a.Root.Kid = e
        del a.Root.Kid
        assert b.make_indirect(e).is_owned_by(b)

    def test_make_indirect_in_owning_pdf_is_allowed(self):
        a = pikepdf.new()
        d = Dictionary(A=1)
        a.Root.Kid = d
        i = a.make_indirect(d)
        assert i.is_owned_by(a)


class TestDescriptions:
    def test_make_indirect_object_is_owned(self):
        pdf = pikepdf.new()
        i = pdf.make_indirect(Dictionary(A=1))
        assert i.is_indirect
        assert i.is_owned_by(pdf)
        assert i.get_raw('/A').is_owned_by(pdf)

    def test_stream_dict_children_are_owned(self):
        pdf = pikepdf.new()
        s = pikepdf.Stream(pdf, b'x', W=1)
        assert int(s.stream_dict.W) == 1
        assert s.stream_dict.get_raw('/W').is_owned_by(pdf)

    def test_stream_dict_setter_children_are_owned(self):
        pdf = pikepdf.new()
        s = pikepdf.Stream(pdf, b'x')
        s.stream_dict = Dictionary(W=1)
        assert int(s.stream_dict.W) == 1
        assert s.stream_dict.get_raw('/W').is_owned_by(pdf)


class TestCopiedObjectsAreAdopted:
    def test_copy_foreign_adopts_children(self, resources):
        src = Pdf.open(resources / 'pal-1bit-trivial.pdf')
        dst = Pdf.new()
        page = dst.copy_foreign(src.pages[0].obj)
        assert page.get_raw('/MediaBox').is_owned_by(dst)

    def test_pages_append_adopts_children(self, resources):
        src = Pdf.open(resources / 'pal-1bit-trivial.pdf')
        dst = Pdf.new(conversion_mode='explicit')
        dst.pages.append(src.pages[0])
        mediabox = dst.pages[0].obj.get_raw('/MediaBox')
        assert mediabox.is_owned_by(dst)
        assert isinstance(mediabox[2], pikepdf.Integer | pikepdf.Real)

    def test_pages_extend_adopts_children(self, resources):
        src = Pdf.open(resources / 'pal-1bit-trivial.pdf')
        dst = Pdf.new()
        dst.pages.extend(src.pages)
        assert dst.pages[0].obj.get_raw('/MediaBox').is_owned_by(dst)

    def test_with_same_owner_as_indirect_adopts_children(self, resources):
        src = Pdf.open(resources / 'pal-1bit-trivial.pdf')
        dst = Pdf.new()
        copied = src.pages[0].obj.with_same_owner_as(dst.Root)
        assert copied.get_raw('/MediaBox').is_owned_by(dst)

    def test_nametree_setitem_adopts(self):
        dst = Pdf.new(conversion_mode='explicit')
        nt = NameTree.new(dst)
        nt['x'] = 5
        assert isinstance(nt['x'], pikepdf.Integer)

    def test_numbertree_setitem_adopts(self):
        dst = Pdf.new(conversion_mode='explicit')
        nt = pikepdf.NumberTree.new(dst)
        nt[1] = 5
        assert isinstance(nt[1], pikepdf.Integer)


def test_name_constant_reusable_across_pdfs():
    a, b = pikepdf.new(), pikepdf.new()
    a.Root.T = Name.Foo
    b.Root.T = Name.Foo
    assert a.Root.T == Name.Foo
    assert b.Root.T == Name.Foo


def test_readopted_object_survives_first_owner_death():
    """An object adopted by A, detached, and adopted by B stays B's when A dies."""
    a = pikepdf.new(conversion_mode='explicit')
    b = pikepdf.new(conversion_mode='explicit')
    t = Dictionary(K=1)
    a.Root.T = t
    del a.Root.T
    b.Root.T = t
    assert t.is_owned_by(b)
    a.close()
    del a
    gc.collect()
    assert t.is_owned_by(b)
    assert isinstance(b.Root.T.K, pikepdf.Integer)


SCALAR_FACTORIES = {
    'Name': lambda: Name('/Foo'),
    'String': lambda: pikepdf.String('text'),
    'Operator': lambda: pikepdf.Operator('q'),
    'Integer': lambda: pikepdf.Array([42])[0],
    'Real': lambda: pikepdf.Array([1.5])[0],
    'Boolean': lambda: pikepdf.Array([True])[0],
}


@pytest.mark.parametrize('how', ['make_indirect', 'with_same_owner_as'])
@pytest.mark.parametrize('kind', SCALAR_FACTORIES)
def test_making_scalar_indirect_leaves_caller_object_direct(how, kind):
    """Making a scalar indirect must not change the caller's handle.

    Scalars are hashable, so a handle turned indirect in place would stop
    hashing and break any dict or set that already holds it.
    """
    pdf = pikepdf.new()
    with pikepdf.explicit_conversion():
        scalar = SCALAR_FACTORIES[kind]()
        assert isinstance(scalar, pikepdf.Object)
        lookup = {scalar: 'value'}
        h = hash(scalar)
        if how == 'make_indirect':
            indirect = pdf.make_indirect(scalar)
        else:
            indirect = scalar.with_same_owner_as(pdf.Root)
        assert indirect.is_indirect
        assert indirect.is_owned_by(pdf)
        assert indirect == scalar
        assert not scalar.is_indirect
        assert hash(scalar) == h
        assert lookup[scalar] == 'value'

        other = pikepdf.new()
        other.Root.T = scalar
        assert other.Root.T == scalar


def test_making_container_indirect_keeps_alias():
    pdf = pikepdf.new()
    d = Dictionary(A=1)
    indirect = pdf.make_indirect(d)
    assert d.is_indirect
    indirect.B = 2
    assert d.B == 2


@pytest.mark.parametrize('kind', SCALAR_FACTORIES)
def test_scalar_read_from_one_pdf_assignable_to_another(kind):
    """A scalar owned by one Pdf is copied, not refused, when put in another."""
    a, b = pikepdf.new(), pikepdf.new()
    with pikepdf.explicit_conversion():
        a.Root.T = SCALAR_FACTORIES[kind]()
        value = a.Root.get_raw('/T')
        assert value.is_owned_by(a)
        b.Root.T = value
        b.Root.A = Array([value])
        assert b.Root.get_raw('/T').is_owned_by(b)
        assert b.Root.A[0].is_owned_by(b)
        assert value.is_owned_by(a)
        indirect = b.make_indirect(value)
        assert indirect.is_owned_by(b)
        assert indirect == value
        assert value.is_owned_by(a)
        assert not value.is_indirect


def test_parsed_scalar_assignable_to_another_pdf(resources):
    with pikepdf.open(resources / 'graph.pdf') as a:
        b = pikepdf.new()
        b.Root.T = a.Root.Type
        assert b.Root.T == Name.Catalog
        assert b.make_indirect(a.Root.Type) == Name.Catalog
