# SPDX-FileCopyrightText: 2026 Khushwant Parihar
# SPDX-License-Identifier: CC0-1.0

from __future__ import annotations

from decimal import Decimal

import pytest
from conftest import set_structure_contents as set_contents

from pikepdf import (
    Array,
    ContentMarker,
    Dictionary,
    Name,
    NameTree,
    Pdf,
    String,
    StructureTreeError,
    mark_text_runs,
)


class TestValidate:
    def test_clean(self, text_pdf):
        page = text_pdf.pages[0]
        tree = text_pdf.open_structure_tree()
        doc = tree.add(Name.Document)
        mark_text_runs(
            page,
            {(Name.F2, Decimal(24)): Name.H1, (Name.F1, Decimal(12)): Name.P},
            parent=doc,
        )
        assert tree.validate() == []

    def test_no_tree(self, blank):
        assert blank.open_structure_tree().validate() == [
            'Document has no /StructTreeRoot'
        ]

    def test_not_marked(self, blank):
        tree = blank.open_structure_tree()
        tree.add(Name.Document)
        tree.marked = False
        assert any('/MarkInfo' in p for p in tree.validate())

    def test_wrong_root_type(self, blank):
        tree = blank.open_structure_tree()
        tree.add(Name.Document)
        tree.obj.Type = Name.Catalog
        assert any('wrong /Type' in p for p in tree.validate())

    def test_missing_root_type(self, blank):
        tree = blank.open_structure_tree().create()
        del tree.obj[Name.Type]

        assert any('missing required /Type' in p for p in tree.validate())

    def test_missing_s(self, blank):
        tree = blank.open_structure_tree().create()
        tree.obj.K = Array(
            [blank.make_indirect(Dictionary(Type=Name.StructElem, P=tree.obj))]
        )
        assert any('missing required /S' in p for p in tree.validate())

    def test_missing_parent(self, blank):
        tree = blank.open_structure_tree()
        doc = tree.add(Name.Document)
        del doc.obj[Name.P]
        assert any('missing required /P' in p for p in tree.validate())

    def test_parent_does_not_claim_child(self, blank):
        tree = blank.open_structure_tree()
        doc = tree.add(Name.Document)
        child = doc.add_child(Name.P)
        doc.obj.K = Array([])
        tree.obj.K = Array([doc.obj, child.obj])
        assert any('/P that does not name' in p for p in tree.validate())

    def test_parent_not_an_element(self, blank):
        tree = blank.open_structure_tree()
        doc = tree.add(Name.Document)
        doc.add_child(Name.P).obj.P = blank.make_indirect(Dictionary(Type=Name.Page))
        assert any('not a structure element' in p for p in tree.validate())

    def test_two_direct_terminal_elements_are_walked_and_validate_cleanly(self, blank):
        tree = blank.open_structure_tree()
        parent = tree.add(Name.Document)
        first = Dictionary(Type=Name.StructElem, S=Name.P, P=parent.obj)
        second = Dictionary(Type=Name.StructElem, S=Name.P, P=parent.obj)
        parent.obj.K = Array([first, second])

        assert [elem.tag for elem in tree.walk()] == [
            Name.Document,
            Name.P,
            Name.P,
        ]
        assert tree.validate(check_content=False) == []

        parent.element_id = 'document'

        assert tree.find_by_id('document') == parent
        assert tree.validate(check_content=False) == []

    def test_direct_terminal_element_mutation_is_explicitly_unsupported(self, blank):
        tree = blank.open_structure_tree()
        parent = tree.add(Name.Document)
        leaf = Dictionary(Type=Name.StructElem, S=Name.P, P=parent.obj)
        parent.obj.K = Array([leaf])
        wrapped = parent.children[0]

        with pytest.raises(StructureTreeError, match="Direct structure elements"):
            wrapped.tag = Name.H1
        with pytest.raises(StructureTreeError, match="Direct structure elements"):
            wrapped.remove()

        assert parent.obj.K[0].S == Name.P

    def test_direct_element_used_as_parent_is_reported(self, blank):
        tree = blank.open_structure_tree().create()
        parent = Dictionary(Type=Name.StructElem, S=Name.Sect, P=tree.obj)
        child = blank.make_indirect(
            Dictionary(Type=Name.StructElem, S=Name.P, P=parent)
        )
        parent.K = Array([child])
        tree.obj.K = Array([parent])

        assert any(
            'direct structure element and cannot be a parent' in problem
            for problem in tree.validate(check_content=False)
        )

    def test_direct_element_in_parent_tree_is_reported(self, blank):
        page = blank.pages[0]
        set_contents(blank, page, b'/P <</MCID 0>> BDC EMC\n')
        tree = blank.open_structure_tree().create()
        elem = Dictionary(
            Type=Name.StructElem,
            S=Name.P,
            P=tree.obj,
            Pg=page.obj,
            K=Array([0]),
        )
        tree.obj.K = Array([elem])
        page.obj.StructParents = 0
        tree.parent_tree[0] = blank.make_indirect(Array([elem]))

        assert any(
            'points to a direct structure element' in problem
            for problem in tree.validate()
        )

    def test_direct_element_in_id_tree_is_reported(self, blank):
        tree = blank.open_structure_tree().create()
        elem = Dictionary(
            Type=Name.StructElem,
            S=Name.P,
            P=tree.obj,
            ID=String('direct'),
        )
        tree.obj.K = Array([elem])
        tree.obj.IDTree = blank.make_indirect(
            Dictionary(Names=Array([String('direct'), elem]))
        )

        assert any(
            '/IDTree entry' in problem and 'direct structure element' in problem
            for problem in tree.validate(check_content=False)
        )

    def test_next_key_too_low(self, blank):
        page = blank.pages[0]
        tree = blank.open_structure_tree()
        tree.add(Name.P, page=page).add_content(page, 0)
        tree.obj.ParentTreeNextKey = 0
        assert any('/ParentTreeNextKey' in p for p in tree.validate())

    def test_negative_struct_parents_mapping_is_valid(self, blank):
        page = blank.pages[0]
        set_contents(blank, page, b'/P <</MCID 0>> BDC EMC\n')
        tree = blank.open_structure_tree()
        elem = tree.add(Name.P, page=page)
        elem.obj.K = Array([0])
        page.obj.StructParents = -2
        tree.parent_tree[-2] = blank.make_indirect(Array([elem.obj]))
        tree.parent_tree.next_key = -1

        assert tree.validate() == []

    def test_negative_struct_parent_mapping_is_valid(self, blank):
        page = blank.pages[0]
        annotation = blank.make_indirect(Dictionary(Type=Name.Annot, StructParent=-1))
        page.obj.Annots = Array([annotation])
        tree = blank.open_structure_tree()
        elem = tree.add(Name.Link, page=page)
        elem.obj.K = Array([Dictionary(Type=Name.OBJR, Obj=annotation)])
        tree.parent_tree[-1] = elem.obj

        assert tree.validate() == []

    def test_missing_struct_parents(self, blank):
        page = blank.pages[0]
        tree = blank.open_structure_tree()
        tree.add(Name.P, page=page).add_content(page, 0)
        del page.obj[Name.StructParents]
        assert any('has no /StructParents' in p for p in tree.validate())

    def test_struct_parents_not_in_tree(self, blank):
        page = blank.pages[0]
        tree = blank.open_structure_tree().create()
        page.obj.StructParents = 12
        assert any('not in the parent tree' in p for p in tree.validate())

    def test_parent_tree_entry_not_array(self, blank):
        page = blank.pages[0]
        tree = blank.open_structure_tree().create()
        page.obj.StructParents = 0
        tree.parent_tree[0] = blank.make_indirect(Dictionary())
        assert any('is not an array' in p for p in tree.validate())

    def test_mcid_missing_from_parent_tree(self, blank):
        page = blank.pages[0]
        set_contents(blank, page, b"/P <</MCID 0>> BDC BT (x) Tj ET EMC\n")
        tree = blank.open_structure_tree()
        elem = tree.add(Name.P, page=page)
        elem.add_content(page, 0)
        tree.parent_tree.entry_for_page(page)[0] = None
        assert any('no parent tree entry' in p for p in tree.validate())

    def test_mcid_points_at_wrong_element(self, blank):
        page = blank.pages[0]
        set_contents(blank, page, b"/P <</MCID 0>> BDC BT (x) Tj ET EMC\n")
        tree = blank.open_structure_tree()
        elem = tree.add(Name.P, page=page)
        other = tree.add(Name.Span, page=page)
        elem.add_content(page, 0)
        tree.parent_tree.entry_for_page(page)[0] = other.obj
        assert any('wrong element' in p for p in tree.validate())

    def test_unclaimed_mcid_in_content_is_core_valid(self, blank):
        page = blank.pages[0]
        set_contents(blank, page, b"/P <</MCID 0>> BDC BT (x) Tj ET EMC\n")
        tree = blank.open_structure_tree().create()

        assert tree.validate() == []

    def test_claimed_mcid_missing_from_content(self, blank):
        page = blank.pages[0]
        tree = blank.open_structure_tree()
        tree.add(Name.P, page=page).add_content(page, 0)
        assert any('does not appear in the content' in p for p in tree.validate())

    def test_content_without_page(self, blank):
        tree = blank.open_structure_tree()
        elem = tree.add(Name.P)
        elem.obj.K = Array([Dictionary(Type=Name.MCR, MCID=0)])
        assert any('content with no page' in p for p in tree.validate())


def _ua_page(pdf):
    page = pdf.add_blank_page()
    page.obj.Resources = Dictionary(
        Font=Dictionary(
            F1=pdf.make_indirect(
                Dictionary(
                    Type=Name.Font,
                    Subtype=Name.Type1,
                    BaseFont=Name.Helvetica,
                    Encoding=Name.WinAnsiEncoding,
                )
            )
        )
    )
    set_contents(
        pdf,
        page,
        b"BT /F1 18 Tf 72 720 Td (A Heading) Tj ET\n"
        b"BT /F1 12 Tf 72 690 Td (Some body text.) Tj ET\n"
        b"q 0 0 1 RG 72 680 m 300 680 l S Q\n",
    )
    pdf.Root.Lang = String('en-US')
    pdf.Root.ViewerPreferences = Dictionary(DisplayDocTitle=True)
    with pdf.open_metadata() as meta:
        meta['dc:title'] = 'Structure demo'
    return page


def _failed_ua_rules(report, *tags: str) -> set[tuple[str, str]]:
    return {
        (rule.attrib['clause'], rule.attrib['testNumber'])
        for rule in report.find('details')
        if rule.attrib.get('status') == 'failed'
        and set(tags) & set(rule.attrib.get('tags', '').split(','))
    }


def test_verapdf_rejects_the_untagged_baseline(verapdf_rules, outpdf):
    """Negative control: the same page untagged must fail the rules we fix.

    Without this, the assertion in the test below could pass vacuously if
    veraPDF ever stopped running the structure rules at all.
    """
    with Pdf.new() as pdf:
        _ua_page(pdf)
        pdf.save(outpdf)
    failed = _failed_ua_rules(
        verapdf_rules(outpdf, flavour='ua1'), 'structure', 'artifact', 'syntax'
    )
    assert ('7.1', '11') in failed
    assert ('7.1', '3') in failed
    assert ('6.2', '1') in failed


def test_verapdf_accepts_the_structure_we_write(verapdf_rules, outpdf):
    """Every PDF/UA-1 structure and artifact rule must pass on our output.

    Font embedding and PDF/UA XMP identification are outside the scope of a
    structure tree API, so rules tagged for those are not asserted here; see
    the untagged baseline above for what tagging is actually responsible for.
    """
    with Pdf.new() as pdf:
        page = _ua_page(pdf)
        tree = pdf.open_structure_tree()
        document = tree.add(Name.Document, lang='en-US')
        marker = ContentMarker(page)
        marker.mark(Name.H1, 0, 5, element=document.add_child(Name.H1, page=page))
        marker.mark(Name.P, 5, 10, element=document.add_child(Name.P, page=page))
        marker.mark_artifact(10, 16)
        marker.apply()
        assert tree.validate() == []
        pdf.save(outpdf)

    report = verapdf_rules(outpdf, flavour='ua1')
    assert _failed_ua_rules(report, 'structure', 'artifact', 'syntax') == set()
    assert int(report.find('details').attrib['passedRules']) > 50


class TestMalformedTrees:
    """A damaged tree must be reportable and cleanable, never a crash."""

    @pytest.mark.parametrize(
        'bad_type',
        [42, True, Decimal('1.5'), String('bad'), Array([]), Dictionary()],
    )
    def test_malformed_k_type_never_leaks_a_pdf_error(self, blank, bad_type):
        tree = blank.open_structure_tree()
        elem = tree.add(Name.Document)
        elem.obj.K = Array([Dictionary(Type=bad_type)])

        assert any(
            'malformed /K' in problem for problem in tree.validate(check_content=False)
        )
        assert repr(elem).startswith('<pikepdf.StructElem:')
        with pytest.raises(StructureTreeError):
            _ = elem.kids

    def test_validate_reports_non_dictionary_parent(self, blank):
        tree = blank.open_structure_tree()
        elem = tree.add(Name.P)
        elem.obj.P = 42
        assert any('not a dictionary' in p for p in tree.validate())

    def test_validate_reports_malformed_kids(self, blank):
        tree = blank.open_structure_tree()
        doc = tree.add(Name.Document)
        doc.obj.K = Array([String("nonsense"), Dictionary(Type=Name.Whatever)])
        problems = tree.validate()
        assert sum('malformed /K entry' in p for p in problems) == 2

    def test_repr_survives_malformed_kids(self, blank):
        tree = blank.open_structure_tree()
        doc = tree.add(Name.Document)
        doc.obj.K = Array([String("nonsense")])
        assert repr(doc) == '<pikepdf.StructElem: /Document with 0 children>'

    def test_walk_rejects_malformed_kids(self, blank):
        tree = blank.open_structure_tree()
        doc = tree.add(Name.Document)
        good = doc.add_child(Name.P)
        doc.obj.K = Array([String("nonsense"), good.obj])

        with pytest.raises(StructureTreeError, match='Unexpected object'):
            list(tree.walk())

    @pytest.mark.parametrize(
        'raw_kids',
        [String('bad'), Array([String('bad')]), Array([Dictionary(Type=Name.MCR)])],
    )
    def test_element_mutations_reject_malformed_existing_k_atomically(
        self, blank, raw_kids
    ):
        page = blank.pages[0]
        tree = blank.open_structure_tree()
        elem = tree.add(Name.P, page=page)
        annotation = blank.make_indirect(Dictionary(Type=Name.Annot))
        elem.obj.K = raw_kids
        object_count = len(blank.objects)

        with pytest.raises(StructureTreeError):
            elem.add_child(Name.Span)
        with pytest.raises(StructureTreeError):
            elem.add_content(page, 0)
        with pytest.raises(StructureTreeError):
            elem.add_object(annotation, page)

        assert elem.obj.K == raw_kids
        assert len(blank.objects) == object_count
        assert Name.StructParents not in page.obj
        assert Name.StructParent not in annotation

    def test_root_kids_and_add_reject_malformed_k_atomically(self, blank):
        tree = blank.open_structure_tree()
        tree.add(Name.Document)
        tree.obj.K = Array([String('bad')])
        object_count = len(blank.objects)

        with pytest.raises(StructureTreeError, match='/StructTreeRoot /K entry'):
            _ = tree.kids
        with pytest.raises(StructureTreeError, match='/StructTreeRoot /K entry'):
            tree.add(Name.Part)

        assert tree.obj.K == Array([String('bad')])
        assert len(blank.objects) == object_count


class TestValidationHardening:
    def test_direct_structure_tree_root_is_reported_and_cannot_be_extended(self, blank):
        direct_root = Dictionary(
            Type=Name.StructTreeRoot,
            K=Array([]),
            ParentTree=Dictionary(Nums=Array([])),
            ParentTreeNextKey=0,
        )
        blank.Root.StructTreeRoot = direct_root
        tree = blank.open_structure_tree()

        assert any(
            '/StructTreeRoot is a direct object' in problem
            for problem in tree.validate(check_content=False)
        )
        with pytest.raises(StructureTreeError, match="indirect"):
            tree.create()
        with pytest.raises(StructureTreeError, match="indirect"):
            tree.add(Name.P)

        assert not tree.obj.is_indirect
        assert tree.obj == direct_root
        assert len(tree.obj.K) == 0
        assert Name.MarkInfo not in blank.Root

    def test_explicit_element_pages_are_validated_without_content(self, blank):
        tree = blank.open_structure_tree()
        scalar = tree.add(Name.P)
        direct = tree.add(Name.P)
        detached = tree.add(Name.P)
        scalar.obj.Pg = 42
        direct.obj.Pg = Dictionary(Type=Name.Page)
        detached.obj.Pg = blank.make_indirect(Dictionary(Type=Name.Page))

        problems = tree.validate(check_content=False)

        assert any('/Pg that is not a page dictionary' in p for p in problems)
        assert any('direct /Pg' in p for p in problems)
        assert any('page outside the page tree' in p for p in problems)

    def test_missing_parent_tree_is_reported_without_creating_one(self, blank):
        page = blank.pages[0]
        set_contents(blank, page, b'/P <</MCID 0>> BDC EMC\n')
        tree = blank.open_structure_tree()
        tree.add(Name.P, page=page).add_content(page, 0)
        del tree.obj[Name.ParentTree]

        problems = tree.validate()

        assert any('missing required /ParentTree' in problem for problem in problems)
        assert Name.ParentTree not in tree.obj

    def test_empty_tree_does_not_require_parent_tree(self, blank):
        tree = blank.open_structure_tree().create()
        del tree.obj[Name.ParentTree]

        assert tree.validate() == []
        assert Name.ParentTree not in tree.obj

    def test_wrong_parent_tree_type_is_reported(self, blank):
        tree = blank.open_structure_tree().create()
        tree.obj.ParentTree = Array([])

        assert any(
            'not a number-tree dictionary' in problem for problem in tree.validate()
        )

    def test_malformed_parent_tree_is_reported(self, blank):
        tree = blank.open_structure_tree().create()
        tree.obj.ParentTree = blank.make_indirect(Dictionary(Nums=Array([0])))

        assert any('malformed /Nums' in problem for problem in tree.validate())

    def test_parent_tree_reversed_limits_are_reported(self, blank):
        tree = blank.open_structure_tree()
        owner = tree.add(Name.P)
        child = blank.make_indirect(
            Dictionary(Nums=Array([0, owner.obj]), Limits=Array([1, 0]))
        )
        tree.obj.ParentTree = blank.make_indirect(Dictionary(Kids=Array([child])))

        assert any(
            '/ParentTree' in problem
            and '/Limits are not in increasing order' in problem
            for problem in tree.validate(check_content=False)
        )

    def test_parent_tree_child_order_and_extrema_are_reported(self, blank):
        tree = blank.open_structure_tree()
        first_owner = tree.add(Name.P)
        second_owner = tree.add(Name.Span)
        first = blank.make_indirect(
            Dictionary(Nums=Array([1, first_owner.obj]), Limits=Array([0, 0]))
        )
        second = blank.make_indirect(
            Dictionary(Nums=Array([0, second_owner.obj]), Limits=Array([0, 0]))
        )
        tree.obj.ParentTree = blank.make_indirect(
            Dictionary(Kids=Array([first, second]))
        )

        problems = tree.validate(check_content=False)

        assert any('/Limits do not match' in problem for problem in problems)
        assert any('/Kids subtrees are not' in problem for problem in problems)

    def test_parent_tree_nonroot_limits_and_indirectness_are_required(self, blank):
        tree = blank.open_structure_tree()
        owner = tree.add(Name.P)
        direct_child = Dictionary(Nums=Array([0, owner.obj]))
        tree.obj.ParentTree = blank.make_indirect(
            Dictionary(Kids=Array([direct_child]))
        )

        problems = tree.validate(check_content=False)

        assert any('/Kids contains a direct node' in p for p in problems)

    def test_duplicate_claim_by_same_element_is_reported(self, blank):
        page = blank.pages[0]
        set_contents(blank, page, b'/P <</MCID 0>> BDC EMC\n')
        tree = blank.open_structure_tree()
        elem = tree.add(Name.P, page=page)
        elem.add_content(page, 0)
        elem.obj.K = Array([0, 0])

        assert any(
            'claimed more than once by the same' in problem
            for problem in tree.validate()
        )

    def test_duplicate_claim_by_different_elements_is_reported(self, blank):
        page = blank.pages[0]
        set_contents(blank, page, b'/P <</MCID 0>> BDC EMC\n')
        tree = blank.open_structure_tree()
        first = tree.add(Name.P, page=page)
        second = tree.add(Name.Span, page=page)
        first.add_content(page, 0)
        second.obj.K = Array([0])
        tree.parent_tree.entry_for_page(page)[0] = second.obj

        assert any(
            'claimed by multiple structure elements' in problem
            for problem in tree.validate()
        )

    def test_invalid_tag_and_mcid_are_reported(self, blank):
        tree = blank.open_structure_tree()
        elem = tree.add(Name.P)
        elem.obj.S = String('P')
        elem.obj.K = Array([-1])

        problems = tree.validate()
        assert any('/S that is not a name' in problem for problem in problems)
        assert any('not a non-negative integer' in problem for problem in problems)

    @pytest.mark.parametrize('mcid', [True, 1.5])
    def test_non_integer_bare_mcid_is_reported(self, blank, mcid):
        tree = blank.open_structure_tree()
        elem = tree.add(Name.P)
        elem.obj.K = Array([mcid])

        assert any(
            'marked-content identifier' in problem
            and 'not a non-negative integer' in problem
            for problem in tree.validate()
        )

    def test_malformed_root_kid_is_reported(self, blank):
        tree = blank.open_structure_tree().create()
        tree.obj.K = Array([String('not an element')])

        assert any(
            '/StructTreeRoot has a malformed /K' in problem
            for problem in tree.validate()
        )

    def test_cycle_and_repeated_element_are_reported(self, blank):
        tree = blank.open_structure_tree()
        document = tree.add(Name.Document)
        child = document.add_child(Name.P)
        document.obj.K = Array([child.obj, child.obj])
        child.obj.K = Array([document.obj])

        problems = tree.validate(check_content=False)
        assert any('appears more than once' in problem for problem in problems)
        assert any('cycle' in problem for problem in problems)

    def test_direct_structure_element_cycle_is_bounded(self, blank):
        tree = blank.open_structure_tree().create()
        direct = Dictionary(Type=Name.StructElem, S=Name.P, P=tree.obj)
        direct.K = direct
        tree.obj.K = Array([direct])
        try:
            problems = tree.validate(check_content=False)
            assert any('cannot be a parent' in problem for problem in problems)
            with pytest.raises(StructureTreeError, match='terminal child'):
                list(tree.walk())
            tree.remove()
            assert not tree.exists
        finally:
            del direct[Name.K]

    def test_direct_structure_element_without_k_is_a_readable_terminal(self, blank):
        tree = blank.open_structure_tree().create()
        direct = Dictionary(Type=Name.StructElem, S=Name.P, P=tree.obj)
        tree.obj.K = Array([direct])

        assert [elem.tag for elem in tree.walk()] == [Name.P]
        assert tree.validate(check_content=False) == []

    def test_empty_structure_element_k_array_is_reported(self, blank):
        tree = blank.open_structure_tree()
        elem = tree.add(Name.P)
        elem.obj.K = Array([])

        assert any(
            'empty /K array' in problem
            for problem in tree.validate(check_content=False)
        )

    @pytest.mark.parametrize('tree_key', [Name.ParentTree, Name.IDTree])
    def test_direct_number_or_name_tree_cycle_is_not_scheduled(self, blank, tree_key):
        tree = blank.open_structure_tree().create()
        cyclic = Dictionary()
        cyclic.Kids = Array([cyclic])
        tree.obj[tree_key] = cyclic
        try:
            problems = tree.validate(check_content=False)
            assert any(
                '/Kids contains a direct node' in problem for problem in problems
            )
            assert len(problems) < 20
        finally:
            del cyclic[Name.Kids]

    def test_page_is_inherited_from_structure_ancestor(self, blank):
        page = blank.pages[0]
        set_contents(blank, page, b'/P <</MCID 0>> BDC EMC\n')
        tree = blank.open_structure_tree()
        document = tree.add(Name.Document, page=page)
        paragraph = document.add_child(Name.P)
        paragraph.add_content(page, 0)

        assert Name.Pg not in paragraph.obj
        assert paragraph.page.obj.objgen == page.obj.objgen
        assert paragraph.content[0].page.objgen == page.obj.objgen
        assert tree.validate() == []

    def test_form_mcr_struct_parents_is_validated(self, blank):
        page = blank.pages[0]
        form = blank.make_stream(
            b'/P <</MCID 0>> BDC EMC\n',
            Type=Name.XObject,
            Subtype=Name.Form,
        )
        page.obj.Resources = Dictionary(XObject=Dictionary(Fm0=form))
        set_contents(blank, page, b'/Fm0 Do\n')
        tree = blank.open_structure_tree()
        tree.add(Name.P, page=page).add_content(page, 0, stream=form)
        assert tree.validate() == []

        del form[Name.StructParents]

        assert any(
            'Form XObject' in problem and 'has no /StructParents' in problem
            for problem in tree.validate()
        )

    def test_form_claimed_mcids_are_cross_checked(self, blank):
        page = blank.pages[0]
        form = blank.make_stream(
            b'/P <</MCID 1>> BDC EMC\n',
            Type=Name.XObject,
            Subtype=Name.Form,
        )
        page.obj.Resources = Dictionary(XObject=Dictionary(Fm0=form))
        tree = blank.open_structure_tree()
        tree.add(Name.P, page=page).add_content(page, 0, stream=form)

        problems = tree.validate()
        assert not any(
            'no structure element claims it' in problem for problem in problems
        )
        assert any(
            'Form XObject' in problem
            and 'MCID 0' in problem
            and 'does not appear' in problem
            for problem in problems
        )

    def test_resource_less_form_uses_page_properties(self, blank):
        page = blank.pages[0]
        form = blank.make_stream(
            b'/P /MC0 BDC EMC\n', Type=Name.XObject, Subtype=Name.Form
        )
        page.obj.Resources = Dictionary(
            Properties=Dictionary(MC0=Dictionary(MCID=0)),
            XObject=Dictionary(Fm0=form),
        )
        set_contents(blank, page, b'/Fm0 Do\n')
        tree = blank.open_structure_tree()
        tree.add(Name.P, page=page).add_content(page, 0, stream=form)

        assert tree.validate() == []

    def test_unused_form_resource_does_not_add_a_page_context(self):
        with Pdf.new() as pdf:
            first_page = pdf.add_blank_page()
            second_page = pdf.add_blank_page()
            form = pdf.make_stream(
                b'/P /MC0 BDC EMC\n', Type=Name.XObject, Subtype=Name.Form
            )
            first_page.obj.Resources = Dictionary(
                Properties=Dictionary(MC0=Dictionary(MCID=0)),
                XObject=Dictionary(Fm0=form),
            )
            second_page.obj.Resources = Dictionary(
                Properties=Dictionary(MC0=Dictionary(MCID=1)),
                XObject=Dictionary(Fm0=form),
            )
            set_contents(pdf, first_page, b'/Fm0 Do\n')
            tree = pdf.open_structure_tree()
            tree.add(Name.P).add_content(first_page, 0, stream=form)

            assert tree.validate() == []

    def test_nested_invoked_forms_are_validated(self, blank):
        page = blank.pages[0]
        inner = blank.make_stream(
            b'/P <</MCID 0>> BDC EMC\n', Type=Name.XObject, Subtype=Name.Form
        )
        outer = blank.make_stream(
            b'/Inner Do\n',
            Type=Name.XObject,
            Subtype=Name.Form,
            Resources=Dictionary(XObject=Dictionary(Inner=inner)),
        )
        page.obj.Resources = Dictionary(XObject=Dictionary(Outer=outer))
        set_contents(blank, page, b'/Outer Do\n')
        tree = blank.open_structure_tree()
        tree.add(Name.P, page=page).add_content(page, 0, stream=inner)

        assert tree.validate() == []

    def test_nested_resource_less_form_uses_page_resources(self, blank):
        page = blank.pages[0]
        inner = blank.make_stream(
            b'/P /MC0 BDC EMC\n', Type=Name.XObject, Subtype=Name.Form
        )
        outer = blank.make_stream(
            b'/Inner Do\n',
            Type=Name.XObject,
            Subtype=Name.Form,
            Resources=Dictionary(XObject=Dictionary(Inner=inner)),
        )
        page.obj.Resources = Dictionary(
            Properties=Dictionary(MC0=Dictionary(MCID=0)),
            XObject=Dictionary(Outer=outer),
        )
        set_contents(blank, page, b'/Outer Do\n')
        tree = blank.open_structure_tree()
        tree.add(Name.P, page=page).add_content(page, 0, stream=inner)

        assert tree.validate() == []

    def test_self_invoking_form_validation_terminates(self, blank):
        page = blank.pages[0]
        form = blank.make_stream(b'/Self Do\n', Type=Name.XObject, Subtype=Name.Form)
        form.Resources = Dictionary(XObject=Dictionary(Self=form))
        page.obj.Resources = Dictionary(XObject=Dictionary(Fm0=form))
        set_contents(blank, page, b'/Fm0 Do\n')
        tree = blank.open_structure_tree().create()

        assert isinstance(tree.validate(), list)

    def test_unclaimed_form_mcid_may_be_invoked_more_than_once(self, blank):
        page = blank.pages[0]
        form = blank.make_stream(
            b'/P <</MCID 0>> BDC EMC\n',
            Type=Name.XObject,
            Subtype=Name.Form,
        )
        page.obj.Resources = Dictionary(XObject=Dictionary(Fm0=form))
        set_contents(blank, page, b'/Fm0 Do /Fm0 Do\n')
        tree = blank.open_structure_tree().create()

        assert tree.validate() == []

    def test_structural_page_scope_may_invoke_unclaimed_form_mcid(self, blank):
        page = blank.pages[0]
        form = blank.make_stream(
            b'/P <</MCID 0>> BDC EMC\n',
            Type=Name.XObject,
            Subtype=Name.Form,
        )
        page.obj.Resources = Dictionary(XObject=Dictionary(Fm0=form))
        set_contents(
            blank,
            page,
            b'/P <</MCID 0>> BDC /Fm0 Do EMC\n',
        )
        tree = blank.open_structure_tree()
        tree.add(Name.P, page=page).add_content(page, 0)

        assert tree.validate() == []

    @pytest.mark.parametrize(
        'content',
        [
            b'/Figure <</MCID 0>> BDC /Fm0 Do /Fm0 Do EMC\n',
            b'/Figure <</MCID 0>> BDC /Fm0 Do EMC /Fm0 Do\n',
        ],
    )
    def test_incomplete_page_wrapper_form_association_is_reported(self, blank, content):
        page = blank.pages[0]
        form = blank.make_stream(b'', Type=Name.XObject, Subtype=Name.Form)
        page.obj.Resources = Dictionary(XObject=Dictionary(Fm0=form))
        set_contents(blank, page, content)
        tree = blank.open_structure_tree()
        tree.add(Name.Figure, page=page).add_content(page, 0)

        assert any(
            'not each enclosed by a distinct claimed' in problem
            for problem in tree.validate()
        )

    def test_page_wrapper_is_propagated_through_nested_form_invocations(self, blank):
        page = blank.pages[0]
        inner = blank.make_stream(b'', Type=Name.XObject, Subtype=Name.Form)
        outer = blank.make_stream(
            b'/Inner Do /Inner Do\n',
            Type=Name.XObject,
            Subtype=Name.Form,
            Resources=Dictionary(XObject=Dictionary(Inner=inner)),
        )
        page.obj.Resources = Dictionary(XObject=Dictionary(Outer=outer))
        set_contents(
            blank,
            page,
            b'/Figure <</MCID 0>> BDC /Outer Do EMC\n',
        )
        tree = blank.open_structure_tree()
        tree.add(Name.Figure, page=page).add_content(page, 0)

        assert any(
            'not each enclosed by a distinct claimed' in problem
            for problem in tree.validate()
        )

    def test_same_page_repeated_form_objr_needs_one_claim(self, blank):
        page = blank.pages[0]
        form = blank.make_stream(b'', Type=Name.XObject, Subtype=Name.Form)
        page.obj.Resources = Dictionary(XObject=Dictionary(Fm0=form))
        set_contents(blank, page, b'/Fm0 Do /Fm0 Do\n')
        tree = blank.open_structure_tree()
        tree.add(Name.Figure, page=page).add_object(form, page)

        assert tree.validate() == []

    def test_form_objr_requires_one_claim_per_observed_page(self):
        with Pdf.new() as pdf:
            first_page = pdf.add_blank_page()
            second_page = pdf.add_blank_page()
            form = pdf.make_stream(b'', Type=Name.XObject, Subtype=Name.Form)
            for page in (first_page, second_page):
                page.obj.Resources = Dictionary(XObject=Dictionary(Fm0=form))
                set_contents(pdf, page, b'/Fm0 Do\n')
            tree = pdf.open_structure_tree()
            elem = tree.add(Name.Figure)
            elem.add_object(form, first_page)

            assert any(
                'without a matching /OBJR claim' in problem
                for problem in tree.validate()
            )

            elem.add_object(form, second_page)
            assert tree.validate() == []

    def test_shared_resource_less_form_cannot_use_internal_mcids(self):
        with Pdf.new() as pdf:
            first_page = pdf.add_blank_page()
            second_page = pdf.add_blank_page()
            form = pdf.make_stream(
                b'/P /MC0 BDC EMC\n', Type=Name.XObject, Subtype=Name.Form
            )
            first_page.obj.Resources = Dictionary(
                Properties=Dictionary(MC0=Dictionary(MCID=0)),
                XObject=Dictionary(Fm0=form),
            )
            second_page.obj.Resources = Dictionary(
                Properties=Dictionary(MC0=Dictionary(MCID=1)),
                XObject=Dictionary(Fm0=form),
            )
            tree = pdf.open_structure_tree()
            elem = tree.add(Name.P)
            elem.add_content(first_page, 0, stream=form)
            elem.obj.K.append(
                Dictionary(
                    Type=Name.MCR,
                    Pg=second_page.obj,
                    Stm=form,
                    MCID=1,
                )
            )
            entry = tree.parent_tree.entry_for_page(form)
            assert entry is not None
            entry.append(elem.obj)
            set_contents(pdf, first_page, b'/Fm0 Do\n')
            set_contents(pdf, second_page, b'/Fm0 Do\n')

            assert any(
                'contains structural marked content' in problem
                and 'invoked more than once' in problem
                for problem in tree.validate()
            )

    def test_shared_form_with_own_resources_cannot_use_internal_mcid(self):
        with Pdf.new() as pdf:
            first_page = pdf.add_blank_page()
            second_page = pdf.add_blank_page()
            form = pdf.make_stream(
                b'/P <</MCID 0>> BDC EMC\n',
                Type=Name.XObject,
                Subtype=Name.Form,
                Resources=Dictionary(),
            )
            for page in (first_page, second_page):
                page.obj.Resources = Dictionary(XObject=Dictionary(Fm0=form))
            tree = pdf.open_structure_tree()
            tree.add(Name.P).add_content(first_page, 0, stream=form)
            for page in (first_page, second_page):
                set_contents(pdf, page, b'/Fm0 Do\n')

            assert any(
                'contains structural marked content' in problem
                and 'invoked more than once' in problem
                for problem in tree.validate()
            )

    def test_shared_form_with_own_resources_rejects_claims_per_page(self):
        with Pdf.new() as pdf:
            first_page = pdf.add_blank_page()
            second_page = pdf.add_blank_page()
            form = pdf.make_stream(
                b'/P <</MCID 0>> BDC EMC\n',
                Type=Name.XObject,
                Subtype=Name.Form,
                Resources=Dictionary(),
            )
            for page in (first_page, second_page):
                page.obj.Resources = Dictionary(XObject=Dictionary(Fm0=form))
            tree = pdf.open_structure_tree()
            elem = tree.add(Name.P)
            elem.add_content(first_page, 0, stream=form)
            elem.obj.K.append(
                Dictionary(
                    Type=Name.MCR,
                    Pg=second_page.obj,
                    Stm=form,
                    MCID=0,
                )
            )
            for page in (first_page, second_page):
                set_contents(pdf, page, b'/Fm0 Do\n')

            problems = tree.validate()
            assert any('invoked more than once' in problem for problem in problems)
            assert any('claimed more than once' in problem for problem in problems)

    def test_object_reference_struct_parent_is_validated(self, blank):
        page = blank.pages[0]
        annotation = blank.make_indirect(Dictionary(Type=Name.Annot))
        page.obj.Annots = Array([annotation])
        tree = blank.open_structure_tree()
        tree.add(Name.Link, page=page).add_object(annotation, page)
        assert tree.validate() == []

        del annotation[Name.StructParent]

        assert any(
            'referenced by /OBJR but has no /StructParent' in problem
            for problem in tree.validate()
        )

    def test_stale_parent_tree_array_entry_is_reported(self, blank):
        page = blank.pages[0]
        set_contents(blank, page, b'/P <</MCID 0>> BDC EMC\n')
        tree = blank.open_structure_tree()
        elem = tree.add(Name.P, page=page)
        elem.add_content(page, 0)
        tree.parent_tree.entry_for_page(page).append(elem.obj)

        assert any(
            'has no matching structure element /K claim' in problem
            for problem in tree.validate()
        )

    def test_malformed_content_stream_is_reported(self, blank):
        page = blank.pages[0]
        page.obj.Contents = Dictionary()
        tree = blank.open_structure_tree().create()

        assert any('could not be parsed' in problem for problem in tree.validate())

    def test_invalid_stream_mcid_is_reported(self, blank):
        page = blank.pages[0]
        set_contents(blank, page, b'/P <</MCID -1>> BDC EMC\n')
        tree = blank.open_structure_tree().create()

        assert any(
            'content stream has an /MCID that is not a non-negative integer' in problem
            for problem in tree.validate()
        )

    def test_stream_mcids_must_start_at_zero(self, blank):
        page = blank.pages[0]
        set_contents(blank, page, b'/P <</MCID 5>> BDC EMC\n')
        tree = blank.open_structure_tree().create()

        assert any(
            'marked content identifiers must start at 0' in problem
            for problem in tree.validate()
        )

    def test_object_cannot_have_both_structural_parent_keys(self, blank):
        page = blank.pages[0]
        form = blank.make_stream(
            b'', Type=Name.XObject, Subtype=Name.Form, StructParents=0
        )
        form.StructParent = 1
        annotation = blank.make_indirect(Dictionary(Type=Name.Annot, StructParent=0))
        page.obj.Resources = Dictionary(XObject=Dictionary(Fm0=form))
        page.obj.Annots = Array([annotation])
        tree = blank.open_structure_tree()
        owner = tree.add(Name.Figure, page=page)
        tree.parent_tree[0] = blank.make_indirect(Array([]))
        tree.parent_tree[1] = owner.obj

        problems = tree.validate()

        assert any('both /StructParent and /StructParents' in p for p in problems)
        assert any('key 0 is shared by multiple objects' in p for p in problems)

    def test_reachable_form_struct_parent_is_reverse_validated(self, blank):
        page = blank.pages[0]
        form = blank.make_stream(b'', Type=Name.XObject, Subtype=Name.Form)
        page.obj.Resources = Dictionary(XObject=Dictionary(Fm0=form))
        annotation = blank.make_indirect(Dictionary(Type=Name.Annot))
        page.obj.Annots = Array([annotation])
        tree = blank.open_structure_tree()
        tree.add(Name.Link, page=page).add_object(annotation, page)
        form.StructParent = annotation.StructParent

        problems = tree.validate(check_content=False)

        assert any(
            'Form XObject' in problem
            and 'no structure element /OBJR claims it' in problem
            for problem in problems
        )
        assert any('key 0 is shared by multiple objects' in p for p in problems)

    def test_annotation_must_not_appear_on_distinct_pages(self):
        with Pdf.new() as pdf:
            first_page = pdf.add_blank_page()
            second_page = pdf.add_blank_page()
            annotation = pdf.make_indirect(Dictionary(Type=Name.Annot))
            first_page.obj.Annots = Array([annotation])
            second_page.obj.Annots = Array([annotation])
            tree = pdf.open_structure_tree()
            elem = tree.add(Name.Link)
            elem.obj.K = Array(
                [Dictionary(Type=Name.OBJR, Obj=annotation, Pg=first_page.obj)]
            )

            assert any(
                'appears in the /Annots arrays of more than one page' in problem
                for problem in tree.validate()
            )

    def test_add_object_rejects_an_annotation_shared_by_pages(self, blank):
        first_page = blank.pages[0]
        second_page = blank.add_blank_page()
        annotation = blank.make_indirect(Dictionary(Type=Name.Annot))
        first_page.obj.Annots = Array([annotation])
        tree = blank.open_structure_tree()
        elem = tree.add(Name.Link)
        elem.add_object(annotation, first_page)
        second_page.obj.Annots = Array([annotation])

        with pytest.raises(StructureTreeError, match='exactly its claimed page'):
            elem.add_object(annotation, second_page)

        assert len(elem.obj.K) == 1

    def test_duplicate_objr_on_same_page_is_reported(self, blank):
        page = blank.pages[0]
        annotation = blank.make_indirect(Dictionary(Type=Name.Annot))
        page.obj.Annots = Array([annotation])
        tree = blank.open_structure_tree()
        elem = tree.add(Name.Link)
        elem.add_object(annotation, page)
        elem.obj.K.append(Dictionary(Type=Name.OBJR, Obj=annotation, Pg=page.obj))

        assert any(
            'referenced more than once' in problem and 'on the same page' in problem
            for problem in tree.validate()
        )

    def test_objr_from_different_elements_is_reported(self):
        with Pdf.new() as pdf:
            first_page = pdf.add_blank_page()
            second_page = pdf.add_blank_page()
            annotation = pdf.make_indirect(Dictionary(Type=Name.Annot))
            first_page.obj.Annots = Array([annotation])
            tree = pdf.open_structure_tree()
            first = tree.add(Name.Link)
            second = tree.add(Name.Link)
            first.add_object(annotation, first_page)
            second.obj.K = Array(
                [Dictionary(Type=Name.OBJR, Obj=annotation, Pg=second_page.obj)]
            )

            assert any(
                'claimed by multiple structure elements' in problem
                for problem in tree.validate()
            )

    @pytest.mark.parametrize(
        ('content', 'message'),
        [
            (b'/P <</MCID 0>> BDC\n', 'unclosed marked-content'),
            (b'EMC\n', 'EMC without a matching'),
            (b'42 <</MCID 0>> BDC EMC\n', 'BDC tag that is not a name'),
            (b'/P (bad) BDC EMC\n', 'BDC property list that is not'),
            (b'Q\n', 'Q without a matching q'),
            (b'BT Q ET\n', 'Q while BT is the active content scope'),
            (b'EX\n', 'EX without a matching BX'),
        ],
    )
    def test_malformed_content_syntax_or_scope_is_reported(
        self, blank, content, message
    ):
        set_contents(blank, blank.pages[0], content)
        tree = blank.open_structure_tree().create()

        assert any(message in problem for problem in tree.validate())

    def test_nested_structural_marked_content_on_page_is_reported(self, blank):
        page = blank.pages[0]
        set_contents(
            blank,
            page,
            b'/P <</MCID 0>> BDC /Span <</MCID 1>> BDC EMC EMC\n',
        )
        tree = blank.open_structure_tree()
        elem = tree.add(Name.P, page=page)
        elem.add_content(page, 0)
        elem.obj.K.append(1)
        entry = tree.parent_tree.entry_for_page(page)
        assert entry is not None
        entry.append(elem.obj)

        assert any(
            'nests an MCID-bearing marked-content sequence' in problem
            for problem in tree.validate()
        )

    def test_nested_structural_marked_content_in_form_is_reported(self, blank):
        page = blank.pages[0]
        form = blank.make_stream(
            b'/P <</MCID 0>> BDC /Span <</MCID 1>> BDC EMC EMC\n',
            Type=Name.XObject,
            Subtype=Name.Form,
        )
        page.obj.Resources = Dictionary(XObject=Dictionary(Fm0=form))
        tree = blank.open_structure_tree()
        elem = tree.add(Name.P, page=page)
        elem.add_content(page, 0, stream=form)
        elem.obj.K.append(Dictionary(Type=Name.MCR, Pg=page.obj, Stm=form, MCID=1))
        entry = tree.parent_tree.entry_for_page(form)
        assert entry is not None
        entry.append(elem.obj)

        assert any(
            'Form XObject' in problem
            and 'nests an MCID-bearing marked-content sequence' in problem
            for problem in tree.validate()
        )

    def test_structural_content_may_nest_in_nonstructural_content(self, blank):
        page = blank.pages[0]
        set_contents(
            blank,
            page,
            b'/OC BMC /P <</MCID 0>> BDC EMC EMC\n',
        )
        tree = blank.open_structure_tree()
        tree.add(Name.P, page=page).add_content(page, 0)

        assert tree.validate() == []

    @pytest.mark.parametrize(
        'content',
        [
            b'/Artifact BMC /P <</MCID 0>> BDC EMC EMC\n',
            b'/P <</MCID 0>> BDC /Artifact BMC EMC EMC\n',
        ],
    )
    def test_artifact_and_structural_content_may_be_nested(self, blank, content):
        page = blank.pages[0]
        set_contents(blank, page, content)
        tree = blank.open_structure_tree()
        tree.add(Name.P, page=page).add_content(page, 0)

        assert tree.validate() == []

    def test_unclaimed_artifact_mcid_is_nonstructural(self, blank):
        set_contents(blank, blank.pages[0], b'/Artifact <</MCID 0>> BDC EMC\n')
        tree = blank.open_structure_tree().create()

        assert tree.validate() == []

    @pytest.mark.parametrize(
        'content',
        [
            b'BT /P <</MCID 0>> BDC (x) Tj ET EMC\n',
            b'/P <</MCID 0>> BDC BT (x) Tj EMC ET\n',
            b'q /P <</MCID 0>> BDC Q EMC\n',
            b'/P <</MCID 0>> BDC q EMC Q\n',
            b'BX /P <</MCID 0>> BDC EX EMC\n',
            b'/P <</MCID 0>> BDC BX EMC EX\n',
        ],
    )
    def test_marked_content_cannot_cross_page_content_scopes(self, blank, content):
        page = blank.pages[0]
        set_contents(blank, page, content)
        tree = blank.open_structure_tree()
        tree.add(Name.P, page=page).add_content(page, 0)

        assert any(
            'marked-content sequence that crosses' in problem
            for problem in tree.validate()
        )

    def test_marked_content_cannot_cross_form_text_objects(self, blank):
        page = blank.pages[0]
        form = blank.make_stream(
            b'BT /P <</MCID 0>> BDC (x) Tj ET EMC\n',
            Type=Name.XObject,
            Subtype=Name.Form,
        )
        page.obj.Resources = Dictionary(XObject=Dictionary(Fm0=form))
        tree = blank.open_structure_tree()
        tree.add(Name.P, page=page).add_content(page, 0, stream=form)

        assert any(
            'Form XObject' in problem
            and 'marked-content sequence that crosses' in problem
            for problem in tree.validate()
        )

    def test_marked_content_may_be_inside_a_compatibility_section(self, blank):
        page = blank.pages[0]
        set_contents(blank, page, b'BX /P <</MCID 0>> BDC EMC EX\n')
        tree = blank.open_structure_tree()
        tree.add(Name.P, page=page).add_content(page, 0)

        assert tree.validate() == []

    def test_graphics_and_compatibility_scopes_balance_when_nested(self, blank):
        set_contents(blank, blank.pages[0], b'q BX EX Q\n')

        assert blank.open_structure_tree().create().validate() == []

    def test_marked_content_boundary_inside_page_path_is_reported(self, blank):
        page = blank.pages[0]
        set_contents(
            blank,
            page,
            b'0 0 m /P <</MCID 0>> BDC 10 10 l EMC S\n',
        )
        tree = blank.open_structure_tree()
        tree.add(Name.P, page=page).add_content(page, 0)

        assert any(
            'marked-content boundary inside a path object' in problem
            for problem in tree.validate()
        )

    def test_marked_content_boundary_inside_form_path_is_reported(self, blank):
        page = blank.pages[0]
        form = blank.make_stream(
            b'0 0 m /P <</MCID 0>> BDC 10 10 l EMC S\n',
            Type=Name.XObject,
            Subtype=Name.Form,
        )
        page.obj.Resources = Dictionary(XObject=Dictionary(Fm0=form))
        tree = blank.open_structure_tree()
        tree.add(Name.P, page=page).add_content(page, 0, stream=form)

        assert any(
            'Form XObject' in problem
            and 'marked-content boundary inside a path object' in problem
            for problem in tree.validate()
        )

    def test_unclosed_path_is_reported(self, blank):
        set_contents(blank, blank.pages[0], b'0 0 m 10 10 l\n')
        tree = blank.open_structure_tree().create()

        assert any('unclosed path object' in problem for problem in tree.validate())

    def test_structural_scope_cannot_invoke_structural_xobject(self, blank):
        page = blank.pages[0]
        form = blank.make_stream(b'', Type=Name.XObject, Subtype=Name.Form)
        page.obj.Resources = Dictionary(XObject=Dictionary(Fm0=form))
        set_contents(
            blank,
            page,
            b'/P <</MCID 0>> BDC /Fm0 Do EMC\n',
        )
        tree = blank.open_structure_tree()
        tree.add(Name.P, page=page).add_content(page, 0)
        tree.add(Name.Figure, page=page).add_object(form, page)

        assert any(
            'invokes a structural object from inside an MCID-bearing' in problem
            for problem in tree.validate()
        )

    def test_structural_scope_cannot_invoke_structural_form_mcid(self, blank):
        page = blank.pages[0]
        form = blank.make_stream(
            b'/P <</MCID 0>> BDC EMC\n',
            Type=Name.XObject,
            Subtype=Name.Form,
        )
        page.obj.Resources = Dictionary(XObject=Dictionary(Fm0=form))
        set_contents(blank, page, b'/P <</MCID 0>> BDC /Fm0 Do EMC\n')
        tree = blank.open_structure_tree()
        tree.add(Name.P).add_content(page, 0)
        tree.add(Name.P).add_content(page, 0, stream=form)

        assert any(
            'invokes a structural object from inside an MCID-bearing' in problem
            for problem in tree.validate()
        )

    def test_structural_scope_detects_structural_form_through_wrapper(self, blank):
        page = blank.pages[0]
        inner = blank.make_stream(
            b'/P <</MCID 0>> BDC EMC\n',
            Type=Name.XObject,
            Subtype=Name.Form,
        )
        outer = blank.make_stream(
            b'/Inner Do\n',
            Type=Name.XObject,
            Subtype=Name.Form,
            Resources=Dictionary(XObject=Dictionary(Inner=inner)),
        )
        page.obj.Resources = Dictionary(XObject=Dictionary(Outer=outer))
        set_contents(blank, page, b'/P <</MCID 0>> BDC /Outer Do EMC\n')
        tree = blank.open_structure_tree()
        tree.add(Name.P).add_content(page, 0)
        tree.add(Name.P).add_content(page, 0, stream=inner)

        assert any(
            'invokes a structural object from inside an MCID-bearing' in problem
            for problem in tree.validate()
        )

    def test_element_id_requires_matching_id_tree_entry(self, blank):
        tree = blank.open_structure_tree()
        elem = tree.add(Name.P)
        elem.obj.ID = String('paragraph')

        problems = tree.validate(check_content=False)

        assert any('missing /IDTree required' in problem for problem in problems)

    def test_element_id_and_id_tree_validate_cleanly(self, blank):
        tree = blank.open_structure_tree()
        elem = tree.add(Name.P)
        elem.element_id = 'paragraph'

        assert tree.validate(check_content=False) == []

    def test_duplicate_element_ids_are_reported(self, blank):
        tree = blank.open_structure_tree()
        first = tree.add(Name.P)
        second = tree.add(Name.Span)
        first.element_id = 'paragraph'
        second.obj.ID = String('paragraph')
        NameTree(tree.obj.IDTree)['paragraph'] = second.obj

        problems = tree.validate(check_content=False)

        assert any(
            'identifier' in problem and 'not unique' in problem for problem in problems
        )

    def test_mismatched_id_tree_entry_is_reported(self, blank):
        tree = blank.open_structure_tree()
        first = tree.add(Name.P)
        second = tree.add(Name.Span)
        first.element_id = 'paragraph'
        NameTree(tree.obj.IDTree)['paragraph'] = second.obj

        problems = tree.validate(check_content=False)

        assert any(
            '/IDTree entry' in problem and 'wrong element' in problem
            for problem in problems
        )

    def test_malformed_id_tree_and_id_value_are_reported(self, blank):
        tree = blank.open_structure_tree()
        elem = tree.add(Name.P)
        elem.obj.ID = 42
        tree.obj.IDTree = Array([])

        problems = tree.validate(check_content=False)

        assert any('/ID that is not a string' in problem for problem in problems)
        assert any('/IDTree is not a name-tree' in problem for problem in problems)

    def test_id_tree_order_uses_raw_pdf_string_bytes(self, blank):
        tree = blank.open_structure_tree()
        first = tree.add(Name.P)
        second = tree.add(Name.P)
        first.obj.ID = String('ä')
        second.obj.ID = String('€')
        tree.obj.IDTree = blank.make_indirect(
            Dictionary(Names=Array([String('ä'), first.obj, String('€'), second.obj]))
        )

        assert any(
            'keys are not in strictly increasing order' in problem
            for problem in tree.validate(check_content=False)
        )

    def test_id_tree_raw_byte_order_is_not_falsely_rejected(self, blank):
        tree = blank.open_structure_tree()
        first = tree.add(Name.P)
        second = tree.add(Name.P)
        first.obj.ID = String('€')
        second.obj.ID = String('ä')
        tree.obj.IDTree = blank.make_indirect(
            Dictionary(Names=Array([String('€'), first.obj, String('ä'), second.obj]))
        )

        assert tree.validate(check_content=False) == []

    def test_id_tree_reversed_limits_are_reported(self, blank):
        tree = blank.open_structure_tree()
        elem = tree.add(Name.P)
        elem.obj.ID = String('a')
        child = blank.make_indirect(
            Dictionary(
                Names=Array([String('a'), elem.obj]),
                Limits=Array([String('z'), String('a')]),
            )
        )
        tree.obj.IDTree = blank.make_indirect(Dictionary(Kids=Array([child])))

        assert any(
            '/IDTree' in problem and '/Limits are not in increasing order' in problem
            for problem in tree.validate(check_content=False)
        )

    def test_id_tree_child_order_and_extrema_are_reported(self, blank):
        tree = blank.open_structure_tree()
        first_elem = tree.add(Name.P)
        second_elem = tree.add(Name.Span)
        first_elem.obj.ID = String('b')
        second_elem.obj.ID = String('a')
        first = blank.make_indirect(
            Dictionary(
                Names=Array([String('b'), first_elem.obj]),
                Limits=Array([String('a'), String('a')]),
            )
        )
        second = blank.make_indirect(
            Dictionary(
                Names=Array([String('a'), second_elem.obj]),
                Limits=Array([String('a'), String('a')]),
            )
        )
        tree.obj.IDTree = blank.make_indirect(Dictionary(Kids=Array([first, second])))

        problems = tree.validate(check_content=False)

        assert any('/Limits do not match' in problem for problem in problems)
        assert any('/Kids subtrees are not' in problem for problem in problems)

    def test_id_tree_nonroot_limits_and_indirectness_are_required(self, blank):
        tree = blank.open_structure_tree()
        elem = tree.add(Name.P)
        elem.obj.ID = String('a')
        direct_child = Dictionary(Names=Array([String('a'), elem.obj]))
        tree.obj.IDTree = blank.make_indirect(Dictionary(Kids=Array([direct_child])))

        problems = tree.validate(check_content=False)

        assert any('/Kids contains a direct node' in p for p in problems)

    def test_stale_id_tree_entry_is_reported(self, blank):
        tree = blank.open_structure_tree()
        elem = tree.add(Name.P)
        tree.obj.IDTree = NameTree.new(blank).obj
        NameTree(tree.obj.IDTree)['stale'] = elem.obj

        assert any(
            'has no matching reachable structure element /ID' in problem
            for problem in tree.validate(check_content=False)
        )

    def test_invalid_role_map_and_attributes_are_reported(self, blank):
        tree = blank.open_structure_tree()
        elem = tree.add(Name.P)
        tree.obj.RoleMap = Dictionary(Custom=String('P'))
        elem.obj.A = String('not attributes')

        problems = tree.validate(check_content=False)

        assert any('/RoleMap values must be names' in problem for problem in problems)
        assert any('/A that is not an attribute' in problem for problem in problems)

    def test_class_map_class_names_and_revisions_validate_cleanly(self, blank):
        tree = blank.open_structure_tree()
        elem = tree.add(Name.P)
        stream_attribute = blank.make_stream(b'', O=Name.Table)
        tree.obj.ClassMap = Dictionary(
            Direct=Dictionary(O=Name.Layout),
            Multiple=Array([Dictionary(O=Name.List), stream_attribute]),
        )
        elem.obj.C = Array([Name.Direct, 0, Name.Multiple, 2])
        elem.obj.R = 3

        assert tree.validate(check_content=False) == []

    def test_missing_class_map_name_is_a_valid_empty_class(self, blank):
        tree = blank.open_structure_tree()
        elem = tree.add(Name.P)
        elem.obj.C = Name.NotInClassMap

        assert tree.validate(check_content=False) == []

    def test_class_map_must_be_a_dictionary(self, blank):
        tree = blank.open_structure_tree().create()
        tree.obj.ClassMap = String('bad')

        assert any(
            '/ClassMap is not a dictionary' in problem
            for problem in tree.validate(check_content=False)
        )

    @pytest.mark.parametrize(
        'value',
        [
            Dictionary(),
            Dictionary(O=String('Layout')),
            Array([]),
            Array([Dictionary(O=Name.Layout), 0]),
            Array([Name.Layout]),
            String('bad'),
        ],
    )
    def test_malformed_class_map_values_are_reported(self, blank, value):
        tree = blank.open_structure_tree().create()
        tree.obj.ClassMap = Dictionary(Bad=value)

        assert any(
            '/ClassMap entry' in problem and 'attribute object' in problem
            for problem in tree.validate(check_content=False)
        )

    def test_foreign_class_map_attribute_is_reported(self):
        with Pdf.new() as first, Pdf.new() as second:
            first.add_blank_page()
            second.add_blank_page()
            tree = first.open_structure_tree().create()
            foreign = second.make_indirect(Dictionary(O=Name.Layout))
            tree.obj.ClassMap = Dictionary(Bad=Array([foreign]))

            assert any(
                '/ClassMap entry' in problem and 'another PDF' in problem
                for problem in tree.validate(check_content=False)
            )

    @pytest.mark.parametrize(
        'value',
        [
            String('Bad'),
            1,
            Array([]),
            Array([1]),
            Array([Name.First, -1]),
            Array([Name.First, True]),
            Array([Name.First, 0, 1]),
            Array([None]),
        ],
    )
    def test_malformed_element_class_names_are_reported(self, blank, value):
        tree = blank.open_structure_tree()
        elem = tree.add(Name.P)
        elem.obj.C = value

        assert any('/C class-name' in p for p in tree.validate(check_content=False))

    @pytest.mark.parametrize('value', [True, -1, 1.5, String('1')])
    def test_malformed_element_revision_is_reported(self, blank, value):
        tree = blank.open_structure_tree()
        elem = tree.add(Name.P)
        elem.obj.R = value

        assert any(
            '/R that is not a non-negative integer' in problem
            for problem in tree.validate(check_content=False)
        )

    def test_role_map_cycle_is_core_valid(self, blank):
        tree = blank.open_structure_tree()
        tree.add(Name.CustomA)
        tree.obj.RoleMap = Dictionary(CustomA=Name.CustomB, CustomB=Name.CustomA)

        assert tree.validate(check_content=False) == []

    def test_role_map_chain_need_not_reach_a_standard_type(self, blank):
        tree = blank.open_structure_tree()
        tree.add(Name.CustomA)
        tree.obj.RoleMap = Dictionary(CustomA=Name.CustomB)

        assert tree.validate(check_content=False) == []

    def test_unmapped_nonstandard_structure_type_is_core_valid(self, blank):
        tree = blank.open_structure_tree()
        tree.add(Name.Custom)

        assert tree.validate(check_content=False) == []

    def test_namespace_structure_type_does_not_use_default_role_map(self, blank):
        tree = blank.open_structure_tree()
        elem = tree.add(Name.Custom)
        elem.namespace = blank.make_indirect(
            Dictionary(Type=Name.Namespace, NS=String('urn:example'))
        )

        assert tree.validate(check_content=False) == []

    def test_namespace_without_optional_type_validates_cleanly(self, blank):
        tree = blank.open_structure_tree()
        elem = tree.add(Name.Custom)
        elem.namespace = blank.make_indirect(Dictionary(NS=String('urn:example')))

        assert tree.validate(check_content=False) == []

    def test_element_namespace_requires_root_namespace_membership(self, blank):
        tree = blank.open_structure_tree()
        elem = tree.add(Name.Custom)
        namespace = blank.make_indirect(
            Dictionary(Type=Name.Namespace, NS=String('urn:example'))
        )
        elem.obj.NS = namespace

        problems = tree.validate(check_content=False)

        assert any('has no /Namespaces array' in problem for problem in problems)

        other = blank.make_indirect(
            Dictionary(Type=Name.Namespace, NS=String('urn:other'))
        )
        tree.obj.Namespaces = Array([other])
        problems = tree.validate(check_content=False)
        assert any('not registered' in problem for problem in problems)

    def test_malformed_namespace_registry_and_entries_are_reported(self, blank):
        tree = blank.open_structure_tree()
        elem = tree.add(Name.Custom)
        namespace = blank.make_indirect(
            Dictionary(Type=Name.Namespace, NS=String('urn:example'))
        )
        elem.obj.NS = namespace
        tree.obj.Namespaces = String('not an array')

        assert any(
            '/Namespaces is not an array' in problem
            for problem in tree.validate(check_content=False)
        )

        tree.obj.Namespaces = Array([String('bad')])
        assert any(
            'is not a namespace dictionary' in problem
            for problem in tree.validate(check_content=False)
        )

    def test_invalid_element_namespace_values_are_reported(self, blank):
        tree = blank.open_structure_tree()
        scalar = tree.add(Name.Custom)
        direct = tree.add(Name.Custom)
        wrong_type = tree.add(Name.Custom)
        missing_name = tree.add(Name.Custom)
        scalar.obj.NS = 42
        direct.obj.NS = Dictionary(NS=String('urn:direct'))
        wrong_type.obj.NS = blank.make_indirect(
            Dictionary(Type=Name.Foo, NS=String('urn:wrong'))
        )
        missing_name.obj.NS = blank.make_indirect(Dictionary(Type=Name.Namespace))
        tree.obj.Namespaces = Array([])

        problems = tree.validate(check_content=False)

        assert any('/NS that is not a namespace dictionary' in p for p in problems)
        assert any('direct /NS' in p for p in problems)
        assert any('/NS dictionary with the wrong /Type' in p for p in problems)
        assert any('/NS dictionary with no string /NS' in p for p in problems)

    def test_duplicate_namespace_names_and_objects_are_core_valid(self, blank):
        tree = blank.open_structure_tree()
        first = blank.make_indirect(
            Dictionary(Type=Name.Namespace, NS=String('urn:example'))
        )
        second = blank.make_indirect(Dictionary(NS=String('urn:example')))
        elem = tree.add(Name.Custom)
        elem.obj.NS = first
        tree.obj.Namespaces = Array([first, first, second])

        assert tree.validate(check_content=False) == []

    def test_foreign_namespace_references_are_reported(self):
        with Pdf.new() as first, Pdf.new() as second:
            first.add_blank_page()
            second.add_blank_page()
            tree = first.open_structure_tree().create()
            namespace = second.make_indirect(
                Dictionary(Type=Name.Namespace, NS=String('urn:foreign'))
            )
            elem = Dictionary(
                Type=Name.StructElem,
                S=Name.Custom,
                P=tree.obj,
                NS=namespace,
            )
            tree.obj.K = Array([elem])
            tree.obj.Namespaces = Array([namespace])

            problems = tree.validate(check_content=False)

            assert any('belongs to another PDF' in problem for problem in problems)

    def test_foreign_mcr_stream_and_owner_are_reported(self):
        with Pdf.new() as first, Pdf.new() as second:
            page = first.add_blank_page()
            second.add_blank_page()
            foreign_stream = second.make_stream(
                b'', Type=Name.XObject, Subtype=Name.Form
            )
            foreign_owner = second.make_indirect(Dictionary())
            tree = first.open_structure_tree()
            elem = tree.add(Name.P, page=page)
            elem.obj.K = Array(
                [
                    Dictionary(
                        Type=Name.MCR,
                        MCID=0,
                        Pg=page.obj,
                        Stm=foreign_stream,
                        StmOwn=foreign_owner,
                    )
                ]
            )

            problems = tree.validate(check_content=False)

            assert any('/Stm that belongs to another PDF' in p for p in problems)
            assert any('/StmOwn that belongs to another PDF' in p for p in problems)

    def test_foreign_objr_referent_is_reported(self):
        with Pdf.new() as first, Pdf.new() as second:
            page = first.add_blank_page()
            second.add_blank_page()
            referent = second.make_indirect(Dictionary(Type=Name.Annot))
            tree = first.open_structure_tree()
            elem = tree.add(Name.Link, page=page)
            elem.obj.K = Array([Dictionary(Type=Name.OBJR, Obj=referent, Pg=page.obj)])

            assert any(
                '/Obj that belongs to another PDF' in problem
                for problem in tree.validate(check_content=False)
            )

    def test_foreign_root_and_child_structure_elements_are_reported(self):
        with Pdf.new() as first, Pdf.new() as second:
            first.add_blank_page()
            second.add_blank_page()
            foreign_tree = second.open_structure_tree()
            foreign_root = foreign_tree.add(Name.Document)
            foreign_child = foreign_root.add_child(Name.P)

            tree = first.open_structure_tree().create()
            tree.obj.K = Array([foreign_root.obj])
            assert any(
                '/K contains a structure element that belongs to another PDF' in problem
                for problem in tree.validate(check_content=False)
            )

            tree.obj.K = Array([])
            parent = tree.add(Name.Document)
            parent.obj.K = Array([foreign_child.obj])
            assert any(
                'child structure element that belongs to another PDF' in problem
                for problem in tree.validate(check_content=False)
            )

    def test_foreign_explicit_page_is_reported(self):
        with Pdf.new() as first, Pdf.new() as second:
            first.add_blank_page()
            foreign_page = second.add_blank_page()
            tree = first.open_structure_tree().create()
            elem = Dictionary(
                Type=Name.StructElem,
                S=Name.P,
                P=tree.obj,
                Pg=foreign_page.obj,
            )
            tree.obj.K = Array([elem])

            assert any(
                '/Pg that belongs to another PDF' in problem
                for problem in tree.validate(check_content=False)
            )

    def test_foreign_parent_and_id_tree_roots_are_reported(self):
        with Pdf.new() as first, Pdf.new() as second:
            first.add_blank_page()
            second.add_blank_page()
            parent_tree = second.make_indirect(Dictionary(Nums=Array([])))
            id_tree = second.make_indirect(Dictionary(Names=Array([])))
            first.Root.StructTreeRoot = Dictionary(
                Type=Name.StructTreeRoot,
                K=Array([]),
                ParentTree=parent_tree,
                ParentTreeNextKey=0,
                IDTree=id_tree,
            )
            tree = first.open_structure_tree()

            problems = tree.validate(check_content=False)

            assert any('/ParentTree belongs to another PDF' in p for p in problems)
            assert any('/IDTree belongs to another PDF' in p for p in problems)

    def test_form_with_invalid_resources_is_reported_when_invoked(self, blank):
        page = blank.pages[0]
        form = blank.make_stream(
            b'',
            Type=Name.XObject,
            Subtype=Name.Form,
            Resources=42,
        )
        page.obj.Resources = Dictionary(XObject=Dictionary(Fm0=form))
        set_contents(blank, page, b'/Fm0 Do\n')
        tree = blank.open_structure_tree().create()

        assert any(
            '/Resources that is not a dictionary' in problem
            for problem in tree.validate()
        )

    def test_form_with_invalid_resources_is_reported_for_mcr(self, blank):
        page = blank.pages[0]
        form = blank.make_stream(
            b'/P <</MCID 0>> BDC EMC\n',
            Type=Name.XObject,
            Subtype=Name.Form,
            Resources=42,
        )
        tree = blank.open_structure_tree()
        elem = tree.add(Name.P, page=page)

        with pytest.raises(StructureTreeError, match='/Resources must be a dictionary'):
            elem.add_content(page, 0, stream=form)

        assert Name.K not in elem.obj
        assert Name.StructParents not in form

        form.StructParents = 0
        elem.obj.K = Array([Dictionary(Type=Name.MCR, Pg=page.obj, Stm=form, MCID=0)])
        tree.parent_tree[0] = blank.make_indirect(Array([elem.obj]))

        assert any(
            '/Resources that is not a dictionary' in problem
            for problem in tree.validate()
        )

    def test_role_map_chain_may_resolve_to_a_standard_type(self, blank):
        tree = blank.open_structure_tree()
        tree.add(Name.CustomA)
        tree.obj.RoleMap = Dictionary(CustomA=Name.CustomB, CustomB=Name.P)

        assert tree.validate(check_content=False) == []

    @pytest.mark.parametrize('in_array', [False, True])
    def test_attribute_stream_validates_cleanly(self, blank, in_array):
        tree = blank.open_structure_tree()
        elem = tree.add(Name.P)
        stream = blank.make_stream(b'', O=Name.Layout)
        elem.obj.A = Array([stream]) if in_array else stream

        assert tree.validate(check_content=False) == []

    @pytest.mark.parametrize('in_array', [False, True])
    @pytest.mark.parametrize('owner', [None, String('Layout')])
    def test_attribute_stream_requires_a_name_owner(self, blank, in_array, owner):
        tree = blank.open_structure_tree()
        elem = tree.add(Name.P)
        stream = blank.make_stream(b'')
        if owner is not None:
            stream.O = owner
        elem.obj.A = Array([stream]) if in_array else stream

        assert any(
            '/A' in problem and 'name-valued /O' in problem
            for problem in tree.validate(check_content=False)
        )

    @pytest.mark.parametrize(
        'attributes',
        [
            Dictionary(),
            Dictionary(O=String('Layout')),
            Array([Dictionary()]),
            Array([Dictionary(O=String('Layout'))]),
        ],
    )
    def test_attribute_dictionary_owner_is_validated(self, blank, attributes):
        tree = blank.open_structure_tree()
        elem = tree.add(Name.P)
        elem.obj.A = attributes

        assert any(
            '/A' in problem and 'name-valued /O' in problem
            for problem in tree.validate(check_content=False)
        )

    def test_attribute_array_with_revisions_is_valid(self, blank):
        tree = blank.open_structure_tree()
        elem = tree.add(Name.P)
        elem.obj.A = Array([Dictionary(O=Name.Layout), 1, Dictionary(O=Name.List)])

        assert tree.validate(check_content=False) == []

    def test_direct_objr_referent_is_reported(self, blank):
        page = blank.pages[0]
        tree = blank.open_structure_tree()
        elem = tree.add(Name.Link, page=page)
        referent = Dictionary(Type=Name.Annot, StructParent=0)
        elem.obj.K = Array([Dictionary(Type=Name.OBJR, Obj=referent, Pg=page.obj)])
        tree.parent_tree[0] = elem.obj

        assert any('/OBJR with a direct /Obj' in problem for problem in tree.validate())

    def test_direct_mcr_page_and_stream_owner_are_reported(self, blank):
        tree = blank.open_structure_tree()
        elem = tree.add(Name.P)
        elem.obj.K = Array(
            [
                Dictionary(
                    Type=Name.MCR,
                    MCID=0,
                    Pg=Dictionary(Type=Name.Page),
                    StmOwn=Dictionary(),
                )
            ]
        )

        problems = tree.validate(check_content=False)

        assert any('/MCR with a direct /Pg' in problem for problem in problems)
        assert any('non-indirect /StmOwn' in problem for problem in problems)
