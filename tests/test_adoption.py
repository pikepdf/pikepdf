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


def _source_pdf(tag):
    pdf = pikepdf.new()
    pdf.Root.Ind = pdf.make_indirect(Dictionary(Tag=pikepdf.String(tag)))
    pdf.Root.Dir = Dictionary(Tag=pikepdf.String(tag))
    pdf.add_blank_page()
    return pdf


def _insert_dict(dst, value):
    dst.Root.Target = value


def _insert_dict_setitem(dst, value):
    dst.Root['/Target'] = value


def _insert_update(dst, value):
    dst.Root.update({'/Target': value})


def _insert_namepath(dst, value):
    dst.Root[pikepdf.NamePath.Target] = value


def _insert_array_append(dst, value):
    dst.Root.Arr.append(value)


def _insert_array_insert(dst, value):
    dst.Root.Arr.insert(0, value)


def _insert_array_extend(dst, value):
    dst.Root.Arr.extend([1, value])


def _insert_array_setitem(dst, value):
    dst.Root.Arr[0] = value


def _insert_array_slice(dst, value):
    dst.Root.Arr[0:1] = [1, value]


def _insert_make_indirect(dst, value):
    dst.make_indirect(value)


def _insert_with_same_owner_as(dst, value):
    value.with_same_owner_as(dst.Root)


def _insert_stream_key(dst, value):
    dst.Root.Strm.stream_dict.Target = value


def _insert_stream_ctor(dst, value):
    pikepdf.Stream(dst, b'x', Target=value)


def _insert_add_resource(dst, value):
    dst.pages[0].add_resource(value, Name.XObject)


def _insert_nametree(dst, value):
    NameTree(dst.Root.NT)['k'] = value


def _insert_numbertree(dst, value):
    pikepdf.NumberTree(dst.Root.NumT)[1] = value


_INSERTERS = [
    _insert_dict,
    _insert_dict_setitem,
    _insert_update,
    _insert_namepath,
    _insert_array_append,
    _insert_array_insert,
    _insert_array_extend,
    _insert_array_setitem,
    _insert_array_slice,
    _insert_make_indirect,
    _insert_with_same_owner_as,
    _insert_stream_key,
    _insert_stream_ctor,
    _insert_add_resource,
    _insert_nametree,
    _insert_numbertree,
]


def _foreign_indirect(src):
    return Dictionary(P=src.Root.Ind)


def _foreign_indirect_nested(src):
    return Array([Dictionary(Inner=Array([src.Root.Ind]))])


def _foreign_direct_nested(src):
    return Dictionary(Inner=src.Root.Dir)


class TestRefusesMixedOwners:
    """A value that refers to another Pdf is refused when it is inserted.

    A Dictionary or Array that belongs to no Pdf may hold anything. Inserting
    it adopts it and its direct children, so that is where an object from
    another Pdf is found and refused, before the target is changed at all.
    """

    @pytest.fixture
    def dst(self):
        pdf = _source_pdf('dst')
        pdf.Root.Arr = Array([0])
        pdf.Root.Strm = pikepdf.Stream(pdf, b'x')
        pdf.Root.NT = NameTree.new(pdf).obj
        pdf.Root.NumT = pikepdf.NumberTree.new(pdf).obj
        return pdf

    @staticmethod
    def _snapshot(pdf):
        return (
            repr(pdf.Root),
            len(pdf.objects),
            repr(pdf.pages[0].obj),
        )

    @pytest.mark.parametrize('insert', _INSERTERS, ids=lambda f: f.__name__[8:])
    @pytest.mark.parametrize(
        'make',
        [_foreign_indirect, _foreign_indirect_nested, _foreign_direct_nested],
        ids=lambda f: f.__name__[1:],
    )
    def test_refused_and_target_unchanged(self, dst, insert, make):
        src = _source_pdf('src')
        value = make(src)
        before = self._snapshot(dst)
        with pytest.raises(ForeignObjectError):
            insert(dst, value)
        assert self._snapshot(dst) == before
        assert not value.is_owned_by(dst)

    def test_page_with_foreign_child_refused(self, dst):
        src = _source_pdf('src')
        page = pikepdf.Page(
            Dictionary(Type=Name.Page, MediaBox=[0, 0, 1, 1], X=src.Root.Ind)
        )
        with pytest.raises(ForeignObjectError):
            dst.pages.append(page)
        with pytest.raises(ForeignObjectError):
            dst.pages.insert(0, page)
        assert len(dst.pages) == 1

    def test_error_names_the_path(self, dst):
        src = _source_pdf('src')
        with pytest.raises(ForeignObjectError, match=r'\[0\]/Inner\[0\]'):
            dst.Root.Target = _foreign_indirect_nested(src)

    def test_users_example(self):
        pdf1, pdf2, pdf3 = _source_pdf('1'), _source_pdf('2'), _source_pdf('3')
        d = Dictionary()
        d.P1 = pdf1.Root.Ind
        d.P2 = pdf2.Root.Ind
        with pytest.raises(ForeignObjectError, match='copy_foreign'):
            pdf3.Root.Obj3 = d
        assert '/Obj3' not in pdf3.Root

    def test_unowned_container_may_mix(self):
        pdf1, pdf2 = _source_pdf('1'), _source_pdf('2')
        d = Dictionary(P1=pdf1.Root.Ind, P2=pdf2.Root.Ind)
        assert str(d.P1.Tag) == '1'
        assert str(d.P2.Tag) == '2'

    def test_own_objects_accepted(self, dst):
        dst.Root.Target = Array([Dictionary(P=dst.Root.Ind, D=dst.Root.Dir)])
        assert str(dst.Root.Target[0].P.Tag) == 'dst'

    def test_copy_foreign_then_insert(self, dst):
        src = _source_pdf('src')
        dst.Root.Target = Dictionary(P=dst.copy_foreign(src.Root.Ind))
        assert dst.Root.Target.P.is_owned_by(dst)

    def test_reading_mixed_state_does_not_raise(self, dst):
        # The page from another Pdf is copied, which is allowed; reads of an
        # existing document must never trip the insertion check.
        src = _source_pdf('src')
        dst.pages.append(src.pages[0])
        assert repr(dst.pages[-1].obj)


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


class TestQpdfCreatedValuesAreAdoptedOnRead:
    """qpdf builds some values itself, which belong to no document until read.

    Reading one out of a container that belongs to a document must apply that
    document's settings, such as its conversion mode.
    """

    @pytest.fixture
    def pdf(self):
        pdf = Pdf.new(conversion_mode='explicit')
        pdf.add_blank_page()
        return pdf

    def test_count_after_add_page(self, pdf):
        assert isinstance(pdf.Root.Pages.Count, pikepdf.Integer)

    def test_count_after_remove_page(self, resources):
        with Pdf.open(resources / 'fourpages.pdf', conversion_mode='explicit') as pdf:
            del pdf.pages[0]
            assert isinstance(pdf.Root.Pages.Count, pikepdf.Integer)

    def test_rotate(self, pdf):
        pdf.pages[0].rotate(90, relative=False)
        assert isinstance(pdf.pages[0].Rotate, pikepdf.Integer)

    @pytest.mark.parametrize(
        'read',
        [
            lambda pages: pages['/Count'],
            lambda pages: pages[Name.Count],
            lambda pages: pages.get('/Count'),
            lambda pages: pages.get(Name.Count),
            lambda pages: dict(pages.items())['/Count'],
            lambda pages: [v for v in pages.values() if not isinstance(v, Array)][0],  # noqa: RUF015
            lambda pages: pages.as_dict()['/Count'],
            lambda pages: pages.as_dict(default=None)['/Count'],
        ],
        ids=[
            'getitem',
            'getitem_name',
            'get',
            'get_name',
            'items',
            'values',
            'as_dict',
            'as_dict_default',
        ],
    )
    def test_dictionary_read_paths(self, pdf, read):
        assert isinstance(read(pdf.Root.Pages), pikepdf.Integer)

    def test_namepath(self, pdf):
        assert isinstance(pdf.Root[pikepdf.NamePath.Pages.Count], pikepdf.Integer)

    def test_value_is_owned_after_read(self, pdf):
        pdf.Root.Pages.Count
        assert pdf.Root.Pages.get_raw('/Count').is_owned_by(pdf)

    @pytest.fixture
    def bbox_parent(self, pdf):
        # qpdf builds the form XObject's /BBox array and its numbers itself
        return pdf.pages[0].as_form_xobject()

    @pytest.mark.parametrize(
        'read',
        [
            lambda bbox: bbox[0],
            lambda bbox: bbox[0:1][0],
            lambda bbox: list(bbox)[0],  # noqa: RUF015
            lambda bbox: bbox.as_list()[0],
            lambda bbox: bbox.as_list(default=None)[0],
        ],
        ids=['getitem', 'slice', 'iter', 'as_list', 'as_list_default'],
    )
    def test_array_read_paths(self, bbox_parent, read):
        assert isinstance(read(bbox_parent.BBox), pikepdf.Integer)

    def test_qpdf_created_container_is_owned_after_read(self, pdf, bbox_parent):
        bbox_parent.BBox
        assert bbox_parent.get_raw('/BBox').is_owned_by(pdf)
