# SPDX-FileCopyrightText: 2026 Khushwant Parihar
# SPDX-License-Identifier: CC0-1.0

from __future__ import annotations

from decimal import Decimal
from io import BytesIO

import pytest
from conftest import set_structure_contents as set_contents
from conftest import structure_registration_failure

import pikepdf
import pikepdf.models as pikepdf_models
import pikepdf.models.structure as structure
from pikepdf import (
    Array,
    ContentMarker,
    Dictionary,
    MarkedContentRef,
    Name,
    NameTree,
    ObjectRef,
    Pdf,
    String,
    StructElem,
    StructTree,
    StructureTreeError,
    mark_text_runs,
    next_mcid,
)


class TestStructTreeCreation:
    def test_absent(self, blank):
        expected_exports = (
            'ContentMarker',
            'FontUsage',
            'MarkedContent',
            'MarkedContentRef',
            'ObjectRef',
            'ParentTree',
            'StructElem',
            'StructTree',
            'StructureTreeError',
            'find_font_usage',
            'find_marked_content',
            'mark_text_runs',
            'next_mcid',
        )
        assert tuple(structure.__all__) == expected_exports
        for name in expected_exports:
            assert getattr(structure, name) is getattr(pikepdf_models, name)
            assert getattr(structure, name) is getattr(pikepdf, name)

        tree = blank.open_structure_tree()
        assert not tree.exists
        assert tree.kids == []
        assert len(tree) == 0
        assert list(tree) == []
        assert 'no structure tree' in repr(tree)
        with pytest.raises(StructureTreeError, match="no structure tree"):
            _ = tree.obj

    def test_create_is_idempotent(self, blank):
        tree = blank.open_structure_tree()
        assert tree.create() is tree
        objgen = tree.obj.objgen
        tree.create()
        assert tree.obj.objgen == objgen
        assert tree.exists
        assert tree.marked
        assert tree.obj.Type == Name.StructTreeRoot
        assert tree.parent_tree.next_key == 0

    @pytest.mark.parametrize('malformed', [Array([]), String('bad')])
    def test_create_does_not_overwrite_malformed_struct_tree_root(
        self, blank, malformed
    ):
        blank.Root.StructTreeRoot = malformed
        tree = blank.open_structure_tree()

        with pytest.raises(StructureTreeError, match="must be a dictionary"):
            tree.create()

        assert blank.Root.StructTreeRoot == malformed
        assert Name.MarkInfo not in blank.Root

    def test_present_malformed_struct_tree_root_is_not_treated_as_absent(self, blank):
        blank.Root.StructTreeRoot = 42
        tree = blank.open_structure_tree()

        assert tree.exists
        with pytest.raises(StructureTreeError, match='must be a dictionary'):
            _ = tree.kids
        with pytest.raises(StructureTreeError, match='must be a dictionary'):
            list(tree.walk())
        assert tree.validate(check_content=False) == [
            'Document catalog /StructTreeRoot is not a dictionary'
        ]
        assert repr(tree) == '<pikepdf.StructTree: malformed structure tree>'

    def test_add_rejects_wrong_struct_tree_root_type_without_mutation(self, blank):
        root = blank.make_indirect(Dictionary(Type=Name.Catalog))
        blank.Root.StructTreeRoot = root
        tree = blank.open_structure_tree()

        with pytest.raises(StructureTreeError, match="wrong /Type"):
            tree.add(Name.P)

        assert blank.Root.StructTreeRoot.objgen == root.objgen
        assert Name.K not in root
        assert Name.MarkInfo not in blank.Root

    def test_create_repairs_a_missing_struct_tree_root_type(self, blank):
        root = blank.make_indirect(Dictionary(K=Array([])))
        blank.Root.StructTreeRoot = root

        blank.open_structure_tree().create()

        assert root.Type == Name.StructTreeRoot
        assert blank.Root.MarkInfo.Marked

    @pytest.mark.parametrize('operation', ['create', 'add', 'marked'])
    def test_malformed_mark_info_is_never_overwritten(self, blank, operation):
        malformed = String('bad')
        blank.Root.MarkInfo = malformed
        tree = blank.open_structure_tree()

        with pytest.raises(StructureTreeError, match="must be a dictionary"):
            if operation == 'create':
                tree.create()
            elif operation == 'add':
                tree.add(Name.P)
            else:
                tree.marked = True

        assert blank.Root.MarkInfo == malformed
        assert Name.StructTreeRoot not in blank.Root

    def test_malformed_mark_info_does_not_trigger_root_type_repair(self, blank):
        root = blank.make_indirect(Dictionary(K=Array([])))
        blank.Root.StructTreeRoot = root
        blank.Root.MarkInfo = String('bad')

        with pytest.raises(StructureTreeError, match="/MarkInfo"):
            blank.open_structure_tree().create()

        assert Name.Type not in root

    def test_add_creates_tree(self, blank):
        tree = blank.open_structure_tree()
        doc = tree.add(Name.Document)
        assert tree.exists
        assert isinstance(doc, StructElem)
        assert tree.kids == [doc]
        assert doc.obj.P.objgen == tree.obj.objgen

    def test_open_structure_tree_returns_new_view(self, blank):
        assert isinstance(blank.open_structure_tree(), StructTree)
        blank.open_structure_tree().add(Name.Document)
        assert blank.open_structure_tree().exists

    def test_marked_setter(self, blank):
        tree = blank.open_structure_tree()
        assert not tree.marked
        tree.marked = True
        assert tree.marked
        assert blank.Root.MarkInfo.Marked
        tree.marked = False
        assert not tree.marked

    @pytest.mark.parametrize('kind', ['string', 'integer', 'name'])
    def test_marked_rejects_truthy_non_booleans(self, blank, kind):
        values = {'string': String('bad'), 'integer': 1, 'name': Name.Yes}
        tree = blank.open_structure_tree().create()
        blank.Root.MarkInfo = Dictionary(Marked=values[kind])

        assert tree.marked is False
        assert any('not a boolean' in problem for problem in tree.validate())

    def test_marked_handles_explicit_conversion(self, blank):
        tree = blank.open_structure_tree().create()
        blank.Root.MarkInfo = Dictionary(Marked=String('bad'))

        with pikepdf.explicit_conversion():
            assert tree.marked is False
            assert any('not a boolean' in problem for problem in tree.validate())
            tree.marked = True
            assert tree.marked is True

    def test_marked_setter_requires_bool(self, blank):
        tree = blank.open_structure_tree().create()

        with pytest.raises(TypeError, match='marked must be a bool'):
            tree.marked = 1  # type: ignore[assignment]

        assert tree.marked is True

    def test_add_to_non_array_k(self, blank):
        tree = blank.open_structure_tree().create()
        first = tree.add(Name.Document)
        tree.obj.K = first.obj
        second = tree.add(Name.Part)
        assert [k.obj.objgen for k in tree.kids] == [
            first.obj.objgen,
            second.obj.objgen,
        ]

    def test_remove(self, blank):
        tree = blank.open_structure_tree()
        elem = tree.add(Name.Document, page=blank.pages[0])
        elem.add_content(blank.pages[0], 0)
        tree.remove()
        assert not tree.exists
        assert Name.MarkInfo not in blank.Root
        assert Name.StructParents not in blank.pages[0].obj


class TestStructElem:
    def test_properties_round_trip(self, blank):
        page = blank.pages[0]
        tree = blank.open_structure_tree()
        elem = tree.add(
            Name.Figure,
            page=page,
            alt="a picture",
            actual_text="cat",
            expansion="Aitch One",
            lang="en-US",
            title="Figure 1",
        )
        assert elem.tag == Name.Figure
        assert elem.page.obj.objgen == page.obj.objgen
        assert elem.alt == "a picture"
        assert elem.actual_text == "cat"
        assert elem.expansion == "Aitch One"
        assert elem.lang == "en-US"
        assert elem.title == "Figure 1"
        assert elem.element_id is None
        assert elem.attributes is None
        assert elem.namespace is None

    def test_properties_clear(self, blank):
        tree = blank.open_structure_tree()
        elem = tree.add(Name.P, page=blank.pages[0], alt="x", lang="en")
        elem.alt = None
        elem.lang = None
        elem.page = None
        assert Name.Alt not in elem.obj
        assert Name.Lang not in elem.obj
        assert Name.Pg not in elem.obj
        assert elem.page is None
        assert elem.alt is None

    def test_settable_properties(self, blank):
        tree = blank.open_structure_tree()
        elem = tree.add(Name.P)
        elem.tag = Name.H1
        elem.actual_text = "text"
        elem.expansion = "exp"
        elem.title = "title"
        elem.element_id = "id-1"
        elem.attributes = Dictionary(O=Name.Layout)
        elem.namespace = blank.make_indirect(
            Dictionary(Type=Name.Namespace, NS=String('urn:example'))
        )
        elem.page = blank.pages[0].obj
        assert elem.tag == Name.H1
        assert elem.obj.ActualText == String("text")
        assert elem.obj.E == String("exp")
        assert elem.obj.T == String("title")
        assert elem.obj.ID == String("id-1")
        assert elem.attributes.O == Name.Layout
        assert elem.namespace.Type == Name.Namespace
        assert elem.page.obj.objgen == blank.pages[0].obj.objgen
        elem.attributes = None
        elem.namespace = None
        assert Name.A not in elem.obj
        assert Name.NS not in elem.obj

    @pytest.mark.parametrize(
        ('key', 'attribute'),
        [
            (Name.Alt, 'alt'),
            (Name.ActualText, 'actual_text'),
            (Name.E, 'expansion'),
            (Name.Lang, 'lang'),
            (Name.T, 'title'),
        ],
    )
    def test_text_properties_reject_malformed_values(self, blank, key, attribute):
        elem = blank.open_structure_tree().add(Name.P)
        elem.obj[key] = Name.Bad

        with pytest.raises(StructureTreeError, match='text string'):
            getattr(elem, attribute)

        assert any(
            str(key) in problem and 'text string' in problem
            for problem in elem.tree.validate(check_content=False)
        )

    def test_missing_tag(self, blank):
        tree = blank.open_structure_tree().create()
        elem = StructElem(blank.make_indirect(Dictionary(Type=Name.StructElem)), tree)
        with pytest.raises(StructureTreeError, match="/S"):
            _ = elem.tag

    def test_must_wrap_dictionary(self, blank):
        tree = blank.open_structure_tree()
        with pytest.raises(TypeError):
            StructElem(Array([]), tree)

    def test_tag_must_be_name(self, blank):
        tree = blank.open_structure_tree()
        with pytest.raises(TypeError, match="pikepdf.Name"):
            tree.add('/P')
        assert not tree.exists
        elem = tree.add(Name.P)
        with pytest.raises(TypeError, match="pikepdf.Name"):
            elem.tag = '/H1'
        assert elem.tag == Name.P

    def test_nesting(self, blank):
        tree = blank.open_structure_tree()
        doc = tree.add(Name.Document)
        sect = doc.add_child(Name.Sect)
        para = sect.add_child(Name.P)
        assert doc.children == [sect]
        assert list(doc) == [sect]
        assert len(doc) == 1
        assert para.parent == sect
        assert sect.parent == doc
        assert doc.parent is None
        assert [str(e.tag) for e in tree.walk()] == ['/Document', '/Sect', '/P']
        assert [str(e.tag) for e in doc.walk()] == ['/Document', '/Sect', '/P']
        assert list(tree.elements_with_tag(Name.P)) == [para]
        assert 'with 1 children' in repr(doc)

    @pytest.mark.parametrize(
        'parent',
        [None, 42, Dictionary(), Dictionary(Type=Name.Page)],
    )
    def test_parent_rejects_malformed_values(self, blank, parent):
        tree = blank.open_structure_tree()
        elem = tree.add(Name.P)
        if parent is None:
            del elem.obj[Name.P]
        elif isinstance(parent, Dictionary) and parent.get(Name.Type) == Name.Page:
            elem.obj.P = blank.make_indirect(parent)
        else:
            elem.obj.P = parent

        with pytest.raises(StructureTreeError, match='/P'):
            _ = elem.parent

    def test_parent_rejects_a_foreign_or_wrong_tree_parent(self):
        with Pdf.new() as first, Pdf.new() as second:
            first.add_blank_page()
            second.add_blank_page()
            tree = first.open_structure_tree()
            elem = tree.add(Name.P)
            foreign = second.open_structure_tree().add(Name.P)
            foreign_child = StructElem(
                Dictionary(Type=Name.StructElem, S=Name.P, P=foreign.obj), tree
            )

            with pytest.raises(StructureTreeError, match='another PDF'):
                _ = foreign_child.parent

            other_root = first.make_indirect(
                Dictionary(Type=Name.StructTreeRoot, K=Array([]))
            )
            elem.obj.P = other_root
            with pytest.raises(StructureTreeError, match='another structure tree'):
                _ = elem.parent

    def test_page_getter_rejects_an_invalid_effective_page(self, blank):
        elem = blank.open_structure_tree().add(Name.P)
        elem.obj.Pg = 42

        with pytest.raises(StructureTreeError, match='invalid effective /Pg'):
            _ = elem.page

    def test_page_getter_rejects_malformed_ancestry(self, blank):
        elem = blank.open_structure_tree().add(Name.P)
        elem.obj.P = 42

        with pytest.raises(StructureTreeError, match='missing or malformed /P'):
            _ = elem.page

    def test_page_getter_rejects_an_ancestry_cycle(self, blank):
        tree = blank.open_structure_tree()
        parent = tree.add(Name.Sect)
        child = parent.add_child(Name.P)
        parent.obj.P = child.obj
        try:
            with pytest.raises(StructureTreeError, match='ancestry contains a cycle'):
                _ = child.page
        finally:
            parent.obj.P = tree.obj

    def test_element_id_getter_rejects_a_non_string(self, blank):
        elem = blank.open_structure_tree().add(Name.P)
        elem.obj.ID = Name.Bad

        with pytest.raises(StructureTreeError, match='/ID must be a string'):
            _ = elem.element_id

    def test_element_wraps_existing(self, blank):
        tree = blank.open_structure_tree()
        doc = tree.add(Name.Document)
        assert tree.element(doc.obj) == doc
        with pytest.raises(StructureTreeError, match="Not a structure element"):
            tree.element(blank.make_indirect(Dictionary(Type=Name.Page)))

    def test_element_without_type_key(self, blank):
        tree = blank.open_structure_tree().create()
        obj = blank.make_indirect(Dictionary(S=Name.P, P=tree.obj))
        tree.obj.K = Array([obj])
        assert [str(e.tag) for e in tree.walk()] == ['/P']

    def test_bad_kid(self, blank):
        tree = blank.open_structure_tree()
        doc = tree.add(Name.Document)
        doc.obj.K = Array([String("nonsense")])
        with pytest.raises(StructureTreeError, match="Unexpected object"):
            _ = doc.kids
        doc.obj.K = Array([Dictionary(Type=Name.Whatever)])
        with pytest.raises(StructureTreeError, match="Unexpected dictionary"):
            _ = doc.kids

    def test_cycle_is_not_infinite(self, blank):
        tree = blank.open_structure_tree()
        doc = tree.add(Name.Document)
        sect = doc.add_child(Name.Sect)
        sect.obj.K = Array([doc.obj])

        with pytest.raises(StructureTreeError, match='cycle'):
            list(tree.walk())

    def test_max_depth(self, blank):
        tree = blank.open_structure_tree(max_depth=1)
        doc = tree.add(Name.Document)
        doc.add_child(Name.Sect).add_child(Name.P)
        assert [str(e.tag) for e in tree.walk()] == ['/Document', '/Sect']

    @pytest.mark.parametrize(
        ('max_depth', 'error'),
        [(True, TypeError), (1.5, TypeError), (-1, ValueError)],
    )
    def test_max_depth_requires_a_nonnegative_integer(self, blank, max_depth, error):
        with pytest.raises(error):
            StructTree(blank, max_depth=max_depth)
        with pytest.raises(error):
            blank.open_structure_tree(max_depth=max_depth)

        assert list(blank.open_structure_tree(max_depth=0).walk()) == []


class TestReferenceSerialization:
    @pytest.mark.parametrize('item', [True, 1.5, String('bad')])
    def test_marked_content_ref_from_object_rejects_invalid_types(self, blank, item):
        with pytest.raises((TypeError, ValueError)):
            MarkedContentRef.from_object(item, blank.pages[0].obj)

    @pytest.mark.parametrize('item', [42, True, 1.5])
    def test_object_ref_from_object_rejects_invalid_types(self, blank, item):
        with pytest.raises(TypeError):
            ObjectRef.from_object(item, blank.pages[0].obj)

    def test_marked_content_ref_to_object(self, blank):
        page = blank.pages[0].obj
        other = blank.add_blank_page().obj
        assert MarkedContentRef(3).to_object(page) == 3
        assert MarkedContentRef(3, page).to_object(page) == 3
        assert MarkedContentRef(3, page).to_object(None).Pg == page
        moved = MarkedContentRef(3, other).to_object(page)
        assert moved.Type == Name.MCR
        assert moved.MCID == 3
        assert moved.Pg == other

    def test_marked_content_ref_with_stream(self, blank):
        page = blank.pages[0].obj
        xobj = blank.make_stream(b"", Type=Name.XObject, Subtype=Name.Form)
        page.OwnedStream = xobj
        ref = MarkedContentRef(1, page, stream=xobj, stream_owner=page)
        built = ref.to_object(page)
        assert built.Stm == xobj
        assert built.StmOwn == page

    def test_marked_content_ref_accepts_an_indirect_annotation_ap(self, blank):
        page = blank.pages[0].obj
        appearance = blank.make_stream(b'', Type=Name.XObject, Subtype=Name.Form)
        owner = blank.make_indirect(
            Dictionary(
                Type=Name.Annot,
                AP=blank.make_indirect(Dictionary(N=appearance)),
            )
        )

        built = MarkedContentRef(
            0,
            page,
            stream=appearance,
            stream_owner=owner,
        ).to_object(page)

        assert built.StmOwn == owner

    def test_marked_content_ref_stream_owner_requires_stream(self, blank):
        page = blank.pages[0].obj
        owner = blank.make_indirect(Dictionary())

        with pytest.raises(ValueError, match='stream_owner requires stream'):
            MarkedContentRef(3, page, stream_owner=owner).to_object(page)

    def test_marked_content_ref_equality_includes_stream_owner(self, blank):
        page = blank.pages[0].obj
        xobj = blank.make_stream(b"", Type=Name.XObject, Subtype=Name.Form)
        first_owner = blank.make_indirect(Dictionary(Type=Name.Annot))
        second_owner = blank.make_indirect(Dictionary(Type=Name.Annot))

        assert MarkedContentRef(
            1, page, stream=xobj, stream_owner=first_owner
        ) == MarkedContentRef(1, page, stream=xobj, stream_owner=first_owner)
        assert MarkedContentRef(
            1, page, stream=xobj, stream_owner=first_owner
        ) != MarkedContentRef(1, page, stream=xobj, stream_owner=second_owner)

    def test_identical_pages_are_not_conflated(self, blank):
        """Object.__eq__ compares dictionaries by value, so compare identity."""
        first = blank.pages[0]
        second = blank.add_blank_page()
        assert first.obj == second.obj
        tree = blank.open_structure_tree()
        elem = tree.add(Name.P, page=first)
        elem.add_content(second, 0)
        assert elem.obj.K[0].Type == Name.MCR
        assert elem.obj.K[0].Pg.objgen == second.obj.objgen
        assert second.obj.StructParents == 0
        assert Name.StructParents not in first.obj

    def test_object_ref_to_object(self, blank):
        page = blank.pages[0].obj
        other = blank.add_blank_page().obj
        annot = blank.make_indirect(Dictionary(Type=Name.Annot))
        assert Name.Pg not in ObjectRef(annot, page).to_object(page)
        assert ObjectRef(annot, other).to_object(page).Pg == other


class TestDocumentOwnership:
    @staticmethod
    def _two_pdfs():
        first = Pdf.new()
        second = Pdf.new()
        first.add_blank_page()
        second.add_blank_page()
        return first, second

    def test_elements_with_the_same_objgen_in_different_pdfs_are_not_equal(self):
        first, second = self._two_pdfs()
        with first, second:
            first_elem = first.open_structure_tree().add(Name.P)
            second_elem = second.open_structure_tree().add(Name.P)
            assert first_elem.obj.objgen == second_elem.obj.objgen
            assert first_elem != second_elem

    def test_add_rejects_a_foreign_page_before_creating_the_tree(self):
        first, second = self._two_pdfs()
        with first, second:
            tree = first.open_structure_tree()
            with pytest.raises(StructureTreeError, match="different PDF"):
                tree.add(Name.P, page=second.pages[0])
            assert not tree.exists

    @pytest.mark.parametrize(
        'kwargs',
        [
            {'alt': 1},
            {'actual_text': True},
            {'attributes': 'bad'},
        ],
    )
    def test_invalid_element_fields_do_not_create_a_tree(self, kwargs):
        with Pdf.new() as pdf:
            pdf.add_blank_page()
            tree = pdf.open_structure_tree()

            with pytest.raises(TypeError):
                tree.add(Name.P, **kwargs)

            assert not tree.exists
            assert Name.MarkInfo not in pdf.Root

    def test_foreign_nested_attribute_does_not_create_a_tree(self):
        first, second = self._two_pdfs()
        with first, second:
            foreign = second.make_indirect(Dictionary(O=Name.Layout))
            attributes = Array([foreign])
            tree = first.open_structure_tree()

            with pytest.raises(StructureTreeError, match="different PDF"):
                tree.add(Name.P, attributes=attributes)

            assert not tree.exists

    def test_cyclic_attributes_do_not_create_a_tree(self, blank):
        attributes = Dictionary(O=Name.Layout)
        attributes.Self = attributes
        tree = blank.open_structure_tree()
        try:
            with pytest.raises(StructureTreeError, match='object graph is cyclic'):
                tree.add(Name.P, attributes=attributes)

            assert not tree.exists
        finally:
            del attributes[Name.Self]

    def test_attributes_allow_a_shared_acyclic_subobject(self, blank):
        shared = Dictionary(Value=1)
        attributes = Dictionary(O=Name.Layout, First=shared, Second=shared)

        elem = blank.open_structure_tree().add(Name.P, attributes=attributes)

        assert elem.attributes.O == Name.Layout

    @pytest.mark.parametrize(
        'attributes',
        [
            Array([]),
            Array([1]),
            Array([Dictionary(O=Name.Layout), -1]),
            Array([Dictionary(O=Name.Layout), True]),
            Array([Dictionary(O=Name.Layout), 1, 2]),
        ],
    )
    def test_invalid_attribute_arrays_do_not_create_a_tree(self, attributes):
        with Pdf.new() as pdf:
            pdf.add_blank_page()
            tree = pdf.open_structure_tree()

            with pytest.raises(TypeError, match="valid attribute Array"):
                tree.add(Name.P, attributes=attributes)

            assert not tree.exists
            assert Name.MarkInfo not in pdf.Root

    @pytest.mark.parametrize(
        'attributes',
        [
            Dictionary(),
            Dictionary(O=String('Layout')),
            Array([Dictionary()]),
            Array([Dictionary(O=String('Layout'))]),
        ],
    )
    def test_attribute_dictionaries_require_name_owner_before_mutation(
        self, attributes
    ):
        with Pdf.new() as pdf:
            pdf.add_blank_page()
            tree = pdf.open_structure_tree()

            with pytest.raises(TypeError, match="name-valued /O"):
                tree.add(Name.P, attributes=attributes)

            assert not tree.exists
            assert Name.MarkInfo not in pdf.Root

    def test_add_content_rejects_foreign_page_and_stream_before_mutation(self):
        first, second = self._two_pdfs()
        with first, second:
            own_page = first.pages[0]
            foreign_page = second.pages[0]
            foreign_stream = second.make_stream(b'')
            own_stream = first.make_stream(b'')
            foreign_owner = second.make_indirect(Dictionary(Type=Name.Annot))
            elem = first.open_structure_tree().add(Name.P, page=own_page)

            with pytest.raises(StructureTreeError, match="different PDF"):
                elem.add_content(foreign_page, 0)
            with pytest.raises(StructureTreeError, match="different PDF"):
                elem.add_content(own_page, 0, stream=foreign_stream)
            with pytest.raises(StructureTreeError, match="different PDF"):
                elem.add_content(
                    own_page,
                    0,
                    stream=own_stream,
                    stream_owner=foreign_owner,
                )

            assert Name.K not in elem.obj
            assert Name.StructParents not in own_page.obj
            assert Name.StructParents not in foreign_page.obj
            assert Name.StructParents not in foreign_stream
            assert Name.StructParents not in own_stream

    def test_add_object_rejects_foreign_objects_before_mutation(self):
        first, second = self._two_pdfs()
        with first, second:
            page = first.pages[0]
            foreign_page = second.pages[0]
            foreign_annot = second.make_indirect(Dictionary(Type=Name.Annot))
            own_annot = first.make_indirect(Dictionary(Type=Name.Annot))
            elem = first.open_structure_tree().add(Name.Link, page=page)

            with pytest.raises(StructureTreeError, match="different PDF"):
                elem.add_object(foreign_annot, page)
            with pytest.raises(StructureTreeError, match="different PDF"):
                elem.add_object(own_annot, foreign_page)

            assert Name.K not in elem.obj
            assert Name.StructParent not in foreign_annot
            assert Name.StructParent not in own_annot

    def test_element_rejects_an_object_from_another_pdf(self):
        first, second = self._two_pdfs()
        with first, second:
            foreign_elem = second.open_structure_tree().add(Name.P)
            tree = first.open_structure_tree().create()
            with pytest.raises(StructureTreeError, match="different PDF"):
                tree.element(foreign_elem.obj)

    def test_forged_foreign_wrapper_cannot_mutate_the_other_pdf(self):
        first, second = self._two_pdfs()
        with first, second:
            foreign = second.open_structure_tree().add(Name.P)
            forged = StructElem(foreign.obj, first.open_structure_tree().create())

            with pytest.raises(StructureTreeError, match="different PDF"):
                forged.tag = Name.H1
            with pytest.raises(StructureTreeError, match="different PDF"):
                forged.remove()

            assert foreign.tag == Name.P
            assert second.open_structure_tree().kids == [foreign]


class TestParameterPreflight:
    def test_page_setter_rejects_a_non_page_without_mutation(self, blank):
        page = blank.pages[0]
        not_page = blank.make_indirect(Dictionary(Type=Name.Annot))
        elem = blank.open_structure_tree().add(Name.P, page=page)

        with pytest.raises(TypeError, match="page dictionary"):
            elem.page = not_page

        assert elem.obj.Pg.objgen == page.obj.objgen

    def test_page_setter_rejects_a_scalar_descendant_page_without_mutation(self, blank):
        first = blank.pages[0]
        second = blank.add_blank_page()
        parent = blank.open_structure_tree().add(Name.Document, page=first)
        child = parent.add_child(Name.P)
        child.obj.Pg = 42

        with pytest.raises(TypeError, match="PDF object"):
            parent.page = second

        assert parent.obj.Pg.objgen == first.obj.objgen
        assert child.obj.Pg == 42

    def test_page_setter_rejects_a_foreign_descendant_page_without_mutation(self):
        with Pdf.new() as first, Pdf.new() as second:
            first_page = first.add_blank_page()
            replacement = first.add_blank_page()
            foreign_page = second.add_blank_page()
            parent = first.open_structure_tree().add(Name.Document, page=first_page)
            child = Dictionary(
                Type=Name.StructElem,
                S=Name.P,
                P=parent.obj,
                Pg=foreign_page.obj,
            )
            parent.obj.K = Array([child])

            with pytest.raises(StructureTreeError, match="different PDF"):
                parent.page = replacement

            assert parent.obj.Pg.objgen == first_page.obj.objgen
            assert child.Pg.same_owner_as(second.Root)

    def test_namespace_setter_registers_uniquely_and_clears_safely(self, blank):
        elem = blank.open_structure_tree().add(Name.Custom)
        namespace = blank.make_indirect(Dictionary(NS=String('urn:example')))

        elem.namespace = namespace
        elem.namespace = namespace

        assert elem.obj.NS.objgen == namespace.objgen
        assert len(elem.tree.obj.Namespaces) == 1
        assert elem.tree.obj.Namespaces[0].objgen == namespace.objgen

        elem.namespace = None

        assert Name.NS not in elem.obj
        assert elem.tree.obj.Namespaces[0].objgen == namespace.objgen

    def test_namespace_setter_rejects_a_wrong_present_type(self, blank):
        elem = blank.open_structure_tree().add(Name.Custom)
        namespace = blank.make_indirect(
            Dictionary(Type=Name.Foo, NS=String('urn:example'))
        )

        with pytest.raises(StructureTreeError, match="/Type"):
            elem.namespace = namespace

        assert Name.NS not in elem.obj
        assert Name.Namespaces not in elem.tree.obj

    @pytest.mark.parametrize('namespace_name', [None, Name.Example, 42])
    def test_namespace_setter_requires_a_text_namespace_name(
        self, blank, namespace_name
    ):
        elem = blank.open_structure_tree().add(Name.Custom)
        data = Dictionary(Type=Name.Namespace)
        if namespace_name is not None:
            data.NS = namespace_name
        namespace = blank.make_indirect(data)

        with pytest.raises(StructureTreeError, match="string /NS"):
            elem.namespace = namespace

        assert Name.NS not in elem.obj
        assert Name.Namespaces not in elem.tree.obj

    @pytest.mark.parametrize(
        'namespace',
        [
            String('not a dictionary'),
            Dictionary(Type=Name.Namespace, NS=String('urn:direct')),
            Dictionary(Type=Name.Namespace),
        ],
    )
    def test_namespace_setter_rejects_invalid_values_without_mutation(
        self, blank, namespace
    ):
        elem = blank.open_structure_tree().add(Name.Custom)

        with pytest.raises((TypeError, StructureTreeError)):
            elem.namespace = namespace

        assert Name.NS not in elem.obj
        assert Name.Namespaces not in elem.tree.obj

    def test_namespace_setter_rejects_a_foreign_namespace_without_mutation(self):
        with Pdf.new() as first, Pdf.new() as second:
            first.add_blank_page()
            second.add_blank_page()
            elem = first.open_structure_tree().add(Name.Custom)
            namespace = second.make_indirect(
                Dictionary(Type=Name.Namespace, NS=String('urn:foreign'))
            )

            with pytest.raises(StructureTreeError, match="different PDF"):
                elem.namespace = namespace

            assert Name.NS not in elem.obj
            assert Name.Namespaces not in elem.tree.obj

    @pytest.mark.parametrize(
        'namespaces',
        [String('not an array'), Array([String('not a namespace')])],
    )
    def test_namespace_setter_rejects_malformed_registry_without_mutation(
        self, blank, namespaces
    ):
        elem = blank.open_structure_tree().add(Name.Custom)
        elem.tree.obj.Namespaces = namespaces
        namespace = blank.make_indirect(
            Dictionary(Type=Name.Namespace, NS=String('urn:example'))
        )

        with pytest.raises(StructureTreeError, match="/Namespaces"):
            elem.namespace = namespace

        assert Name.NS not in elem.obj
        assert elem.tree.obj.Namespaces == namespaces

    def test_namespace_setter_allows_duplicate_namespace_names(self, blank):
        elem = blank.open_structure_tree().add(Name.Custom)
        first = blank.make_indirect(
            Dictionary(Type=Name.Namespace, NS=String('urn:example'))
        )
        duplicate = blank.make_indirect(
            Dictionary(Type=Name.Namespace, NS=String('urn:example'))
        )
        elem.namespace = first

        elem.namespace = duplicate

        assert elem.obj.NS.objgen == duplicate.objgen
        assert len(elem.tree.obj.Namespaces) == 2

    def test_namespace_setter_tolerates_duplicate_registry_objects(self, blank):
        elem = blank.open_structure_tree().add(Name.Custom)
        registered = blank.make_indirect(Dictionary(NS=String('urn:registered')))
        target = blank.make_indirect(Dictionary(NS=String('urn:target')))
        elem.tree.obj.Namespaces = Array([registered, registered])

        elem.namespace = target

        assert elem.obj.NS.objgen == target.objgen
        assert [item.objgen for item in elem.tree.obj.Namespaces] == [
            registered.objgen,
            registered.objgen,
            target.objgen,
        ]

    def test_attributes_accept_streams(self, blank):
        elem = blank.open_structure_tree().add(Name.P)
        stream = blank.make_stream(b'', O=Name.Layout)

        elem.attributes = stream

        assert elem.attributes.objgen == stream.objgen
        assert elem.tree.validate(check_content=False) == []

    @pytest.mark.parametrize('owner', [None, String('Layout')])
    def test_attributes_reject_streams_without_a_name_owner(self, blank, owner):
        elem = blank.open_structure_tree().add(Name.P)
        stream = blank.make_stream(b'')
        if owner is not None:
            stream.O = owner

        with pytest.raises(TypeError, match="name-valued /O"):
            elem.attributes = stream

        assert Name.A not in elem.obj

    def test_valid_attribute_array_is_accepted(self, blank):
        attributes = Array([Dictionary(O=Name.Layout), 1, Dictionary(O=Name.List)])
        elem = blank.open_structure_tree().add(Name.P, attributes=attributes)

        assert elem.attributes == attributes

    def test_page_setter_rejects_retargeting_implicit_content(self, blank):
        first = blank.pages[0]
        second = blank.add_blank_page()
        elem = blank.open_structure_tree().add(Name.P, page=first)
        elem.add_content(first, 0)

        with pytest.raises(StructureTreeError, match="effective page"):
            elem.page = second

        assert elem.obj.Pg.objgen == first.obj.objgen
        assert elem.obj.K == Array([0])

    def test_page_setter_rejects_retargeting_inherited_content(self, blank):
        first = blank.pages[0]
        second = blank.add_blank_page()
        parent = blank.open_structure_tree().add(Name.Document, page=first)
        child = parent.add_child(Name.P)
        child.add_content(first, 0)

        with pytest.raises(StructureTreeError, match="effective page"):
            parent.page = second

        assert parent.obj.Pg.objgen == first.obj.objgen
        assert Name.Pg not in child.obj

    def test_page_setter_allows_unchanged_or_explicit_reference_pages(self, blank):
        first = blank.pages[0]
        second = blank.add_blank_page()
        parent = blank.open_structure_tree().add(Name.Document, page=first)
        child = parent.add_child(Name.P, page=second)
        child.add_content(second, 0)

        parent.page = second
        child.page = second

        assert parent.obj.Pg.objgen == second.obj.objgen
        assert child.obj.Pg.objgen == second.obj.objgen

    def test_page_setter_allows_explicit_kid_reference_page(self, blank):
        first = blank.pages[0]
        second = blank.add_blank_page()
        elem = blank.open_structure_tree().add(Name.P, page=first)
        elem.add_content(second, 0)

        elem.page = second

        assert elem.obj.Pg.objgen == second.obj.objgen
        assert elem.obj.K[0].Pg.objgen == second.obj.objgen

    def test_owned_mutations_do_not_walk_the_full_tree(self, blank, monkeypatch):
        tree = blank.open_structure_tree()
        parent = tree.add(Name.Document)
        children = [parent.add_child(Name.P) for _ in range(100)]

        def fail_walk():
            raise AssertionError("full-tree walk")

        monkeypatch.setattr(tree, "_walk_all", fail_walk)
        children[-1].tag = Name.Span
        children[-1].add_child(Name.Span)

    def test_add_rejects_a_non_page_before_creating_the_tree(self, blank):
        not_page = blank.make_indirect(Dictionary(Type=Name.Annot))
        tree = blank.open_structure_tree()

        with pytest.raises(TypeError, match="page dictionary"):
            tree.add(Name.P, page=not_page)

        assert not tree.exists

    def test_add_rejects_a_page_dictionary_outside_the_page_tree(self, blank):
        detached_page = blank.make_indirect(Dictionary(Type=Name.Page))
        tree = blank.open_structure_tree()

        with pytest.raises(StructureTreeError, match="not in.*page tree"):
            tree.add(Name.P, page=detached_page)

        assert not tree.exists

    def test_add_child_rejects_a_non_page_before_changing_k(self, blank):
        not_page = blank.make_indirect(Dictionary(Type=Name.Annot))
        parent = blank.open_structure_tree().add(Name.Document)

        with pytest.raises(TypeError, match="page dictionary"):
            parent.add_child(Name.P, page=not_page)

        assert Name.K not in parent.obj

    def test_add_content_rejects_a_non_page_before_mutation(self, blank):
        page = blank.pages[0]
        not_page = blank.make_indirect(Dictionary(Type=Name.Annot))
        elem = blank.open_structure_tree().add(Name.P, page=page)

        with pytest.raises(TypeError, match="page dictionary"):
            elem.add_content(not_page, 0)

        assert Name.K not in elem.obj
        assert Name.StructParents not in not_page
        assert Name.StructParents not in page.obj

    def test_add_content_rejects_a_non_stream_before_mutation(self, blank):
        page = blank.pages[0]
        not_stream = blank.make_indirect(Dictionary(Type=Name.Annot))
        elem = blank.open_structure_tree().add(Name.P, page=page)

        with pytest.raises(TypeError, match="pikepdf.Stream"):
            elem.add_content(page, 0, stream=not_stream)

        assert Name.K not in elem.obj
        assert Name.StructParents not in not_stream
        assert Name.StructParents not in page.obj

    def test_content_container_cannot_also_have_struct_parent(self, blank):
        page = blank.pages[0]
        page.obj.StructParent = 8
        elem = blank.open_structure_tree().add(Name.P, page=page)

        with pytest.raises(StructureTreeError, match="also have /StructParent"):
            elem.add_content(page, 0)

        assert Name.K not in elem.obj
        assert page.obj.StructParent == 8
        assert Name.StructParents not in page.obj

    def test_add_object_rejects_a_non_page_before_mutation(self, blank):
        page = blank.pages[0]
        not_page = blank.make_indirect(Dictionary(Type=Name.Annot))
        referent = blank.make_indirect(Dictionary(Type=Name.Annot))
        elem = blank.open_structure_tree().add(Name.Link, page=page)

        with pytest.raises(TypeError, match="page dictionary"):
            elem.add_object(referent, not_page)

        assert Name.K not in elem.obj
        assert Name.StructParent not in referent

    def test_add_object_rejects_a_scalar_referent_before_mutation(self, blank):
        page = blank.pages[0]
        referent = blank.make_indirect(String('not an object container'))
        elem = blank.open_structure_tree().add(Name.Link, page=page)

        with pytest.raises(TypeError, match="Dictionary or Stream"):
            elem.add_object(referent, page)

        assert Name.K not in elem.obj

    def test_referent_cannot_also_have_struct_parents(self, blank):
        page = blank.pages[0]
        referent = blank.make_indirect(Dictionary(Type=Name.Annot, StructParents=8))
        elem = blank.open_structure_tree().add(Name.Link, page=page)

        with pytest.raises(StructureTreeError, match="also have /StructParents"):
            elem.add_object(referent, page)

        assert Name.K not in elem.obj
        assert referent.StructParents == 8
        assert Name.StructParent not in referent

    def test_removed_element_cannot_register_content(self, blank):
        page = blank.pages[0]
        tree = blank.open_structure_tree()
        elem = tree.add(Name.P, page=page)
        elem.remove()

        with pytest.raises(StructureTreeError, match="not attached"):
            elem.add_content(page, 0)

        assert tree.kids == []
        assert Name.K not in elem.obj
        assert Name.StructParents not in page.obj

    def test_same_pdf_forged_element_cannot_mutate(self, blank):
        page = blank.pages[0]
        tree = blank.open_structure_tree().create()
        obj = blank.make_indirect(
            Dictionary(Type=Name.StructElem, S=Name.P, P=tree.obj)
        )
        forged = StructElem(obj, tree)

        with pytest.raises(StructureTreeError, match="not attached"):
            forged.tag = Name.H1
        with pytest.raises(StructureTreeError, match="not attached"):
            forged.add_content(page, 0)

        assert forged.obj.S == Name.P
        assert Name.K not in forged.obj
        assert Name.StructParents not in page.obj

    def test_content_marker_rejects_a_removed_target_without_mutation(self, blank):
        page = blank.pages[0]
        set_contents(blank, page, b"BT (a) Tj ET\n")
        before = page.obj.Contents.read_bytes()
        tree = blank.open_structure_tree()
        elem = tree.add(Name.P, page=page)
        elem.remove()
        marker = ContentMarker(page)

        with pytest.raises(StructureTreeError, match="not attached"):
            marker.mark(Name.P, 0, 3, element=elem)

        assert marker.apply() == []
        assert page.obj.Contents.read_bytes() == before
        assert Name.StructParents not in page.obj


class TestRemoval:
    @staticmethod
    def _element_with_auxiliary_state(blank):
        page = blank.pages[0]
        annot = blank.make_indirect(Dictionary(Type=Name.Annot))
        page.obj.Annots = Array([annot])
        tree = blank.open_structure_tree()
        elem = tree.add(Name.Link, page=page)
        elem.element_id = 'target'
        elem.add_content(page, 0)
        elem.add_object(annot, page)
        return page, annot, tree, elem

    def test_remove_detaches_and_clears_parent_tree(self, blank):
        page = blank.pages[0]
        tree = blank.open_structure_tree()
        doc = tree.add(Name.Document, page=page)
        keep = doc.add_child(Name.P, page=page)
        drop = doc.add_child(Name.P, page=page)
        child_of_drop = drop.add_child(Name.Span, page=page)
        keep.add_content(page, 0)
        drop.add_content(page, 1)
        child_of_drop.add_content(page, 2)

        drop.remove()

        assert doc.children == [keep]
        entry = tree.parent_tree.entry_for_page(page)
        assert entry[0].objgen == keep.obj.objgen
        assert entry[1] is None
        assert entry[2] is None

    def test_remove_only_child(self, blank):
        tree = blank.open_structure_tree()
        doc = tree.add(Name.Document)
        doc.add_child(Name.P).remove()
        assert Name.K not in doc.obj

    def test_remove_scalar_k(self, blank):
        tree = blank.open_structure_tree()
        doc = tree.add(Name.Document)
        child = doc.add_child(Name.P)
        doc.obj.K = child.obj
        child.remove()
        assert Name.K not in doc.obj

    def test_remove_clears_object_entry(self, blank):
        page = blank.pages[0]
        annot = blank.make_indirect(Dictionary(Type=Name.Annot))
        page.obj.Annots = Array([annot])
        tree = blank.open_structure_tree()
        elem = tree.add(Name.Link, page=page)
        elem.add_object(annot, page)
        assert 0 in tree.parent_tree
        elem.remove()
        assert 0 not in tree.parent_tree

    def test_malformed_parent_tree_does_not_partially_remove(self, blank):
        page, annot, tree, elem = self._element_with_auxiliary_state(blank)
        original_parent_tree = tree.parent_tree.number_tree
        page_key = page.obj.StructParents
        object_key = annot.StructParent
        id_tree = NameTree(tree.obj.IDTree)
        original_k = Array(elem.obj.K)
        tree.obj.ParentTree = String('bad')

        with pytest.raises(StructureTreeError, match="/ParentTree"):
            elem.remove()

        assert tree.kids == [elem]
        assert elem.obj.K == original_k
        assert elem.obj.ID == String('target')
        assert id_tree['target'].objgen == elem.obj.objgen
        assert page.obj.StructParents == page_key
        assert annot.StructParent == object_key
        assert original_parent_tree[page_key][0].objgen == elem.obj.objgen
        assert original_parent_tree[object_key].objgen == elem.obj.objgen
        assert tree.obj.ParentTree == String('bad')

    def test_malformed_id_tree_does_not_partially_remove(self, blank):
        page, annot, tree, elem = self._element_with_auxiliary_state(blank)
        parent_tree = tree.parent_tree.number_tree
        page_key = page.obj.StructParents
        object_key = annot.StructParent
        original_id_tree = NameTree(tree.obj.IDTree)
        original_k = Array(elem.obj.K)
        tree.obj.IDTree = String('bad')

        with pytest.raises(StructureTreeError, match="/IDTree"):
            elem.remove()

        assert tree.kids == [elem]
        assert elem.obj.K == original_k
        assert elem.obj.ID == String('target')
        assert original_id_tree['target'].objgen == elem.obj.objgen
        assert page.obj.StructParents == page_key
        assert annot.StructParent == object_key
        assert parent_tree[page_key][0].objgen == elem.obj.objgen
        assert parent_tree[object_key].objgen == elem.obj.objgen
        assert tree.obj.IDTree == String('bad')

    @pytest.mark.parametrize('reference_type', ['OBJR', 'MCR'])
    def test_foreign_references_reject_subtree_removal_atomically(self, reference_type):
        with Pdf.new() as first, Pdf.new() as second:
            page = first.add_blank_page()
            second.add_blank_page()
            tree = first.open_structure_tree()
            elem = tree.add(Name.Link, page=page)
            elem.element_id = 'target'
            if reference_type == 'OBJR':
                foreign = second.make_indirect(
                    Dictionary(Type=Name.Annot, StructParent=7)
                )
                elem.obj.K = Array(
                    [Dictionary(Type=Name.OBJR, Obj=foreign, Pg=page.obj)]
                )
                foreign_key = Name.StructParent
            else:
                foreign = second.make_stream(b'', StructParents=7)
                elem.obj.K = Array(
                    [
                        Dictionary(
                            Type=Name.MCR,
                            MCID=0,
                            Pg=page.obj,
                            Stm=foreign,
                        )
                    ]
                )
                foreign_key = Name.StructParents
            original_k = Array(elem.obj.K)

            with pytest.raises(StructureTreeError, match="another PDF"):
                elem.remove()

            assert tree.kids == [elem]
            assert elem.obj.K == original_k
            assert elem.obj.ID == String('target')
            assert tree.find_by_id('target') == elem
            assert foreign[foreign_key] == 7


class TestParentTree:
    def test_allocate_key(self, blank):
        tree = blank.open_structure_tree().create()
        pt = tree.parent_tree
        assert pt.allocate_key() == 0
        assert pt.allocate_key() == 1
        assert pt.next_key == 2

    def test_key_for_page_rejects_an_annotation_without_mutation(self, blank):
        annot = blank.make_indirect(Dictionary(Type=Name.Annot))
        tree = blank.open_structure_tree().create()

        with pytest.raises(TypeError, match="PDF page or pikepdf.Stream"):
            tree.parent_tree.key_for_page(annot, create=True)

        assert Name.StructParents not in annot
        assert tree.parent_tree.keys() == []

    def test_key_for_page_rejects_a_struct_parent_container(self, blank):
        page = blank.pages[0]
        page.obj.StructParent = 3
        tree = blank.open_structure_tree().create()

        with pytest.raises(StructureTreeError, match='cannot also have'):
            tree.parent_tree.key_for_page(page, create=True)

        assert Name.StructParents not in page.obj
        assert tree.parent_tree.keys() == []

    def test_register_content_rejects_an_annotation_without_mutation(self, blank):
        annot = blank.make_indirect(Dictionary(Type=Name.Annot))
        tree = blank.open_structure_tree()
        elem = tree.add(Name.P)

        with pytest.raises(TypeError, match="PDF page or pikepdf.Stream"):
            tree.parent_tree.register_content(annot, 0, elem)

        assert Name.StructParents not in annot
        assert tree.parent_tree.keys() == []

    def test_allocate_key_skips_used(self, blank):
        tree = blank.open_structure_tree().create()
        pt = tree.parent_tree
        pt.number_tree[0] = blank.make_indirect(Array([]))
        assert pt.allocate_key() == 1

    def test_reserve_key_advances_once_past_a_collision(self, blank):
        page = blank.pages[0]
        parent_tree = blank.open_structure_tree().create().parent_tree
        state = parent_tree._content_check_state()
        state.next_available_key = 0
        state.parent_tree_keys.add(0)

        assert parent_tree._reserve_key(page.obj, state) == 1

    def test_allocate_key_repairs_next_key_below_the_highest_used_key(self, blank):
        tree = blank.open_structure_tree().create()
        pt = tree.parent_tree
        pt.number_tree[100] = blank.make_indirect(Array([]))
        tree.obj.ParentTreeNextKey = 1

        assert pt.allocate_key() == 101
        assert pt.next_key == 102

    def test_allocate_key_skips_dangling_container_keys(self, blank):
        page = blank.pages[0]
        page.obj.StructParents = 0
        annot = blank.make_indirect(Dictionary(Type=Name.Annot, StructParent=1))
        page.obj.Annots = Array([annot])
        pt = blank.open_structure_tree().create().parent_tree

        assert pt.allocate_key() == 2

    def test_setitem_advances_next_key(self, blank):
        tree = blank.open_structure_tree().create()
        pt = tree.parent_tree
        pt[7] = blank.make_indirect(Array([]))
        assert pt.next_key == 8
        assert 7 in pt
        assert pt.keys() == [7]
        assert 'entries' in repr(pt)

    @pytest.mark.parametrize(
        ('value', 'error'),
        [(True, TypeError), (1.5, TypeError)],
    )
    def test_next_key_setter_rejects_invalid_values(self, blank, value, error):
        pt = blank.open_structure_tree().create().parent_tree

        with pytest.raises(error):
            pt.next_key = value

        assert pt.next_key == 0

    def test_next_key_setter_must_stay_above_used_keys(self, blank):
        tree = blank.open_structure_tree().create()
        pt = tree.parent_tree
        pt[5] = blank.make_indirect(Array([]))

        with pytest.raises(ValueError, match='greater than every used'):
            pt.next_key = 5

        assert pt.next_key == 6

    def test_next_key_setter_counts_structural_parent_key_users(self, blank):
        page = blank.pages[0]
        annotation = blank.make_indirect(Dictionary(Type=Name.Annot, StructParent=7))
        page.obj.Annots = Array([annotation])
        pt = blank.open_structure_tree().create().parent_tree

        with pytest.raises(ValueError, match='greater than every used'):
            pt.next_key = 7

        pt.next_key = 8
        assert pt.next_key == 8

    def test_next_key_setter_allows_any_integer_when_no_keys_are_used(self, blank):
        pt = blank.open_structure_tree().create().parent_tree

        pt.next_key = -2

        assert pt.next_key == -2

    @pytest.mark.parametrize('key', [True, 1.5])
    def test_getitem_rejects_non_integer_keys(self, blank, key):
        pt = blank.open_structure_tree().create().parent_tree

        with pytest.raises(TypeError):
            _ = pt[key]

        assert key not in pt

    def test_getitem_uses_key_error_for_a_missing_key(self, blank):
        pt = blank.open_structure_tree().create().parent_tree

        with pytest.raises(KeyError):
            _ = pt[99]

    @pytest.mark.parametrize(
        ('key', 'error'),
        [(True, TypeError), (1.5, TypeError)],
    )
    def test_setitem_rejects_invalid_keys_without_mutation(self, blank, key, error):
        pt = blank.open_structure_tree().create().parent_tree

        with pytest.raises(error):
            pt[key] = blank.make_indirect(Array([]))

        assert pt.keys() == []
        assert pt.next_key == 0

    @pytest.mark.parametrize('value', [String('bad'), True, 1.5])
    def test_malformed_next_key_is_rejected_before_content_mutation(self, blank, value):
        page = blank.pages[0]
        tree = blank.open_structure_tree().create()
        tree.obj.ParentTreeNextKey = value
        elem = tree.add(Name.P, page=page)

        with pytest.raises(StructureTreeError, match="must be an integer"):
            elem.add_content(page, 0)

        assert Name.K not in elem.obj
        assert Name.StructParents not in page.obj
        assert tree.parent_tree.keys() == []
        assert tree.obj.ParentTreeNextKey == value

    def test_negative_next_key_is_valid_and_allocator_stays_nonnegative(self, blank):
        tree = blank.open_structure_tree().create()
        tree.obj.ParentTreeNextKey = -2

        assert tree.parent_tree.next_key == -2
        assert tree.parent_tree.allocate_key() == 0
        assert tree.parent_tree.next_key == 1

    def test_negative_parent_tree_key_is_supported(self, blank):
        tree = blank.open_structure_tree().create()
        entry = blank.make_indirect(Array([]))

        tree.parent_tree[-1] = entry

        assert tree.parent_tree[-1] == entry
        assert tree.parent_tree.keys() == [-1]
        assert tree.parent_tree.next_key == 0

    def test_content_registration_accepts_existing_negative_key(self, blank):
        page = blank.pages[0]
        tree = blank.open_structure_tree()
        elem = tree.add(Name.P, page=page)
        page.obj.StructParents = -1
        tree.parent_tree[-1] = blank.make_indirect(Array([]))

        elem.add_content(page, 0)

        assert tree.parent_tree.entry_for_page(page)[0] == elem.obj

    def test_object_registration_accepts_existing_negative_key(self, blank):
        page = blank.pages[0]
        annotation = blank.make_indirect(Dictionary(Type=Name.Annot, StructParent=-1))
        page.obj.Annots = Array([annotation])
        tree = blank.open_structure_tree()
        elem = tree.add(Name.Link, page=page)

        elem.add_object(annotation, page)

        assert annotation.StructParent == -1
        assert tree.parent_tree[-1] == elem.obj

    def test_key_for_page_without_create(self, blank):
        tree = blank.open_structure_tree().create()
        assert tree.parent_tree.key_for_page(blank.pages[0]) is None
        assert tree.parent_tree.entry_for_page(blank.pages[0]) is None

    def test_entry_for_page_rejects_a_missing_or_non_array_entry(self, blank):
        page = blank.pages[0]
        tree = blank.open_structure_tree().create()
        page.obj.StructParents = 0

        with pytest.raises(StructureTreeError, match='no corresponding'):
            tree.parent_tree.entry_for_page(page)

        tree.parent_tree[0] = tree.add(Name.P).obj
        with pytest.raises(StructureTreeError, match='must be an array'):
            tree.parent_tree.entry_for_page(page)

    def test_parent_tree_created_on_demand(self, blank):
        tree = blank.open_structure_tree().create()
        del tree.obj[Name.ParentTree]
        assert isinstance(tree.parent_tree.obj, Dictionary)
        assert Name.ParentTree in tree.obj

    def test_parent_tree_reads_do_not_create_a_missing_tree(self, blank):
        tree = blank.open_structure_tree().create()
        del tree.obj[Name.ParentTree]
        parent_tree = tree.parent_tree

        assert parent_tree.keys() == []
        assert 0 not in parent_tree
        assert parent_tree.entry_for_page(blank.pages[0]) is None
        assert '0 entries' in repr(parent_tree)
        assert Name.ParentTree not in tree.obj

    def test_content_marker_rolls_back_new_parent_tree(self, blank, monkeypatch):
        page = blank.pages[0]
        set_contents(blank, page, b"BT (a) Tj ET BT (b) Tj ET\n")
        tree = blank.open_structure_tree().create()
        del tree.obj[Name.ParentTree]
        first = tree.add(Name.P, page=page)
        second = tree.add(Name.P, page=page)
        marker = ContentMarker(page)
        marker.mark(Name.P, 0, 3, element=first)
        marker.mark(Name.P, 3, 6, element=second)
        monkeypatch.setattr(
            StructElem,
            '_add_content_prechecked',
            structure_registration_failure(second),
        )

        with pytest.raises(RuntimeError, match="injected failure"):
            marker.apply()

        assert Name.ParentTree not in tree.obj
        assert tree.parent_tree.next_key == 0
        assert Name.StructParents not in page.obj
        assert Name.K not in first.obj
        assert Name.K not in second.obj

    def test_malformed_parent_tree_is_rejected_before_k_changes(self, blank):
        page = blank.pages[0]
        tree = blank.open_structure_tree().create()
        tree.obj.ParentTree = Array([])
        elem = tree.add(Name.P, page=page)

        with pytest.raises(StructureTreeError, match="must be a dictionary"):
            elem.add_content(page, 0)

        assert Name.K not in elem.obj
        assert Name.StructParents not in page.obj

    def test_entry_must_be_array(self, blank):
        page = blank.pages[0]
        tree = blank.open_structure_tree().create()
        page.obj.StructParents = 0
        tree.parent_tree[0] = blank.make_indirect(Dictionary())
        elem = tree.add(Name.P, page=page)
        with pytest.raises(StructureTreeError, match="not an array"):
            elem.add_content(page, 0)
        assert Name.K not in elem.obj

    def test_dangling_struct_parents_is_rejected_before_k_changes(self, blank):
        page = blank.pages[0]
        page.obj.StructParents = 7
        tree = blank.open_structure_tree().create()
        elem = tree.add(Name.P, page=page)

        with pytest.raises(StructureTreeError, match="no corresponding"):
            elem.add_content(page, 0)

        assert Name.K not in elem.obj
        assert page.obj.StructParents == 7

    def test_non_element_content_entry_is_not_overwritten(self, blank):
        page = blank.pages[0]
        page.obj.StructParents = 0
        tree = blank.open_structure_tree().create()
        entry = blank.make_indirect(Array([String('invalid')]))
        tree.parent_tree[0] = entry
        elem = tree.add(Name.P, page=page)

        with pytest.raises(StructureTreeError, match="not a structure element"):
            elem.add_content(page, 0)

        assert Name.K not in elem.obj
        assert entry[0] == String('invalid')

    @pytest.mark.parametrize('value', [True, String('zero')])
    def test_invalid_struct_parents_is_not_overwritten(self, blank, value):
        page = blank.pages[0]
        page.obj.StructParents = value
        tree = blank.open_structure_tree().create()
        elem = tree.add(Name.P, page=page)

        with pytest.raises(StructureTreeError, match="must be an integer"):
            elem.add_content(page, 0)

        assert Name.K not in elem.obj
        assert page.obj.StructParents == value

    def test_register_content_requires_an_existing_k_claim(self, blank):
        page = blank.pages[0]
        tree = blank.open_structure_tree()
        elem = tree.add(Name.P, page=page)

        with pytest.raises(StructureTreeError, match='exactly one reachable'):
            tree.parent_tree.register_content(page, 2, elem)

        assert Name.StructParents not in page.obj

    def test_register_object_requires_an_existing_objr_claim(self, blank):
        annot = blank.make_indirect(Dictionary(Type=Name.Annot))
        tree = blank.open_structure_tree()
        elem = tree.add(Name.Link)

        with pytest.raises(StructureTreeError, match='a reachable matching'):
            tree.parent_tree.register_object(annot, elem)

        assert Name.StructParent not in annot

    def test_object_key_cannot_replace_a_page_entry(self, blank):
        page = blank.pages[0]
        page.obj.StructParents = 0
        annot = blank.make_indirect(
            Dictionary(Type=Name.Annot, Subtype=Name.Link, StructParent=0)
        )
        page.obj.Annots = Array([annot])
        tree = blank.open_structure_tree().create()
        page_entry = blank.make_indirect(Array([]))
        tree.parent_tree[0] = page_entry
        elem = tree.add(Name.Link, page=page)

        with pytest.raises(StructureTreeError, match="not a structure element"):
            elem.add_object(annot, page)

        assert Name.K not in elem.obj
        assert tree.parent_tree[0].objgen == page_entry.objgen

    def test_two_pages_cannot_share_a_struct_parents_key(self, blank):
        first = blank.pages[0]
        second = blank.add_blank_page()
        first.obj.StructParents = 0
        second.obj.StructParents = 0
        tree = blank.open_structure_tree().create()
        entry = blank.make_indirect(Array([]))
        tree.parent_tree[0] = entry
        elem = tree.add(Name.P, page=second)

        with pytest.raises(StructureTreeError, match="already used"):
            elem.add_content(second, 0)

        assert Name.K not in elem.obj
        assert len(entry) == 0

    def test_page_and_form_cannot_share_a_struct_parents_key(self, blank):
        page = blank.pages[0]
        page.obj.StructParents = 0
        form = blank.make_stream(
            b'', Type=Name.XObject, Subtype=Name.Form, StructParents=0
        )
        page.obj.Resources = Dictionary(XObject=Dictionary(Fm0=form))
        tree = blank.open_structure_tree().create()
        entry = blank.make_indirect(Array([]))
        tree.parent_tree[0] = entry
        elem = tree.add(Name.P, page=page)

        with pytest.raises(StructureTreeError, match="already used"):
            elem.add_content(page, 0, stream=form)

        assert Name.K not in elem.obj
        assert len(entry) == 0

    def test_two_objects_cannot_share_a_key_for_the_same_element(self, blank):
        page = blank.pages[0]
        first = blank.make_indirect(Dictionary(Type=Name.Annot, StructParent=5))
        page.obj.Annots = Array([first])
        tree = blank.open_structure_tree()
        elem = tree.add(Name.Link, page=page)
        elem.add_object(first, page)
        second = blank.make_indirect(Dictionary(Type=Name.Annot, StructParent=5))
        page.obj.Annots.append(second)

        with pytest.raises(StructureTreeError, match="already claimed"):
            elem.add_object(second, page)

        assert len(elem.obj.K) == 1
        assert second.StructParent == 5

    def test_dangling_object_key_cannot_collide_with_a_page_key(self, blank):
        page = blank.pages[0]
        page.obj.StructParents = 5
        annot = blank.make_indirect(Dictionary(Type=Name.Annot, StructParent=5))
        page.obj.Annots = Array([annot])
        tree = blank.open_structure_tree()
        elem = tree.add(Name.Link, page=page)

        with pytest.raises(StructureTreeError, match="already used"):
            elem.add_object(annot, page)

        assert Name.K not in elem.obj
        assert tree.parent_tree.keys() == []
        assert page.obj.StructParents == 5
        assert annot.StructParent == 5

    def test_two_dangling_object_keys_cannot_be_conflated(self, blank):
        page = blank.pages[0]
        first = blank.make_indirect(Dictionary(Type=Name.Annot, StructParent=5))
        second = blank.make_indirect(Dictionary(Type=Name.Annot, StructParent=5))
        page.obj.Annots = Array([first, second])
        tree = blank.open_structure_tree()
        elem = tree.add(Name.Link, page=page)

        with pytest.raises(StructureTreeError, match="already used"):
            elem.add_object(first, page)

        assert Name.K not in elem.obj
        assert tree.parent_tree.keys() == []

    @pytest.mark.parametrize('value', [True, String('zero')])
    def test_invalid_struct_parent_is_not_overwritten(self, blank, value):
        page = blank.pages[0]
        annot = blank.make_indirect(Dictionary(Type=Name.Annot, StructParent=value))
        page.obj.Annots = Array([annot])
        tree = blank.open_structure_tree()
        elem = tree.add(Name.Link, page=page)

        with pytest.raises(StructureTreeError, match="must be an integer"):
            elem.add_object(annot, page)

        assert Name.K not in elem.obj
        assert annot.StructParent == value


class TestRoundTrip:
    def test_save_and_reopen(self, text_pdf, outpdf):
        page = text_pdf.pages[0]
        tree = text_pdf.open_structure_tree()
        doc = tree.add(Name.Document, lang='en-US')
        mark_text_runs(
            page,
            {(Name.F2, Decimal(24)): Name.H1, (Name.F1, Decimal(12)): Name.P},
            parent=doc,
        )
        tree.add_role(Name.MyPara, Name.P)
        text_pdf.save(outpdf)

        with Pdf.open(outpdf) as reopened:
            reloaded = reopened.open_structure_tree()
            assert reloaded.marked
            assert [str(e.tag) for e in reloaded.walk()] == ['/Document', '/H1', '/P']
            assert reloaded.kids[0].lang == 'en-US'
            assert reloaded.role_map[Name.MyPara] == Name.P
            assert reloaded.validate() == []
            assert reloaded.parent_tree.keys() == [0]

    def test_qpdf_can_strip_it(self, text_pdf, outpdf, outdir):
        page = text_pdf.pages[0]
        tree = text_pdf.open_structure_tree()
        mark_text_runs(
            page, {(Name.F1, Decimal(12)): Name.P}, parent=tree.add(Name.Document)
        )
        text_pdf.save(outpdf)
        stripped = outdir / 'stripped.pdf'
        pikepdf.JobBuilder().input(outpdf).output(stripped).remove_structure().run()
        with Pdf.open(stripped) as after:
            assert not after.open_structure_tree().exists


class TestOtherAccessors:
    def test_id_tree(self, blank):
        tree = blank.open_structure_tree()
        elem = tree.add(Name.P)
        assert tree.id_tree is None
        assert tree.find_by_id('x') is None
        elem.element_id = 'para1'
        assert tree.find_by_id('para1') == elem
        assert tree.find_by_id('missing') is None

    def test_find_by_id_rejects_a_wrong_target(self, blank):
        tree = blank.open_structure_tree()
        first = tree.add(Name.P)
        second = tree.add(Name.P)
        first.element_id = 'first'
        second.element_id = 'second'
        NameTree(tree.obj.IDTree)['first'] = second.obj

        with pytest.raises(StructureTreeError, match='reachable element'):
            tree.find_by_id('first')

    def test_find_by_id_rejects_a_detached_target(self, blank):
        tree = blank.open_structure_tree().create()
        detached = blank.make_indirect(
            Dictionary(
                Type=Name.StructElem,
                S=Name.P,
                P=tree.obj,
                ID=String('detached'),
            )
        )
        tree.obj.IDTree = NameTree.new(blank).obj
        NameTree(tree.obj.IDTree)['detached'] = detached

        with pytest.raises(StructureTreeError, match='reachable element'):
            tree.find_by_id('detached')

    def test_find_by_id_rejects_a_target_with_no_matching_id(self, blank):
        tree = blank.open_structure_tree()
        elem = tree.add(Name.P)
        elem.element_id = 'target'
        del elem.obj[Name.ID]

        with pytest.raises(StructureTreeError, match='matching /ID'):
            tree.find_by_id('target')

    @pytest.mark.parametrize('value', [String('bad'), Dictionary(Names=String('bad'))])
    def test_id_tree_accessor_rejects_malformed_values(self, blank, value):
        tree = blank.open_structure_tree().create()
        tree.obj.IDTree = value

        with pytest.raises(StructureTreeError, match='/IDTree'):
            _ = tree.id_tree

    def test_element_id_rename_and_clear(self, blank):
        tree = blank.open_structure_tree()
        elem = tree.add(Name.P)
        elem.element_id = 'old'

        elem.element_id = 'new'

        assert tree.find_by_id('old') is None
        assert tree.find_by_id('new') == elem
        assert elem.element_id == 'new'

        elem.element_id = None

        assert elem.element_id is None
        assert tree.find_by_id('new') is None
        assert tree.id_tree is None

    def test_element_id_must_be_unique(self, blank):
        tree = blank.open_structure_tree()
        first = tree.add(Name.P)
        second = tree.add(Name.P)
        first.element_id = 'shared'

        with pytest.raises(StructureTreeError, match="not unique"):
            second.element_id = 'shared'

        assert first.element_id == 'shared'
        assert second.element_id is None
        assert tree.find_by_id('shared') == first

    def test_remove_clears_ids_for_the_full_subtree(self, blank):
        tree = blank.open_structure_tree()
        retained = tree.add(Name.P)
        retained.element_id = 'retained'
        parent = tree.add(Name.Sect)
        child = parent.add_child(Name.P)
        parent.element_id = 'parent'
        child.element_id = 'child'

        parent.remove()

        assert tree.find_by_id('retained') == retained
        assert tree.find_by_id('parent') is None
        assert tree.find_by_id('child') is None

    def test_element_id_round_trips(self, blank, outpdf):
        tree = blank.open_structure_tree()
        tree.add(Name.P).element_id = 'paragraph'
        blank.save(outpdf)

        with Pdf.open(outpdf) as reopened:
            elem = reopened.open_structure_tree().find_by_id('paragraph')
            assert elem is not None
            assert elem.element_id == 'paragraph'

    def test_element_id_preserves_exact_bytes_and_distinguishes_text(self, blank):
        tree = blank.open_structure_tree()
        encoded = tree.add(Name.P)
        plain = tree.add(Name.P)
        encoded_id = b'\xfe\xff\x00A'
        encoded.element_id = encoded_id
        plain.element_id = 'A'

        assert encoded.element_id == encoded_id
        assert plain.element_id == 'A'
        assert tree.find_by_id(encoded_id) == encoded
        assert tree.find_by_id('A') == plain
        assert [bytes(tree.obj.IDTree.Names[index]) for index in (0, 2)] == [
            b'A',
            encoded_id,
        ]
        assert tree.validate(check_content=False) == []

        encoded.element_id = None

        assert tree.find_by_id(encoded_id) is None
        assert tree.find_by_id('A') == plain
        assert bytes(tree.obj.IDTree.Names[0]) == b'A'
        assert tree.validate(check_content=False) == []

    def test_element_id_getter_assignment_is_a_lossless_noop(self, blank):
        tree = blank.open_structure_tree()
        elem = tree.add(Name.P)
        elem.element_id = b'\xfe\xff\x00A'
        original_id_tree = tree.obj.IDTree
        value = elem.element_id

        elem.element_id = value

        assert value == b'\xfe\xff\x00A'
        assert bytes(elem.obj.ID) == b'\xfe\xff\x00A'
        assert tree.obj.IDTree.objgen == original_id_tree.objgen

    def test_byte_distinct_element_ids_round_trip(self, blank, outpdf):
        tree = blank.open_structure_tree()
        encoded_id = b'\xfe\xff\x00A'
        tree.add(Name.P).element_id = encoded_id
        tree.add(Name.P).element_id = 'A'
        blank.save(outpdf)

        with Pdf.open(outpdf) as reopened:
            reopened_tree = reopened.open_structure_tree()
            encoded = reopened_tree.find_by_id(encoded_id)
            plain = reopened_tree.find_by_id('A')
            assert encoded is not None and encoded.element_id == encoded_id
            assert plain is not None and plain.element_id == 'A'

    def test_exact_duplicate_byte_element_id_is_rejected(self, blank):
        tree = blank.open_structure_tree()
        first = tree.add(Name.P)
        second = tree.add(Name.P)
        first.element_id = b'\xfe\xff\x00A'

        with pytest.raises(StructureTreeError, match="not unique"):
            second.element_id = b'\xfe\xff\x00A'

        assert second.element_id is None

    def test_byte_id_rename_collision_is_atomic(self, blank):
        tree = blank.open_structure_tree()
        encoded = tree.add(Name.P)
        plain = tree.add(Name.P)
        encoded_id = b'\xfe\xff\x00A'
        encoded.element_id = encoded_id
        plain.element_id = 'A'
        original_id_tree = tree.obj.IDTree

        with pytest.raises(StructureTreeError, match="not unique"):
            encoded.element_id = 'A'

        assert encoded.element_id == encoded_id
        assert plain.element_id == 'A'
        assert tree.obj.IDTree.objgen == original_id_tree.objgen
        assert tree.find_by_id(encoded_id) == encoded
        assert tree.find_by_id('A') == plain

    def test_element_id_rejects_non_text_or_bytes(self, blank):
        elem = blank.open_structure_tree().add(Name.P)

        with pytest.raises(TypeError, match="str, bytes, or None"):
            elem.element_id = 42

    def test_role_map(self, blank):
        tree = blank.open_structure_tree().create()
        assert tree.role_map is None
        tree.add_role(Name.Chapter, Name.Sect)
        tree.add_role(Name.MyPara, Name.P)
        assert tree.role_map[Name.Chapter] == Name.Sect
        assert tree.role_map[Name.MyPara] == Name.P

    @pytest.mark.parametrize(
        ('key', 'attribute'),
        [(Name.RoleMap, 'role_map'), (Name.ClassMap, 'class_map')],
    )
    def test_map_accessors_reject_malformed_values(self, blank, key, attribute):
        tree = blank.open_structure_tree().create()
        tree.obj[key] = String('bad')

        with pytest.raises(StructureTreeError, match='must be a dictionary'):
            getattr(tree, attribute)

    @pytest.mark.parametrize(
        ('key', 'attribute'),
        [(Name.RoleMap, 'role_map'), (Name.ClassMap, 'class_map')],
    )
    def test_map_accessors_reject_foreign_dictionaries(self, key, attribute):
        with Pdf.new() as first, Pdf.new() as second:
            first.add_blank_page()
            second.add_blank_page()
            foreign = second.make_indirect(Dictionary())
            raw_root = Dictionary(Type=Name.StructTreeRoot, K=Array([]))
            raw_root[key] = foreign
            first.Root.StructTreeRoot = raw_root
            tree = first.open_structure_tree()

            with pytest.raises(StructureTreeError, match='another PDF'):
                getattr(tree, attribute)

    @pytest.mark.parametrize(
        ('custom', 'standard'),
        [(String('Custom'), Name.P), (Name.Custom, String('P')), (Name.Custom, 42)],
    )
    def test_role_map_requires_names_without_mutation(self, blank, custom, standard):
        tree = blank.open_structure_tree().create()

        with pytest.raises(TypeError, match="pikepdf.Name"):
            tree.add_role(custom, standard)

        assert Name.RoleMap not in tree.obj

    def test_malformed_role_map_is_not_overwritten(self, blank):
        tree = blank.open_structure_tree().create()
        malformed = String('bad')
        tree.obj.RoleMap = malformed

        with pytest.raises(StructureTreeError, match="must be a dictionary"):
            tree.add_role(Name.Custom, Name.P)

        assert tree.obj.RoleMap == malformed

    def test_add_role_rejects_existing_non_name_values_without_mutation(self, blank):
        tree = blank.open_structure_tree().create()
        tree.obj.RoleMap = Dictionary(Bad=String('P'))

        with pytest.raises(StructureTreeError, match='values must be names'):
            tree.add_role(Name.Custom, Name.P)

        assert Name.Custom not in tree.obj.RoleMap
        assert tree.obj.RoleMap.Bad == String('P')

    def test_class_map(self, blank):
        tree = blank.open_structure_tree().create()
        assert tree.class_map is None
        tree.obj.ClassMap = Dictionary(Normal=Dictionary(O=Name.Layout))
        assert tree.class_map.Normal.O == Name.Layout

    def test_tree_backreference(self, blank):
        tree = blank.open_structure_tree()
        assert tree.add(Name.Document).tree is tree

    def test_elem_equality(self, blank):
        tree = blank.open_structure_tree()
        doc = tree.add(Name.Document)
        assert doc == tree.element(doc.obj)
        assert doc != tree.add(Name.Part)
        assert doc.__eq__(object()) is NotImplemented

    def test_ref_equality(self, blank):
        page = blank.pages[0]
        tree = blank.open_structure_tree()
        elem = tree.add(Name.P, page=page)
        first = elem.add_content(page, 0)
        assert first == elem.content[0]
        assert first != elem.add_content(page, 1)
        assert first.__eq__(object()) is NotImplemented
        annot = blank.make_indirect(Dictionary(Type=Name.Annot))
        page.obj.Annots = Array([annot])
        ref = elem.add_object(annot, page)
        assert ref == elem.kids[-1]
        assert ref.__eq__(object()) is NotImplemented


def test_explicit_conversion_mode(text_pdf):
    with pikepdf.explicit_conversion():
        page = text_pdf.pages[0]
        tree = text_pdf.open_structure_tree()
        doc = tree.add(Name.Document)
        result = mark_text_runs(page, {(Name.F2, Decimal(24)): Name.H1}, parent=doc)
        assert [(str(mc.tag), mc.mcid) for mc in result] == [('/H1', 0)]
        assert tree.marked
        tree.marked = False
        assert not tree.marked
        tree.marked = True
        assert tree.parent_tree.next_key == 1
        assert next_mcid(page) == 1
        assert tree.validate() == []


def test_docs_example_round_trips():
    with Pdf.new() as pdf:
        page = pdf.add_blank_page()
        page.obj.Contents = Array([])
        page.contents_add(b"BT (Hello) Tj ET\n")
        page.contents_coalesce()

        tree = pdf.open_structure_tree()
        document = tree.add(Name.Document)
        paragraph = document.add_child(Name.P, page=page)

        marker = ContentMarker(page)
        marker.mark(Name.P, 0, 3, element=paragraph)
        marker.apply()

        assert tree.validate() == []
        bio = BytesIO()
        pdf.save(bio)
        bio.seek(0)
        with Pdf.open(bio) as reopened:
            assert reopened.open_structure_tree().validate() == []


class TestDuplicateIdentifiers:
    def test_second_element_cannot_claim_an_mcid(self, blank):
        page = blank.pages[0]
        tree = blank.open_structure_tree()
        first = tree.add(Name.P, page=page)
        second = tree.add(Name.Span, page=page)
        first.add_content(page, 0)
        with pytest.raises(StructureTreeError, match="already claimed"):
            second.add_content(page, 0)
        assert Name.K not in second.obj
        assert tree.parent_tree.entry_for_page(page)[0].objgen == first.obj.objgen

    def test_element_cannot_claim_its_own_mcid_twice(self, blank):
        page = blank.pages[0]
        tree = blank.open_structure_tree()
        elem = tree.add(Name.P, page=page)
        elem.add_content(page, 0)
        with pytest.raises(StructureTreeError, match="already claimed"):
            elem.add_content(page, 0)
        assert elem.obj.K == Array([0])
        assert tree.parent_tree.entry_for_page(page)[0].objgen == elem.obj.objgen

    def test_stale_slot_does_not_hide_same_element_k_claim(self, blank):
        page = blank.pages[0]
        tree = blank.open_structure_tree()
        elem = tree.add(Name.P, page=page)
        elem.obj.K = Array([0])
        page.obj.StructParents = 0
        entry = blank.make_indirect(Array([None]))
        tree.parent_tree[0] = entry

        with pytest.raises(StructureTreeError, match="already claimed"):
            elem.add_content(page, 0)

        assert elem.obj.K == Array([0])
        assert entry[0] is None

    def test_stale_slot_does_not_hide_other_element_k_claim(self, blank):
        page = blank.pages[0]
        tree = blank.open_structure_tree()
        first = tree.add(Name.P, page=page)
        second = tree.add(Name.Span, page=page)
        first.obj.K = Array([0])
        page.obj.StructParents = 0
        entry = blank.make_indirect(Array([None]))
        tree.parent_tree[0] = entry

        with pytest.raises(StructureTreeError, match="already claimed"):
            second.add_content(page, 0)

        assert Name.K not in second.obj
        assert entry[0] is None

    def test_register_content_can_repair_one_existing_k_claim(self, blank):
        page = blank.pages[0]
        tree = blank.open_structure_tree()
        elem = tree.add(Name.P, page=page)
        elem.obj.K = Array([0])

        tree.parent_tree.register_content(page, 0, elem)

        assert elem.obj.K == Array([0])
        assert tree.parent_tree.entry_for_page(page)[0].objgen == elem.obj.objgen

    def test_register_content_rejects_duplicate_k_claims(self, blank):
        page = blank.pages[0]
        tree = blank.open_structure_tree()
        elem = tree.add(Name.P, page=page)
        elem.obj.K = Array([0, 0])

        with pytest.raises(StructureTreeError, match='exactly one reachable'):
            tree.parent_tree.register_content(page, 0, elem)

        assert Name.StructParents not in page.obj

    def test_second_element_cannot_claim_an_object(self, blank):
        page = blank.pages[0]
        annot = blank.make_indirect(Dictionary(Type=Name.Annot))
        page.obj.Annots = Array([annot])
        tree = blank.open_structure_tree()
        first = tree.add(Name.Link, page=page)
        second = tree.add(Name.Link, page=page)
        first.add_object(annot, page)
        with pytest.raises(StructureTreeError, match="already claimed"):
            second.add_object(annot, page)
        assert Name.K not in second.obj

    def test_same_object_can_be_referenced_on_two_pages_by_one_element(self, blank):
        first_page = blank.pages[0]
        second_page = blank.add_blank_page()
        form = blank.make_stream(b'', Type=Name.XObject, Subtype=Name.Form)
        tree = blank.open_structure_tree()
        elem = tree.add(Name.Figure, page=first_page)

        elem.add_object(form, first_page)
        key = form.StructParent
        elem.add_object(form, second_page)

        assert len(elem.obj.K) == 2
        assert Name.Pg not in elem.obj.K[0]
        assert elem.obj.K[1].Pg.objgen == second_page.obj.objgen
        assert form.StructParent == key
        assert tree.parent_tree[key].objgen == elem.obj.objgen

    def test_same_object_cannot_be_referenced_twice_on_one_page(self, blank):
        page = blank.pages[0]
        form = blank.make_stream(b'', Type=Name.XObject, Subtype=Name.Form)
        tree = blank.open_structure_tree()
        elem = tree.add(Name.Figure, page=page)
        elem.add_object(form, page)

        with pytest.raises(StructureTreeError, match="same page"):
            elem.add_object(form, page)

        assert len(elem.obj.K) == 1

    def test_other_element_cannot_reference_same_object_on_another_page(self, blank):
        first_page = blank.pages[0]
        second_page = blank.add_blank_page()
        form = blank.make_stream(b'', Type=Name.XObject, Subtype=Name.Form)
        tree = blank.open_structure_tree()
        first = tree.add(Name.Figure, page=first_page)
        second = tree.add(Name.Figure, page=second_page)
        first.add_object(form, first_page)

        with pytest.raises(StructureTreeError, match="another structure element"):
            second.add_object(form, second_page)

        assert Name.K not in second.obj

    def test_missing_struct_parent_does_not_hide_same_element_objr(self, blank):
        page = blank.pages[0]
        annot = blank.make_indirect(Dictionary(Type=Name.Annot))
        page.obj.Annots = Array([annot])
        tree = blank.open_structure_tree()
        elem = tree.add(Name.Link, page=page)
        elem.obj.K = Array([Dictionary(Type=Name.OBJR, Obj=annot)])

        with pytest.raises(StructureTreeError, match="already claimed"):
            elem.add_object(annot, page)

        assert len(elem.obj.K) == 1
        assert Name.StructParent not in annot

    def test_missing_struct_parent_does_not_hide_other_element_objr(self, blank):
        page = blank.pages[0]
        annot = blank.make_indirect(Dictionary(Type=Name.Annot))
        page.obj.Annots = Array([annot])
        tree = blank.open_structure_tree()
        first = tree.add(Name.Link, page=page)
        second = tree.add(Name.Link, page=page)
        first.obj.K = Array([Dictionary(Type=Name.OBJR, Obj=annot)])

        with pytest.raises(StructureTreeError, match="already claimed"):
            second.add_object(annot, page)

        assert Name.K not in second.obj
        assert Name.StructParent not in annot

    def test_register_object_can_repair_one_existing_objr_claim(self, blank):
        page = blank.pages[0]
        annot = blank.make_indirect(Dictionary(Type=Name.Annot))
        page.obj.Annots = Array([annot])
        tree = blank.open_structure_tree()
        elem = tree.add(Name.Link, page=page)
        elem.obj.K = Array([Dictionary(Type=Name.OBJR, Obj=annot)])

        key = tree.parent_tree.register_object(annot, elem)

        assert len(elem.obj.K) == 1
        assert annot.StructParent == key
        assert tree.parent_tree[key].objgen == elem.obj.objgen

    def test_register_object_rejects_annotation_claimed_on_the_wrong_page(self, blank):
        actual_page = blank.pages[0]
        wrong_page = blank.add_blank_page()
        annot = blank.make_indirect(Dictionary(Type=Name.Annot))
        actual_page.obj.Annots = Array([annot])
        tree = blank.open_structure_tree()
        elem = tree.add(Name.Link)
        elem.obj.K = Array([Dictionary(Type=Name.OBJR, Obj=annot, Pg=wrong_page.obj)])

        with pytest.raises(StructureTreeError, match='exactly its claimed page'):
            tree.parent_tree.register_object(annot, elem)

        assert Name.StructParent not in annot

    def test_register_object_repairs_form_claims_on_distinct_pages(self, blank):
        first_page = blank.pages[0]
        second_page = blank.add_blank_page()
        form = blank.make_stream(b'', Type=Name.XObject, Subtype=Name.Form)
        tree = blank.open_structure_tree()
        elem = tree.add(Name.Figure)
        elem.obj.K = Array(
            [
                Dictionary(Type=Name.OBJR, Obj=form, Pg=first_page.obj),
                Dictionary(Type=Name.OBJR, Obj=form, Pg=second_page.obj),
            ]
        )

        key = tree.parent_tree.register_object(form, elem)

        assert form.StructParent == key
        assert tree.parent_tree[key].objgen == elem.obj.objgen

    def test_register_object_rejects_duplicate_objr_claims(self, blank):
        page = blank.pages[0]
        annot = blank.make_indirect(Dictionary(Type=Name.Annot))
        page.obj.Annots = Array([annot])
        tree = blank.open_structure_tree()
        elem = tree.add(Name.Link, page=page)
        claim = Dictionary(Type=Name.OBJR, Obj=annot)
        elem.obj.K = Array([claim, Dictionary(Type=Name.OBJR, Obj=annot)])

        with pytest.raises(StructureTreeError, match='same page'):
            tree.parent_tree.register_object(annot, elem)

        assert Name.StructParent not in annot

    def test_content_marker_refuses_an_identifier_already_in_the_stream(self, blank):
        page = blank.pages[0]
        set_contents(blank, page, b"/P <</MCID 0>> BDC BT (a) Tj ET EMC BT (b) Tj ET\n")
        marker = ContentMarker(page, first_mcid=0)
        with pytest.raises(StructureTreeError, match="already used by this page"):
            marker.mark(Name.P, 5, 8)

    def test_validate_reports_duplicate_mcids_in_the_stream(self, blank):
        page = blank.pages[0]
        set_contents(
            blank,
            page,
            b"/P <</MCID 0>> BDC BT (a) Tj ET EMC /P <</MCID 0>> BDC BT (b) Tj ET EMC\n",
        )
        tree = blank.open_structure_tree()
        tree.add(Name.P, page=page).add_content(page, 0)
        assert any('must be unique' in p for p in tree.validate())


class TestCleanupCompleteness:
    def test_remove_clears_struct_parent_of_referenced_objects(self, blank):
        page = blank.pages[0]
        dropped = blank.make_indirect(Dictionary(Type=Name.Annot, Subtype=Name.Link))
        retained = blank.make_indirect(Dictionary(Type=Name.Annot, Subtype=Name.Link))
        page.obj.Annots = Array([dropped, retained])
        tree = blank.open_structure_tree()
        doc = tree.add(Name.Document, page=page)
        doc.add_child(Name.Link, page=page).add_object(retained, page)
        link = doc.add_child(Name.Link, page=page)
        link.add_object(dropped, page)

        link.remove()

        assert Name.StructParent not in dropped
        assert retained.StructParent == 0
        assert tree.parent_tree[0].objgen == doc.children[0].obj.objgen

    def test_tree_remove_clears_annotation_and_xobject_keys(self, blank):
        page = blank.pages[0]
        annot = blank.make_indirect(Dictionary(Type=Name.Annot, Subtype=Name.Link))
        page.obj.Annots = Array([annot])
        xobj = blank.make_stream(b"", Type=Name.XObject, Subtype=Name.Form)
        page.obj.Resources = Dictionary(XObject=Dictionary(Fm0=xobj))
        tree = blank.open_structure_tree()
        doc = tree.add(Name.Document, page=page)
        doc.add_child(Name.Link, page=page).add_object(annot, page)
        doc.add_child(Name.P, page=page).add_content(page, 0, stream=xobj)

        tree.remove()

        assert Name.StructParent not in annot
        assert Name.StructParents not in xobj
        assert Name.StructParents not in page.obj
        assert not tree.exists

    def test_tree_remove_ignores_malformed_content_references(self, blank):
        page = blank.pages[0]
        tree = blank.open_structure_tree()
        elem = tree.add(Name.P, page=page)
        elem.obj.K = Array(
            [
                Dictionary(
                    Type=Name.MCR,
                    MCID=0,
                    Pg=page.obj,
                    Stm=String('not a stream'),
                ),
                Dictionary(Type=Name.OBJR, Pg=page.obj, Obj=String('not an object')),
            ]
        )

        tree.remove()

        assert not tree.exists
        assert Name.MarkInfo not in blank.Root

    def test_tree_remove_preserves_other_mark_info_entries(self, blank):
        tree = blank.open_structure_tree().create()
        blank.Root.MarkInfo.Suspects = True
        blank.Root.MarkInfo.PrivateData = String('keep')

        tree.remove()

        assert Name.Marked not in blank.Root.MarkInfo
        assert blank.Root.MarkInfo.Suspects is True
        assert blank.Root.MarkInfo.PrivateData == String('keep')

    def test_tree_remove_skips_foreign_referenced_objects(self):
        with Pdf.new() as first, Pdf.new() as second:
            page = first.add_blank_page()
            second.add_blank_page()
            foreign_annot = second.make_indirect(
                Dictionary(Type=Name.Annot, StructParent=7)
            )
            foreign_stream = second.make_stream(b'', StructParents=8)
            tree = first.open_structure_tree()
            elem = tree.add(Name.Link, page=page)
            elem.obj.K = Array(
                [
                    Dictionary(Type=Name.OBJR, Obj=foreign_annot, Pg=page.obj),
                    Dictionary(
                        Type=Name.MCR,
                        MCID=0,
                        Pg=page.obj,
                        Stm=foreign_stream,
                    ),
                ]
            )

            tree.remove()

            assert not tree.exists
            assert foreign_annot.StructParent == 7
            assert foreign_stream.StructParents == 8
            assert Name.MarkInfo not in first.Root

    def test_tree_remove_clears_nested_form_xobject_keys(self, blank):
        page = blank.pages[0]
        inner = blank.make_stream(
            b'', Type=Name.XObject, Subtype=Name.Form, StructParents=2
        )
        outer = blank.make_stream(
            b'',
            Type=Name.XObject,
            Subtype=Name.Form,
            StructParents=1,
            Resources=Dictionary(XObject=Dictionary(Inner=inner)),
        )
        page.obj.Resources = Dictionary(XObject=Dictionary(Outer=outer))
        tree = blank.open_structure_tree().create()

        tree.remove()

        assert Name.StructParents not in outer
        assert Name.StructParents not in inner
        assert not tree.exists

    def test_tree_remove_finds_forms_through_inherited_resources(self, blank):
        page = blank.pages[0]
        form = blank.make_stream(
            b'', Type=Name.XObject, Subtype=Name.Form, StructParents=3
        )
        if Name.Resources in page.obj:
            del page.obj[Name.Resources]
        page.obj.Parent.Resources = Dictionary(XObject=Dictionary(Form=form))
        tree = blank.open_structure_tree().create()

        tree.remove()

        assert Name.StructParents not in form

    def test_tree_remove_without_a_tree(self, blank):
        page = blank.pages[0]
        page.obj.StructParents = 3
        blank.open_structure_tree().remove()
        assert Name.StructParents not in page.obj


class TestDepthLimit:
    @staticmethod
    def _deep_tree(pdf, depth):
        page = pdf.pages[0]
        set_contents(pdf, page, b"BT (a) Tj ET\n")
        tree = pdf.open_structure_tree(max_depth=2)
        root = tree.add(Name.Document, page=page)
        node = root
        for _ in range(depth):
            node = node.add_child(Name.Sect, page=page)
        return tree, root, node.add_child(Name.P, page=page), page

    def test_walk_still_honours_max_depth(self, blank):
        tree, _root, _deep, _page = self._deep_tree(blank, 5)
        assert len(list(tree.walk())) == 3

    def test_validate_reaches_past_max_depth(self, blank):
        tree, _root, deep, _page = self._deep_tree(blank, 5)
        del deep.obj[Name.S]
        assert any('missing required /S' in p for p in tree.validate())

    def test_remove_reaches_past_max_depth(self, blank):
        tree, root, deep, page = self._deep_tree(blank, 5)
        deep.add_content(page, 0)
        assert tree.parent_tree.entry_for_page(page)[0] is not None
        root.remove()
        assert tree.parent_tree.entry_for_page(page)[0] is None
