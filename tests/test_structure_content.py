# SPDX-FileCopyrightText: 2026 Khushwant Parihar
# SPDX-License-Identifier: CC0-1.0

from __future__ import annotations

from decimal import Decimal

import pytest
from conftest import set_structure_contents as set_contents
from conftest import structure_registration_failure

import pikepdf
from pikepdf import (
    Array,
    ContentMarker,
    Dictionary,
    FontUsage,
    MarkedContent,
    Name,
    ObjectRef,
    Pdf,
    String,
    StructElem,
    StructureTreeError,
    find_font_usage,
    find_marked_content,
    mark_text_runs,
    next_mcid,
)


class TestContentReferences:
    def test_add_content(self, blank):
        page = blank.pages[0]
        tree = blank.open_structure_tree()
        elem = tree.add(Name.P, page=page)
        ref = elem.add_content(page, 0)
        assert ref.mcid == 0
        assert ref.obj is None
        assert elem.content == [ref]
        assert elem.obj.K == Array([0])
        assert page.obj.StructParents == 0
        assert tree.parent_tree.next_key == 1
        entry = tree.parent_tree.entry_for_page(page)
        assert entry[0].objgen == elem.obj.objgen
        assert 'mcid=0' in repr(ref)

    def test_add_content_other_page(self, blank):
        blank.add_blank_page()
        first, second = blank.pages[0], blank.pages[1]
        tree = blank.open_structure_tree()
        elem = tree.add(Name.P, page=first)
        elem.add_content(first, 0)
        elem.add_content(second, 2)
        assert elem.obj.K[0] == 0
        mcr = elem.obj.K[1]
        assert mcr.Type == Name.MCR
        assert mcr.MCID == 2
        assert mcr.Pg.objgen == second.obj.objgen
        assert [r.mcid for r in elem.content] == [0, 2]
        assert second.obj.StructParents == 1
        entry = tree.parent_tree.entry_for_page(second)
        assert len(entry) == 3
        assert entry[0] is None and entry[1] is None
        assert entry[2].objgen == elem.obj.objgen

    def test_add_content_uses_inherited_element_page(self, blank):
        page = blank.pages[0]
        tree = blank.open_structure_tree()
        document = tree.add(Name.Document, page=page)
        paragraph = document.add_child(Name.P)

        paragraph.add_content(page, 0)

        assert paragraph.page.obj.objgen == page.obj.objgen
        assert paragraph.obj.K == Array([0])

    def test_add_content_in_form_xobject(self, blank):
        page = blank.pages[0]
        xobj = blank.make_stream(b"BT (x) Tj ET", Type=Name.XObject, Subtype=Name.Form)
        tree = blank.open_structure_tree()
        elem = tree.add(Name.P, page=page)
        ref = elem.add_content(page, 0, stream=xobj)
        assert ref.stream == xobj
        assert ref.obj == elem.obj.K[0]
        ref.obj.TestValue = 42
        assert elem.obj.K[0].TestValue == 42
        assert Name.StructParents not in page.obj
        assert xobj.StructParents == 0
        assert elem.obj.K[0].Stm == xobj

    def test_add_content_with_stream_owner(self, blank):
        page = blank.pages[0]
        appearance = blank.make_stream(b'', Type=Name.XObject, Subtype=Name.Form)
        owner = blank.make_indirect(Dictionary(OwnedStream=appearance))
        elem = blank.open_structure_tree().add(Name.Figure, page=page)

        ref = elem.add_content(
            page,
            0,
            stream=appearance,
            stream_owner=owner,
        )

        assert ref.stream_owner == owner
        assert ref.obj == elem.obj.K[0]
        assert ref.obj.StmOwn == owner

    def test_annotation_appearance_mcr_is_an_executed_stream(self, blank):
        page = blank.pages[0]
        appearance = blank.make_stream(
            b'/Figure <</MCID 0>> BDC EMC\n',
            Type=Name.XObject,
            Subtype=Name.Form,
        )
        annotation = blank.make_indirect(
            Dictionary(
                Type=Name.Annot,
                Subtype=Name.Widget,
                AP=Dictionary(N=Dictionary(On=appearance)),
            )
        )
        page.obj.Annots = Array([annotation])
        tree = blank.open_structure_tree()

        tree.add(Name.Figure, page=page).add_content(
            page,
            0,
            stream=appearance,
            stream_owner=annotation,
        )

        assert tree.validate() == []

    @pytest.mark.parametrize('indirect_state_dictionary', [False, True])
    @pytest.mark.parametrize('typed_annotation', [False, True])
    def test_annotation_appearance_owner_accepts_indirect_ap_dictionaries(
        self, blank, indirect_state_dictionary, typed_annotation
    ):
        page = blank.pages[0]
        appearance = blank.make_stream(
            b'/Figure <</MCID 0>> BDC EMC\n',
            Type=Name.XObject,
            Subtype=Name.Form,
        )
        normal = Dictionary(On=appearance)
        if indirect_state_dictionary:
            normal = blank.make_indirect(normal)
        appearances = blank.make_indirect(Dictionary(N=normal))
        annotation_data = Dictionary(Subtype=Name.Widget, AP=appearances)
        if typed_annotation:
            annotation_data.Type = Name.Annot
        annotation = blank.make_indirect(annotation_data)
        page.obj.Annots = Array([annotation])
        tree = blank.open_structure_tree()

        tree.add(Name.Figure, page=page).add_content(
            page,
            0,
            stream=appearance,
            stream_owner=annotation,
        )

        assert tree.validate() == []

    def test_annotation_appearance_owner_must_be_on_the_claimed_page(self, blank):
        first_page = blank.pages[0]
        second_page = blank.add_blank_page()
        appearance = blank.make_stream(
            b'/Figure <</MCID 0>> BDC EMC\n',
            Type=Name.XObject,
            Subtype=Name.Form,
        )
        annotation = blank.make_indirect(
            Dictionary(Type=Name.Annot, AP=Dictionary(N=appearance))
        )
        first_page.obj.Annots = Array([annotation])
        elem = blank.open_structure_tree().add(Name.Figure)

        with pytest.raises(StructureTreeError, match='not on the claimed page'):
            elem.add_content(
                second_page,
                0,
                stream=appearance,
                stream_owner=annotation,
            )

        assert Name.K not in elem.obj
        assert Name.StructParents not in appearance

    def test_unlinked_stream_owner_is_rejected_without_mutation(self, blank):
        page = blank.pages[0]
        claimed = blank.make_stream(
            b'/Figure <</MCID 0>> BDC EMC\n',
            Type=Name.XObject,
            Subtype=Name.Form,
        )
        other = blank.make_stream(b'', Type=Name.XObject, Subtype=Name.Form)
        annotation = blank.make_indirect(
            Dictionary(Type=Name.Annot, AP=Dictionary(N=other))
        )
        page.obj.Annots = Array([annotation])
        tree = blank.open_structure_tree()
        elem = tree.add(Name.Figure, page=page)

        with pytest.raises(StructureTreeError, match='does not reference stream'):
            elem.add_content(
                page,
                0,
                stream=claimed,
                stream_owner=annotation,
            )

        assert Name.K not in elem.obj
        assert Name.StructParents not in claimed

    def test_large_stream_owner_graph_is_supported(self, blank):
        page = blank.pages[0]
        claimed = blank.make_stream(b'', Type=Name.XObject, Subtype=Name.Form)
        owner = blank.make_indirect(
            Dictionary(Owned=Array([claimed, *[Dictionary() for _ in range(300)]]))
        )
        elem = blank.open_structure_tree().add(Name.Figure, page=page)

        elem.add_content(page, 0, stream=claimed, stream_owner=owner)

        assert len(elem.content) == 1
        assert claimed.StructParents == 0

    def test_over_budget_stream_owner_graph_is_bounded_without_mutation(self, blank):
        page = blank.pages[0]
        claimed = blank.make_stream(b'', Type=Name.XObject, Subtype=Name.Form)
        owner = blank.make_indirect(
            Dictionary(Owned=Array([claimed, *[Dictionary() for _ in range(10_001)]]))
        )
        elem = blank.open_structure_tree().add(Name.Figure, page=page)

        with pytest.raises(StructureTreeError, match='does not reference stream'):
            elem.add_content(page, 0, stream=claimed, stream_owner=owner)

        assert Name.K not in elem.obj
        assert Name.StructParents not in claimed

    def test_broken_stream_owner_link_is_reported(self, blank):
        page = blank.pages[0]
        appearance = blank.make_stream(
            b'/Figure <</MCID 0>> BDC EMC\n',
            Type=Name.XObject,
            Subtype=Name.Form,
        )
        owner = blank.make_indirect(Dictionary(OwnedStream=appearance))
        tree = blank.open_structure_tree()
        tree.add(Name.Figure, page=page).add_content(
            page,
            0,
            stream=appearance,
            stream_owner=owner,
        )
        del owner[Name.OwnedStream]

        assert any(
            '/StmOwn does not reference /Stm' in problem for problem in tree.validate()
        )

    def test_stream_owner_without_stream_is_reported(self, blank):
        page = blank.pages[0]
        owner = blank.make_indirect(Dictionary())
        tree = blank.open_structure_tree()
        elem = tree.add(Name.Figure, page=page)
        elem.obj.K = Array(
            [Dictionary(Type=Name.MCR, MCID=0, Pg=page.obj, StmOwn=owner)]
        )

        assert any('/StmOwn but no /Stm' in problem for problem in tree.validate())

    def test_non_annotation_stream_owner_is_valid(self, blank):
        page = blank.pages[0]
        appearance = blank.make_stream(
            b'/Figure <</MCID 0>> BDC EMC\n',
            Type=Name.XObject,
            Subtype=Name.Form,
        )
        owner = blank.make_indirect(Dictionary(Owned=Array([appearance])))
        tree = blank.open_structure_tree()
        tree.add(Name.Figure, page=page).add_content(
            page,
            0,
            stream=appearance,
            stream_owner=owner,
        )

        assert tree.validate() == []

    def test_annotation_appearance_owner_must_be_on_claimed_page(self, blank):
        first = blank.pages[0]
        second = blank.add_blank_page()
        appearance = blank.make_stream(
            b'/Figure <</MCID 0>> BDC EMC\n',
            Type=Name.XObject,
            Subtype=Name.Form,
        )
        annotation = blank.make_indirect(
            Dictionary(Type=Name.Annot, AP=Dictionary(N=appearance))
        )
        first.obj.Annots = Array([annotation])
        tree = blank.open_structure_tree()
        elem = tree.add(Name.Figure, page=second)
        elem.obj.K = Array(
            [
                Dictionary(
                    Type=Name.MCR,
                    Pg=second.obj,
                    Stm=appearance,
                    StmOwn=annotation,
                    MCID=0,
                )
            ]
        )
        appearance.StructParents = 0
        tree.parent_tree[0] = blank.make_indirect(Array([elem.obj]))

        assert any(
            'annotation appearance /StmOwn that is not on /Pg' in problem
            for problem in tree.validate()
        )

    def test_stream_owner_requires_stream_without_mutation(self, blank):
        page = blank.pages[0]
        owner = blank.make_indirect(Dictionary(Type=Name.Annot))
        elem = blank.open_structure_tree().add(Name.Figure, page=page)

        with pytest.raises(ValueError, match="stream_owner requires stream"):
            elem.add_content(page, 0, stream_owner=owner)

        assert Name.K not in elem.obj
        assert Name.StructParents not in page.obj

    def test_stream_owner_must_be_owned_and_indirect_without_mutation(self, blank):
        page = blank.pages[0]
        appearance = blank.make_stream(b'', Type=Name.XObject, Subtype=Name.Form)
        elem = blank.open_structure_tree().add(Name.Figure, page=page)

        with pytest.raises(StructureTreeError, match="indirect object"):
            elem.add_content(
                page,
                0,
                stream=appearance,
                stream_owner=Dictionary(Type=Name.Annot),
            )

        assert Name.K not in elem.obj
        assert Name.StructParents not in appearance

    def test_form_mcid_cannot_be_shared_across_pages(self, blank):
        first = blank.pages[0]
        second = blank.add_blank_page()
        form = blank.make_stream(
            b"/P <</MCID 0>> BDC EMC\n",
            Type=Name.XObject,
            Subtype=Name.Form,
        )
        for page in (first, second):
            page.obj.Resources = Dictionary(XObject=Dictionary(Fm0=form))
            set_contents(blank, page, b"")
        tree = blank.open_structure_tree()
        elem = tree.add(Name.P)

        elem.add_content(first, 0, stream=form)
        with pytest.raises(StructureTreeError, match="more than one page"):
            elem.add_content(second, 1, stream=form)

        assert len(elem.content) == 1
        assert elem.content[0].page.objgen == first.obj.objgen
        assert tree.parent_tree[form.StructParents][0].objgen == elem.obj.objgen
        assert tree.validate() == []

    def test_same_form_mcid_cannot_be_claimed_twice_on_one_page(self, blank):
        page = blank.pages[0]
        form = blank.make_stream(b"", Type=Name.XObject, Subtype=Name.Form)
        elem = blank.open_structure_tree().add(Name.P)
        elem.add_content(page, 0, stream=form)

        with pytest.raises(StructureTreeError, match="already claimed"):
            elem.add_content(page, 0, stream=form)

        assert len(elem.content) == 1

    def test_form_mcr_need_not_be_observed_in_the_partial_execution_graph(self, blank):
        page = blank.pages[0]
        form = blank.make_stream(
            b"/P <</MCID 0>> BDC EMC\n",
            Type=Name.XObject,
            Subtype=Name.Form,
        )
        page.obj.Resources = Dictionary(XObject=Dictionary(Fm0=form))
        set_contents(blank, page, b"")
        tree = blank.open_structure_tree()
        tree.add(Name.P).add_content(page, 0, stream=form)

        assert tree.validate() == []

    def test_structural_form_cannot_be_invoked_twice_on_one_page(self, blank):
        page = blank.pages[0]
        form = blank.make_stream(
            b"/P <</MCID 0>> BDC EMC\n",
            Type=Name.XObject,
            Subtype=Name.Form,
        )
        page.obj.Resources = Dictionary(XObject=Dictionary(Fm0=form))
        set_contents(blank, page, b"/Fm0 Do /Fm0 Do\n")
        tree = blank.open_structure_tree()
        elem = tree.add(Name.P)

        with pytest.raises(StructureTreeError, match="invoked more than once"):
            elem.add_content(page, 0, stream=form)

        assert Name.K not in elem.obj
        assert Name.StructParents not in form

    def test_nested_paths_to_structural_form_count_as_multiple_invocations(self, blank):
        page = blank.pages[0]
        inner = blank.make_stream(
            b"/P <</MCID 0>> BDC EMC\n",
            Type=Name.XObject,
            Subtype=Name.Form,
        )
        first_outer = blank.make_stream(
            b"/Inner Do\n",
            Type=Name.XObject,
            Subtype=Name.Form,
            Resources=Dictionary(XObject=Dictionary(Inner=inner)),
        )
        second_outer = blank.make_stream(
            b"/Inner Do\n",
            Type=Name.XObject,
            Subtype=Name.Form,
            Resources=Dictionary(XObject=Dictionary(Inner=inner)),
        )
        page.obj.Resources = Dictionary(
            XObject=Dictionary(First=first_outer, Second=second_outer)
        )
        set_contents(blank, page, b"/First Do /Second Do\n")
        tree = blank.open_structure_tree()
        elem = tree.add(Name.P)

        with pytest.raises(StructureTreeError, match="invoked more than once"):
            elem.add_content(page, 0, stream=inner)

        assert Name.K not in elem.obj
        assert Name.StructParents not in inner

    @pytest.mark.parametrize('in_form', [False, True])
    def test_second_claim_cannot_create_nested_structural_content(self, blank, in_form):
        page = blank.pages[0]
        content = b'/P <</MCID 0>> BDC /Span <</MCID 1>> BDC EMC EMC\n'
        stream = (
            blank.make_stream(content, Type=Name.XObject, Subtype=Name.Form)
            if in_form
            else None
        )
        if stream is None:
            set_contents(blank, page, content)
        tree = blank.open_structure_tree()
        elem = tree.add(Name.P, page=page)
        elem.add_content(page, 0, stream=stream)

        with pytest.raises(StructureTreeError, match='must not be nested'):
            elem.add_content(page, 1, stream=stream)

        assert [ref.mcid for ref in elem.content] == [0]
        container = page.obj if stream is None else stream
        entry = tree.parent_tree.entry_for_page(container)
        assert entry is not None
        assert len(entry) == 1

    def test_negative_mcid(self, blank):
        tree = blank.open_structure_tree()
        elem = tree.add(Name.P, page=blank.pages[0])
        with pytest.raises(ValueError, match="non-negative"):
            elem.add_content(blank.pages[0], -1)
        assert Name.K not in elem.obj

    @pytest.mark.parametrize('mcid', [True, 1.5, '1'])
    def test_mcid_must_be_an_integer(self, blank, mcid):
        page = blank.pages[0]
        elem = blank.open_structure_tree().add(Name.P, page=page)

        with pytest.raises(TypeError, match="must be integers"):
            elem.add_content(page, mcid)

        assert Name.K not in elem.obj
        assert Name.StructParents not in page.obj

    def test_add_object(self, blank):
        page = blank.pages[0]
        annot = blank.make_indirect(Dictionary(Type=Name.Annot, Subtype=Name.Link))
        page.obj.Annots = Array([annot])
        tree = blank.open_structure_tree()
        elem = tree.add(Name.Link, page=page)
        ref = elem.add_object(annot, page)
        assert isinstance(ref, ObjectRef)
        assert ref.obj == elem.obj.K[0]
        ref.obj.TestValue = 42
        assert elem.obj.K[0].TestValue == 42
        assert annot.StructParent == 0
        assert elem.obj.K[0].Type == Name.OBJR
        assert tree.parent_tree[0].objgen == elem.obj.objgen
        assert isinstance(elem.kids[0], ObjectRef)
        assert elem.kids[0].referent == annot
        assert repr(ref).startswith('<pikepdf.ObjectRef:')

    def test_add_object_reuses_struct_parent(self, blank):
        page = blank.pages[0]
        annot = blank.make_indirect(
            Dictionary(Type=Name.Annot, Subtype=Name.Link, StructParent=5)
        )
        page.obj.Annots = Array([annot])
        tree = blank.open_structure_tree()
        elem = tree.add(Name.Link, page=page)
        elem.add_object(annot, page)
        assert annot.StructParent == 5
        assert tree.parent_tree[5].objgen == elem.obj.objgen

    def test_add_object_uses_inherited_element_page(self, blank):
        page = blank.pages[0]
        annot = blank.make_indirect(Dictionary(Type=Name.Annot, Subtype=Name.Link))
        page.obj.Annots = Array([annot])
        tree = blank.open_structure_tree()
        document = tree.add(Name.Document, page=page)
        link = document.add_child(Name.Link)

        link.add_object(annot, page)

        assert Name.Pg not in link.obj.K[0]

    def test_objr_without_obj(self, blank):
        tree = blank.open_structure_tree()
        elem = tree.add(Name.Link)
        elem.obj.K = Array([Dictionary(Type=Name.OBJR)])
        with pytest.raises(StructureTreeError, match="/Obj"):
            _ = elem.kids

    def test_mcr_without_mcid(self, blank):
        tree = blank.open_structure_tree()
        elem = tree.add(Name.P)
        elem.obj.K = Array([Dictionary(Type=Name.MCR)])
        with pytest.raises(StructureTreeError, match="/MCID"):
            _ = elem.kids

    def test_kid_append_to_scalar_k(self, blank):
        page = blank.pages[0]
        tree = blank.open_structure_tree()
        elem = tree.add(Name.P, page=page)
        elem.obj.K = 0
        elem.add_content(page, 1)
        assert list(elem.obj.K) == [0, 1]


class TestMarkedContentDiscovery:
    @pytest.mark.parametrize(
        'operation',
        [find_marked_content, next_mcid, find_font_usage, ContentMarker],
    )
    def test_page_argument_must_be_a_page(self, blank, operation):
        with pytest.raises(TypeError, match="pikepdf.Page"):
            operation(blank.pages[0].obj)

    def test_find_marked_content(self, blank):
        page = blank.pages[0]
        page.obj.Resources = Dictionary(
            Properties=Dictionary(MC0=blank.make_indirect(Dictionary(MCID=7)))
        )
        set_contents(
            blank,
            page,
            b"/P /MC0 BDC BT (x) Tj ET EMC /Span BMC (y) Tj EMC "
            b"/P <</MCID 2>> BDC EMC\n",
        )
        found = find_marked_content(page)
        assert [(str(mc.tag), mc.mcid) for mc in found] == [
            ('/P', 7),
            ('/Span', None),
            ('/P', 2),
        ]
        assert next_mcid(page) == 8

    def test_next_mcid_on_untagged_page(self, blank):
        assert next_mcid(blank.pages[0]) == 0
        assert find_marked_content(blank.pages[0]) == []

    def test_find_marked_content_ignores_junk(self, blank):
        page = blank.pages[0]
        set_contents(blank, page, b"(notaname) 1 BDC EMC\n")
        assert find_marked_content(page) == []

    def test_find_marked_content_checks_operator_arity(self, blank):
        page = blank.pages[0]
        set_contents(
            blank,
            page,
            b"/P <</MCID 9>> BMC EMC /P BDC EMC /Span BMC EMC\n",
        )

        assert find_marked_content(page) == [MarkedContent(Name.Span, None)]

    def test_next_mcid_ignores_invalid_negative_identifiers(self, blank):
        page = blank.pages[0]
        set_contents(blank, page, b"/P <</MCID -2>> BDC EMC\n")

        assert next_mcid(page) == 0

    def test_find_font_usage(self, text_pdf):
        usage = find_font_usage(text_pdf.pages[0])
        assert [(str(u.font), u.size) for u in usage] == [
            ('/F2', Decimal(24)),
            ('/F1', Decimal(12)),
            ('/F1', Decimal(12)),
        ]
        assert usage[0].base_font == Name('/Helvetica-Bold')
        assert usage[0].index == 1

    def test_find_font_usage_without_resources(self, blank):
        page = blank.pages[0]
        set_contents(blank, page, b"BT /F1 12 Tf ET\n")
        assert find_font_usage(page)[0].base_font is None

    def test_find_font_usage_skips_malformed_numbers_and_base_font(self, blank):
        page = blank.pages[0]
        page.obj.Resources = Dictionary(
            Font=Dictionary(
                F1=blank.make_indirect(Dictionary(BaseFont=String('not a name')))
            )
        )
        set_contents(
            blank,
            page,
            b"BT /F1 /Bad Tf /F1 true Tf /F1 12 Tf (x) Tj ET\n",
        )

        assert find_font_usage(page) == [FontUsage(Name.F1, Decimal(12), 3, None)]

    def test_inherited_resources_resolve_mcids_and_fonts(self, blank):
        page = blank.pages[0]
        if Name.Resources in page.obj:
            del page.obj[Name.Resources]
        page.obj.Parent.Resources = Dictionary(
            Properties=Dictionary(MC0=blank.make_indirect(Dictionary(MCID=7))),
            Font=Dictionary(
                F1=blank.make_indirect(
                    Dictionary(
                        Type=Name.Font,
                        Subtype=Name.Type1,
                        BaseFont=Name.Helvetica,
                    )
                )
            ),
        )
        set_contents(blank, page, b"/P /MC0 BDC BT /F1 12 Tf (x) Tj ET EMC\n")

        assert find_marked_content(page)[0].mcid == 7
        assert next_mcid(page) == 8
        assert find_font_usage(page)[0].base_font == Name.Helvetica


class TestContentMarker:
    def test_mark_and_apply(self, text_pdf):
        page = text_pdf.pages[0]
        marker = ContentMarker(page)
        assert len(marker.instructions) == 20
        result = marker.mark(Name.H1, 0, 5)
        assert result.mcid == 0
        assert marker.apply() == [result]
        data = page.obj.Contents.read_bytes()
        assert b'/H1 << /MCID 0 >> BDC' in data
        assert data.index(b'BDC') < data.index(b'BT')
        assert data.index(b'EMC') > data.index(b'ET')
        assert [(str(mc.tag), mc.mcid) for mc in find_marked_content(page)] == [
            ('/H1', 0)
        ]

    def test_apply_with_no_spans(self, text_pdf):
        page = text_pdf.pages[0]
        before = page.obj.Contents.read_bytes()
        assert ContentMarker(page).apply() == []
        assert page.obj.Contents.read_bytes() == before

    def test_new_tagged_ranges_cannot_be_nested(self, text_pdf):
        page = text_pdf.pages[0]
        tree = text_pdf.open_structure_tree()
        outer = tree.add(Name.Sect, page=page)
        inner = tree.add(Name.H1, page=page)
        marker = ContentMarker(page)
        marker.mark(Name.Sect, 0, 10, element=outer)
        with pytest.raises(StructureTreeError, match="must not be nested"):
            marker.mark(Name.H1, 0, 5, element=inner)

    def test_new_tagged_range_cannot_wrap_another(self, text_pdf):
        page = text_pdf.pages[0]
        tree = text_pdf.open_structure_tree()
        inner = tree.add(Name.H1, page=page)
        outer = tree.add(Name.Sect, page=page)
        marker = ContentMarker(page)
        marker.mark(Name.H1, 0, 5, element=inner)
        with pytest.raises(StructureTreeError, match="must not be nested"):
            marker.mark(Name.Sect, 0, 10, element=outer)

    def test_new_unbound_tagged_ranges_may_be_nested(self, text_pdf):
        marker = ContentMarker(text_pdf.pages[0])
        marker.mark(Name.Sect, 0, 10)
        marker.mark(Name.H1, 0, 5)

        marker.apply()

    def test_artifact(self, text_pdf):
        page = text_pdf.pages[0]
        marker = ContentMarker(page)
        marker.mark_artifact(15, 20)
        marker.mark(Name.H1, 0, 5)
        marker.apply()
        data = page.obj.Contents.read_bytes()
        assert b'/Artifact BMC' in data
        assert b'/H1 << /MCID 0 >> BDC' in data

    def test_artifact_with_properties(self, text_pdf):
        page = text_pdf.pages[0]
        marker = ContentMarker(page)
        marker.mark_artifact(15, 20, properties={Name.Type: Name.Pagination})
        marker.apply()
        assert (
            b'/Artifact << /Type /Pagination >> BDC' in page.obj.Contents.read_bytes()
        )

    def test_artifact_mcid_uses_the_stream_identifier_space(self, text_pdf):
        page = text_pdf.pages[0]
        marker = ContentMarker(page)

        marker.mark_artifact(15, 20, properties={Name.MCID: 0})
        tagged = marker.mark(Name.H1, 0, 5)

        assert tagged.mcid == 1
        marker.apply()
        assert next_mcid(page) == 2
        assert [(item.tag, item.mcid) for item in find_marked_content(page)] == [
            (Name.H1, 1),
            (Name.Artifact, 0),
        ]

    def test_duplicate_artifact_mcid_is_rejected_without_mutation(self, text_pdf):
        page = text_pdf.pages[0]
        before = page.obj.Contents.read_bytes()
        marker = ContentMarker(page)
        marker.mark_artifact(0, 5, properties={Name.MCID: 0})

        with pytest.raises(StructureTreeError, match="already used"):
            marker.mark_artifact(5, 10, properties={Name.MCID: 0})

        assert page.obj.Contents.read_bytes() == before

    @pytest.mark.parametrize(
        ('mcid', 'error'),
        [(True, TypeError), (1.5, TypeError), (-1, ValueError), (5, ValueError)],
    )
    def test_invalid_artifact_mcid_is_rejected_without_mutation(
        self, text_pdf, mcid, error
    ):
        page = text_pdf.pages[0]
        before = page.obj.Contents.read_bytes()

        with pytest.raises(error):
            ContentMarker(page).mark_artifact(
                0,
                5,
                properties={Name.MCID: mcid},
            )

        assert page.obj.Contents.read_bytes() == before

    def test_extra_properties(self, text_pdf):
        page = text_pdf.pages[0]
        marker = ContentMarker(page)
        marker.mark(Name.Span, 0, 5, properties={Name.Lang: String('fr-CA')})
        marker.apply()
        data = page.obj.Contents.read_bytes()
        assert b'/Lang' in data and b'/MCID 0' in data

    def test_respects_existing_mcids(self, text_pdf):
        page = text_pdf.pages[0]
        first = ContentMarker(page)
        first.mark(Name.H1, 0, 5)
        first.apply()
        second = ContentMarker(page)
        assert second.mark(Name.P, 7, 12).mcid == 1

    def test_first_mcid_override(self, text_pdf):
        page = text_pdf.pages[0]
        first = ContentMarker(page)
        first.mark(Name.H1, 0, 5)
        first.apply()

        marker = ContentMarker(page, first_mcid=100)
        assert marker.mark(Name.P, 7, 12).mcid == 100

    def test_first_mcid_must_start_at_zero_on_unmarked_stream(self, text_pdf):
        with pytest.raises(ValueError, match="must be 0"):
            ContentMarker(text_pdf.pages[0], first_mcid=100)

    def test_marker_rejects_existing_identifier_space_that_does_not_start_at_zero(
        self, blank
    ):
        page = blank.pages[0]
        set_contents(blank, page, b'/P <</MCID 5>> BDC EMC 0 g\n')
        before = page.obj.Contents.read_bytes()
        marker = ContentMarker(page)
        marker.mark(Name.Span, 2, 3)

        with pytest.raises(StructureTreeError, match="start at 0"):
            marker.apply()

        assert page.obj.Contents.read_bytes() == before

        repair = ContentMarker(page, first_mcid=0)
        assert repair.mark(Name.Span, 2, 3).mcid == 0
        repair.apply()
        assert {item.mcid for item in find_marked_content(page)} == {0, 5}

    @pytest.mark.parametrize(
        ('first_mcid', 'error'),
        [(-1, ValueError), (True, TypeError), (1.5, TypeError)],
    )
    def test_invalid_first_mcid_is_rejected_without_mutation(
        self, text_pdf, first_mcid, error
    ):
        page = text_pdf.pages[0]
        before = page.obj.Contents.read_bytes()
        with pytest.raises(error):
            ContentMarker(page, first_mcid=first_mcid)
        assert page.obj.Contents.read_bytes() == before

    def test_tag_must_be_a_name(self, text_pdf):
        marker = ContentMarker(text_pdf.pages[0])
        with pytest.raises(TypeError, match="pikepdf.Name"):
            marker.mark('/P', 0, 5)  # type: ignore[arg-type]
        assert marker.apply() == []

    def test_element_must_be_a_struct_elem(self, text_pdf):
        marker = ContentMarker(text_pdf.pages[0])

        with pytest.raises(TypeError, match="StructElem"):
            marker.mark(Name.P, 0, 5, element=Dictionary())

        assert marker.apply() == []

    def test_inline_properties_reject_nested_indirect_objects(self, text_pdf):
        page = text_pdf.pages[0]
        indirect = text_pdf.make_indirect(Dictionary(Value=1))
        marker = ContentMarker(page)

        with pytest.raises(ValueError, match="indirect objects"):
            marker.mark(
                Name.P,
                0,
                5,
                properties={Name.A: Array([Dictionary(Value=indirect)])},
            )

        assert marker.apply() == []

    def test_inline_properties_reject_a_direct_cycle_without_mutation(self, text_pdf):
        page = text_pdf.pages[0]
        cyclic = Dictionary()
        cyclic.Self = cyclic
        marker = ContentMarker(page)
        try:
            with pytest.raises(ValueError, match='object graph is cyclic'):
                marker.mark(Name.P, 0, 5, properties={Name.Value: cyclic})

            assert marker.apply() == []
        finally:
            del cyclic[Name.Self]

    def test_inline_properties_allow_a_shared_acyclic_subobject(self, text_pdf):
        page = text_pdf.pages[0]
        shared = Dictionary(Value=1)
        marker = ContentMarker(page)

        marker.mark(
            Name.P,
            0,
            5,
            properties={Name.First: shared, Name.Second: shared},
        )

        assert len(marker.apply()) == 1

    def test_artifact_tag_uses_artifact_api(self, text_pdf):
        marker = ContentMarker(text_pdf.pages[0])
        with pytest.raises(ValueError, match="mark_artifact"):
            marker.mark(Name.Artifact, 0, 5)

    def test_wires_element(self, text_pdf):
        page = text_pdf.pages[0]
        tree = text_pdf.open_structure_tree()
        elem = tree.add(Name.H1, page=page)
        marker = ContentMarker(page)
        marker.mark(Name.H1, 0, 5, element=elem)
        marker.apply()
        assert [r.mcid for r in elem.content] == [0]
        assert tree.validate() == []

    def test_apply_preflights_every_target_element_before_mutation(self, text_pdf):
        page = text_pdf.pages[0]
        tree = text_pdf.open_structure_tree()
        first = tree.add(Name.P, page=page)
        malformed = tree.add(Name.P, page=page)
        malformed.obj.K = String('bad')
        marker = ContentMarker(page)
        marker.mark(Name.P, 0, 5, element=first)
        marker.mark(Name.P, 5, 10, element=malformed)
        before_contents = page.obj.Contents.read_bytes()
        before_objects = len(text_pdf.objects)

        with pytest.raises(StructureTreeError):
            marker.apply()

        assert page.obj.Contents.read_bytes() == before_contents
        assert Name.K not in first.obj
        assert malformed.obj.K == String('bad')
        assert Name.StructParents not in page.obj
        assert tree.parent_tree.keys() == []
        assert len(text_pdf.objects) == before_objects

    def test_foreign_element_is_rejected_without_mutation(self, text_pdf):
        page = text_pdf.pages[0]
        before = page.obj.Contents.read_bytes()
        with Pdf.new() as other:
            other.add_blank_page()
            foreign = other.open_structure_tree().add(Name.P)
            marker = ContentMarker(page)
            with pytest.raises(StructureTreeError, match="different PDF"):
                marker.mark(Name.P, 0, 5, element=foreign)
            assert marker.apply() == []
            assert Name.K not in foreign.obj
        assert page.obj.Contents.read_bytes() == before

    def test_marker_is_reusable_after_apply(self, text_pdf):
        page = text_pdf.pages[0]
        marker = ContentMarker(page)
        marker.mark(Name.H1, 0, 5)
        marker.apply()
        assert len(marker.instructions) == 22
        assert marker.apply() == []

    @pytest.mark.parametrize('start,stop', [(-1, 4), (4, 4), (5, 3), (0, 999)])
    def test_bad_range(self, text_pdf, start, stop):
        with pytest.raises(IndexError):
            ContentMarker(text_pdf.pages[0]).mark(Name.P, start, stop)

    @pytest.mark.parametrize(
        ('start', 'stop'),
        [(True, 5), (0, False), (0.0, 5), (0, 5.0)],
    )
    def test_range_indices_must_be_exact_integers(self, text_pdf, start, stop):
        with pytest.raises(TypeError, match="indices must be integers"):
            ContentMarker(text_pdf.pages[0]).mark(Name.P, start, stop)

    def test_partial_overlap(self, text_pdf):
        marker = ContentMarker(text_pdf.pages[0])
        marker.mark(Name.P, 0, 10)
        with pytest.raises(StructureTreeError, match="partially overlaps"):
            marker.mark(Name.P, 5, 15)

    def test_straddling_rejected(self, text_pdf):
        marker = ContentMarker(text_pdf.pages[0])
        with pytest.raises(StructureTreeError, match="straddles"):
            marker.mark(Name.P, 1, 7)

    def test_straddling_close_rejected(self, text_pdf):
        marker = ContentMarker(text_pdf.pages[0])
        with pytest.raises(StructureTreeError, match="straddles"):
            marker.mark(Name.P, 3, 8)

    @pytest.mark.parametrize(
        'content, start, stop',
        [
            (b"0 0 m 10 10 l S\n", 1, 2),
            (b"q 0 0 m 10 10 l S Q\n", 2, 3),
            (b"0 0 10 10 re W n\n", 1, 2),
        ],
    )
    def test_path_objects_cannot_be_split(self, blank, content, start, stop):
        page = blank.pages[0]
        set_contents(blank, page, content)

        with pytest.raises(StructureTreeError, match="splits a path object"):
            ContentMarker(page).mark_artifact(start, stop)

    @pytest.mark.parametrize(
        'content, start, stop',
        [
            (b"0 0 m 10 10 l S\n", 0, 3),
            (b"q 0 0 m 10 10 l S Q\n", 1, 4),
            (b"0 0 10 10 re W n\n", 0, 3),
        ],
    )
    def test_complete_path_objects_can_be_wrapped(self, blank, content, start, stop):
        page = blank.pages[0]
        set_contents(blank, page, content)
        marker = ContentMarker(page)
        marker.mark_artifact(start, stop)

        marker.apply()

        operators = [str(item.operator) for item in pikepdf.parse_content_stream(page)]
        path_start = next(
            index for index, operator in enumerate(operators) if operator in {'m', 're'}
        )
        path_end = max(
            index for index, operator in enumerate(operators) if operator in {'S', 'n'}
        )
        assert operators.index('BMC') < path_start
        assert operators.index('EMC') > path_end

    def test_path_construction_without_a_start_is_rejected(self, blank):
        page = blank.pages[0]
        set_contents(blank, page, b"10 10 l S\n")

        with pytest.raises(StructureTreeError, match="outside a path object"):
            ContentMarker(page).mark_artifact(0, 2)

    def test_unterminated_path_is_rejected(self, blank):
        page = blank.pages[0]
        set_contents(blank, page, b"0 0 m 10 10 l\n")

        with pytest.raises(StructureTreeError, match="unterminated path object"):
            ContentMarker(page).mark_artifact(0, 2)

    def test_existing_marked_content_boundary_cannot_be_crossed(self, blank):
        page = blank.pages[0]
        set_contents(
            blank,
            page,
            b"/P <</MCID 0>> BDC BT (a) Tj ET EMC BT (b) Tj ET\n",
        )
        marker = ContentMarker(page)
        with pytest.raises(StructureTreeError, match="marked-content sequence"):
            marker.mark(Name.P, 1, 8)

    def test_tagged_content_cannot_nest_in_existing_tagged_content(self, blank):
        page = blank.pages[0]
        set_contents(blank, page, b"/P <</MCID 0>> BDC BT (a) Tj ET EMC\n")
        tree = blank.open_structure_tree()
        tree.add(Name.P, page=page).add_content(page, 0)
        target = tree.add(Name.Span, page=page)
        marker = ContentMarker(page)
        marker.mark(Name.Span, 1, 4, element=target)

        with pytest.raises(StructureTreeError, match="must not be nested"):
            marker.apply()

    def test_tagged_content_cannot_wrap_existing_tagged_content(self, blank):
        page = blank.pages[0]
        set_contents(blank, page, b"/P <</MCID 0>> BDC BT (a) Tj ET EMC\n")
        tree = blank.open_structure_tree()
        tree.add(Name.P, page=page).add_content(page, 0)
        target = tree.add(Name.Sect, page=page)
        marker = ContentMarker(page)
        marker.mark(Name.Sect, 0, 5, element=target)

        with pytest.raises(StructureTreeError, match="must not be nested"):
            marker.apply()

    @pytest.mark.parametrize(
        ('existing_claimed', 'new_claimed', 'rejected'),
        [
            (False, False, False),
            (False, True, False),
            (True, False, False),
            (True, True, True),
        ],
    )
    def test_only_claimed_marked_content_is_structural_for_nesting(
        self, blank, existing_claimed, new_claimed, rejected
    ):
        page = blank.pages[0]
        set_contents(blank, page, b'/P <</MCID 0>> BDC BT (x) Tj ET EMC\n')
        tree = blank.open_structure_tree()
        if existing_claimed:
            tree.add(Name.P, page=page).add_content(page, 0)
        target = tree.add(Name.Span, page=page) if new_claimed else None
        marker = ContentMarker(page)
        marker.mark(Name.Span, 1, 4, element=target)

        if rejected:
            with pytest.raises(StructureTreeError, match='must not be nested'):
                marker.apply()
        else:
            marker.apply()

    def test_tagged_content_can_nest_in_nonstructural_marked_content(self, blank):
        page = blank.pages[0]
        set_contents(blank, page, b"/OC BMC BT (a) Tj ET EMC\n")
        marker = ContentMarker(page)
        marker.mark(Name.Span, 1, 4)
        marker.apply()
        assert page.obj.Contents.read_bytes().count(b'BDC') == 1

    @pytest.mark.parametrize('existing_tag', [Name.P, Name.Artifact])
    def test_artifacts_and_tags_may_nest(self, blank, existing_tag):
        page = blank.pages[0]
        if existing_tag == Name.Artifact:
            set_contents(blank, page, b"/Artifact BMC BT (a) Tj ET EMC\n")
            marker = ContentMarker(page)
        else:
            set_contents(blank, page, b"/P <</MCID 0>> BDC BT (a) Tj ET EMC\n")
            marker = ContentMarker(page)
        if existing_tag == Name.Artifact:
            marker.mark(Name.P, 1, 4)
        else:
            marker.mark_artifact(1, 4)
        marker.apply()

    def test_inherited_properties_identify_existing_tagged_content(self, blank):
        page = blank.pages[0]
        if Name.Resources in page.obj:
            del page.obj[Name.Resources]
        page.obj.Parent.Resources = Dictionary(
            Properties=Dictionary(MC0=blank.make_indirect(Dictionary(MCID=0)))
        )
        set_contents(blank, page, b"/P /MC0 BDC BT (a) Tj ET EMC\n")

        marker = ContentMarker(page)
        marker.mark_artifact(1, 4)
        marker.apply()

    def test_apply_rechecks_changed_inherited_properties(self, blank):
        page = blank.pages[0]
        if Name.Resources in page.obj:
            del page.obj[Name.Resources]
        page.obj.Parent.Resources = Dictionary(
            Properties=Dictionary(MC0=Dictionary(Type=Name.OCG))
        )
        set_contents(blank, page, b"/OC /MC0 BDC BT (a) Tj ET EMC\n")
        before = page.obj.Contents.read_bytes()
        marker = ContentMarker(page)
        marker.mark(Name.Span, 1, 4)
        page.obj.Parent.Resources.Properties.MC0 = Dictionary(MCID=0)

        with pytest.raises(StructureTreeError, match="already used"):
            marker.apply()

        assert page.obj.Contents.read_bytes() == before

    def test_object_claimed_xobject_cannot_be_wrapped(self, blank):
        page = blank.pages[0]
        form = blank.make_stream(b"", Type=Name.XObject, Subtype=Name.Form)
        page.obj.Resources = Dictionary(XObject=Dictionary(Fm0=form))
        set_contents(blank, page, b"/Fm0 Do\n")
        tree = blank.open_structure_tree()
        tree.add(Name.Figure, page=page).add_object(form, page)
        target = tree.add(Name.P, page=page)

        marker = ContentMarker(page)
        marker.mark(Name.P, 0, 1, element=target)
        with pytest.raises(StructureTreeError, match="structural content"):
            marker.apply()

    def test_mcr_claimed_xobject_cannot_be_wrapped(self, blank):
        page = blank.pages[0]
        form = blank.make_stream(
            b'/Figure <</MCID 0>> BDC EMC\n',
            Type=Name.XObject,
            Subtype=Name.Form,
        )
        page.obj.Resources = Dictionary(XObject=Dictionary(Fm0=form))
        set_contents(blank, page, b'/Fm0 Do\n')
        tree = blank.open_structure_tree()
        tree.add(Name.Figure, page=page).add_content(page, 0, stream=form)
        target = tree.add(Name.P, page=page)

        marker = ContentMarker(page)
        marker.mark(Name.P, 0, 1, element=target)
        with pytest.raises(StructureTreeError, match='structural content'):
            marker.apply()

    def test_artifact_range_may_invoke_structural_xobject(self, blank):
        page = blank.pages[0]
        form = blank.make_stream(
            b"", Type=Name.XObject, Subtype=Name.Form, StructParents=0
        )
        page.obj.Resources = Dictionary(XObject=Dictionary(Fm0=form))
        set_contents(blank, page, b"/Fm0 Do\n")
        marker = ContentMarker(page)

        marker.mark_artifact(0, 1)
        marker.apply()

    def test_nested_resource_less_form_uses_top_page_resources(self, blank):
        page = blank.pages[0]
        inner = blank.make_stream(
            b'/Figure <</MCID 0>> BDC EMC\n',
            Type=Name.XObject,
            Subtype=Name.Form,
        )
        outer = blank.make_stream(b"/Inner Do\n", Type=Name.XObject, Subtype=Name.Form)
        page.obj.Resources = Dictionary(XObject=Dictionary(Outer=outer, Inner=inner))
        set_contents(blank, page, b"/Outer Do\n")
        tree = blank.open_structure_tree()
        tree.add(Name.Figure, page=page).add_content(page, 0, stream=inner)
        target = tree.add(Name.P, page=page)

        marker = ContentMarker(page)
        marker.mark(Name.P, 0, 1, element=target)
        with pytest.raises(StructureTreeError, match="structural content"):
            marker.apply()

    def test_tagged_range_may_invoke_artifact_form(self, blank):
        page = blank.pages[0]
        form = blank.make_stream(
            b"/Artifact BMC EMC\n", Type=Name.XObject, Subtype=Name.Form
        )
        page.obj.Resources = Dictionary(XObject=Dictionary(Fm0=form))
        set_contents(blank, page, b"/Fm0 Do\n")

        marker = ContentMarker(page)
        marker.mark(Name.P, 0, 1)
        marker.apply()

    def test_structural_range_may_invoke_an_unclaimed_mcid_form(self, blank):
        page = blank.pages[0]
        form = blank.make_stream(
            b'/P <</MCID 0>> BDC EMC\n',
            Type=Name.XObject,
            Subtype=Name.Form,
        )
        page.obj.Resources = Dictionary(XObject=Dictionary(Fm0=form))
        set_contents(blank, page, b'/Fm0 Do\n')
        tree = blank.open_structure_tree()
        target = tree.add(Name.P, page=page)
        marker = ContentMarker(page)
        marker.mark(Name.P, 0, 1, element=target)

        marker.apply()

        assert tree.validate() == []

    def test_form_mcid_claim_on_another_page_is_not_structural_here(self):
        with Pdf.new() as pdf:
            first_page = pdf.add_blank_page()
            second_page = pdf.add_blank_page()
            form = pdf.make_stream(
                b'/P /MC0 BDC EMC\n', Type=Name.XObject, Subtype=Name.Form
            )
            for page in (first_page, second_page):
                page.obj.Resources = Dictionary(
                    Properties=Dictionary(MC0=Dictionary(MCID=0)),
                    XObject=Dictionary(Fm0=form),
                )
            set_contents(pdf, first_page, b'')
            set_contents(pdf, second_page, b'/Fm0 Do\n')
            tree = pdf.open_structure_tree()
            tree.add(Name.P).add_content(first_page, 0, stream=form)
            target = tree.add(Name.Figure, page=second_page)
            marker = ContentMarker(second_page)

            marker.mark(Name.Figure, 0, 1, element=target)
            marker.apply()

            assert tree.validate() == []

    @pytest.mark.parametrize('stop', [1, 2])
    def test_repeated_form_invocations_need_distinct_claimed_spans(self, blank, stop):
        page = blank.pages[0]
        form = blank.make_stream(b'', Type=Name.XObject, Subtype=Name.Form)
        page.obj.Resources = Dictionary(XObject=Dictionary(Fm0=form))
        set_contents(blank, page, b'/Fm0 Do /Fm0 Do\n')
        tree = blank.open_structure_tree()
        target = tree.add(Name.Figure, page=page)
        marker = ContentMarker(page)
        marker.mark(Name.Figure, 0, stop, element=target)

        with pytest.raises(StructureTreeError, match='distinct claimed'):
            marker.apply()

        assert Name.K not in target.obj

    def test_nested_repeated_form_invocations_inherit_the_page_wrapper(self, blank):
        page = blank.pages[0]
        inner = blank.make_stream(b'', Type=Name.XObject, Subtype=Name.Form)
        outer = blank.make_stream(
            b'/Inner Do /Inner Do\n',
            Type=Name.XObject,
            Subtype=Name.Form,
            Resources=Dictionary(XObject=Dictionary(Inner=inner)),
        )
        page.obj.Resources = Dictionary(XObject=Dictionary(Outer=outer))
        set_contents(blank, page, b'/Outer Do\n')
        tree = blank.open_structure_tree()
        target = tree.add(Name.Figure, page=page)
        before = page.obj.Contents.read_bytes()
        marker = ContentMarker(page)
        marker.mark(Name.Figure, 0, 1, element=target)

        with pytest.raises(StructureTreeError, match='distinct claimed'):
            marker.apply()

        assert page.obj.Contents.read_bytes() == before
        assert Name.K not in target.obj

    def test_repeated_form_invocations_may_use_distinct_claimed_spans(self, blank):
        page = blank.pages[0]
        form = blank.make_stream(b'', Type=Name.XObject, Subtype=Name.Form)
        page.obj.Resources = Dictionary(XObject=Dictionary(Fm0=form))
        set_contents(blank, page, b'/Fm0 Do /Fm0 Do\n')
        tree = blank.open_structure_tree()
        first = tree.add(Name.Figure, page=page)
        second = tree.add(Name.Figure, page=page)
        marker = ContentMarker(page)
        marker.mark(Name.Figure, 0, 1, element=first)
        marker.mark(Name.Figure, 1, 2, element=second)

        marker.apply()

        assert tree.validate() == []

    def test_unbound_span_may_contain_repeated_form_invocations(self, blank):
        page = blank.pages[0]
        form = blank.make_stream(b'', Type=Name.XObject, Subtype=Name.Form)
        page.obj.Resources = Dictionary(XObject=Dictionary(Fm0=form))
        set_contents(blank, page, b'/Fm0 Do /Fm0 Do\n')
        marker = ContentMarker(page)
        marker.mark(Name.Figure, 0, 2)

        marker.apply()

    def test_apply_rechecks_changed_xobject_resources(self, blank):
        page = blank.pages[0]
        clean = blank.make_stream(b"", Type=Name.XObject, Subtype=Name.Form)
        structural = blank.make_stream(
            b'/Figure <</MCID 0>> BDC EMC\n',
            Type=Name.XObject,
            Subtype=Name.Form,
        )
        page.obj.Resources = Dictionary(XObject=Dictionary(Fm0=clean))
        set_contents(blank, page, b"/Fm0 Do\n")
        tree = blank.open_structure_tree()
        tree.add(Name.Figure, page=page).add_content(page, 0, stream=structural)
        target = tree.add(Name.P, page=page)
        before = page.obj.Contents.read_bytes()
        marker = ContentMarker(page)
        marker.mark(Name.P, 0, 1, element=target)
        page.obj.Resources.XObject.Fm0 = structural

        with pytest.raises(StructureTreeError, match="structural content"):
            marker.apply()

        assert page.obj.Contents.read_bytes() == before

    def test_self_invoking_form_is_rejected_without_recursing_forever(self, blank):
        page = blank.pages[0]
        form = blank.make_stream(b"/Self Do\n", Type=Name.XObject, Subtype=Name.Form)
        form.Resources = Dictionary(XObject=Dictionary(Self=form))
        page.obj.Resources = Dictionary(XObject=Dictionary(Fm0=form))
        set_contents(blank, page, b"/Fm0 Do\n")

        with pytest.raises(StructureTreeError, match="Cyclic Form"):
            ContentMarker(page).mark(Name.P, 0, 1)

    def test_bx_ex_boundaries_are_typed_scopes(self, blank):
        page = blank.pages[0]
        set_contents(blank, page, b"BX 0 g EX\n")
        marker = ContentMarker(page)
        marker.mark_artifact(1, 2)
        marker.apply()

        set_contents(blank, page, b"BX BT Q ET EX\n")
        with pytest.raises(StructureTreeError, match="unmatched Q"):
            ContentMarker(page)

    def test_artifact_can_wrap_existing_tagged_content(self, blank):
        page = blank.pages[0]
        set_contents(blank, page, b"/P <</MCID 0>> BDC BT (a) Tj ET EMC\n")
        marker = ContentMarker(page)
        marker.mark_artifact(0, 5)
        marker.apply()

    def test_queued_artifact_and_tag_may_nest(self, text_pdf):
        marker = ContentMarker(text_pdf.pages[0])
        marker.mark(Name.P, 0, 5)
        marker.mark_artifact(0, 5)
        marker.apply()

    def test_parent_tree_conflict_leaves_everything_unchanged(self, text_pdf):
        page = text_pdf.pages[0]
        tree = text_pdf.open_structure_tree()
        owner = tree.add(Name.P, page=page)
        owner.add_content(page, 0)
        target = tree.add(Name.Span, page=page)
        before = page.obj.Contents.read_bytes()
        marker = ContentMarker(page, first_mcid=0)
        marker.mark(Name.Span, 0, 5, element=target)

        with pytest.raises(StructureTreeError, match="already claimed"):
            marker.apply()

        assert page.obj.Contents.read_bytes() == before
        assert Name.K not in target.obj
        assert tree.parent_tree.entry_for_page(page)[0].objgen == owner.obj.objgen

    def test_all_spans_are_preflighted_before_mutation(self, text_pdf):
        page = text_pdf.pages[0]
        tree = text_pdf.open_structure_tree()
        owner = tree.add(Name.P, page=page)
        owner.add_content(page, 1)
        first = tree.add(Name.Span, page=page)
        second = tree.add(Name.Span, page=page)
        before = page.obj.Contents.read_bytes()
        marker = ContentMarker(page)
        marker.mark(Name.Span, 0, 5, element=first)
        marker.mark(Name.Span, 5, 10, element=second)

        with pytest.raises(StructureTreeError, match="already claimed"):
            marker.apply()

        assert page.obj.Contents.read_bytes() == before
        assert Name.K not in first.obj
        assert Name.K not in second.obj
        entry = tree.parent_tree.entry_for_page(page)
        assert entry[0] is None
        assert entry[1].objgen == owner.obj.objgen

    def test_apply_rolls_back_an_unexpected_registration_failure(
        self, text_pdf, monkeypatch
    ):
        page = text_pdf.pages[0]
        tree = text_pdf.open_structure_tree()
        first = tree.add(Name.H1, page=page)
        second = tree.add(Name.P, page=page)
        before = page.obj.Contents.read_bytes()
        marker = ContentMarker(page)
        marker.mark(Name.H1, 0, 5, element=first)
        marker.mark(Name.P, 5, 10, element=second)
        monkeypatch.setattr(
            StructElem,
            '_add_content_prechecked',
            structure_registration_failure(second),
        )
        with pytest.raises(RuntimeError, match="injected failure"):
            marker.apply()

        assert page.obj.Contents.read_bytes() == before
        assert Name.StructParents not in page.obj
        assert Name.K not in first.obj
        assert Name.K not in second.obj
        assert tree.parent_tree.keys() == []
        assert tree.parent_tree.next_key == 0

    def test_stale_marker_does_not_overwrite_newer_content(self, text_pdf):
        page = text_pdf.pages[0]
        first = ContentMarker(page)
        stale = ContentMarker(page)
        first.mark(Name.H1, 0, 5)
        stale.mark(Name.P, 5, 10)
        first.apply()
        before = page.obj.Contents.read_bytes()

        with pytest.raises(StructureTreeError, match="content stream changed"):
            stale.apply()

        assert page.obj.Contents.read_bytes() == before


class TestMarkTextRuns:
    def test_page_and_parent_inputs_are_strict(self, text_pdf):
        page = text_pdf.pages[0]
        with pytest.raises(TypeError, match="pikepdf.Page"):
            mark_text_runs(page.obj, {})
        with pytest.raises(TypeError, match="StructElem"):
            mark_text_runs(page, {}, parent=Dictionary())

    def test_mapping(self, text_pdf):
        page = text_pdf.pages[0]
        tree = text_pdf.open_structure_tree()
        doc = tree.add(Name.Document)
        result = mark_text_runs(
            page,
            {(Name.F2, Decimal(24)): Name.H1, (Name.F1, Decimal(12)): Name.P},
            parent=doc,
        )
        assert [(str(mc.tag), mc.mcid) for mc in result] == [('/H1', 0), ('/P', 1)]
        assert [str(c.tag) for c in doc.children] == ['/H1', '/P']
        assert tree.validate() == []
        assert b'/Artifact' not in page.obj.Contents.read_bytes()

    def test_adjacent_runs_merge(self, text_pdf):
        page = text_pdf.pages[0]
        result = mark_text_runs(page, {(Name.F1, Decimal(12)): Name.P})
        assert len(result) == 1
        data = page.obj.Contents.read_bytes()
        assert data.count(b'BDC') == 1
        assert data.count(b'(Body one)') == 1
        assert data.count(b'(Body two)') == 1

    def test_callable(self, text_pdf):
        page = text_pdf.pages[0]
        result = mark_text_runs(
            page, lambda usage: Name.H1 if usage.size > 20 else None
        )
        assert [(str(mc.tag), mc.mcid) for mc in result] == [('/H1', 0)]

    def test_nothing_mapped(self, text_pdf):
        page = text_pdf.pages[0]
        before = page.obj.Contents.read_bytes()
        assert mark_text_runs(page, {}) == []
        assert page.obj.Contents.read_bytes() == before

    def test_leaves_graphics_alone(self, text_pdf):
        page = text_pdf.pages[0]
        mark_text_runs(page, {(Name.F2, Decimal(24)): Name.H1})
        data = page.obj.Contents.read_bytes().decode()
        assert data.rstrip().endswith('Q')

    def test_each_font_change_in_a_text_object_is_honored(self, blank):
        page = blank.pages[0]
        page.obj.Resources = Dictionary(
            Font=Dictionary(
                F1=blank.make_indirect(Dictionary(BaseFont=Name.Helvetica)),
                F2=blank.make_indirect(Dictionary(BaseFont=Name.Courier)),
            )
        )
        set_contents(
            blank,
            page,
            b"BT /F1 12 Tf (one) Tj /F2 10 Tf (two) Tj ET 0 0 m 10 10 l S\n",
        )

        result = mark_text_runs(
            page,
            {
                (Name.F1, Decimal(12)): Name.P,
                (Name.F2, Decimal(10)): Name.H1,
            },
        )

        assert [item.tag for item in result] == [Name.P, Name.H1]
        operators = [str(item.operator) for item in pikepdf.parse_content_stream(page)]
        assert operators.count('BDC') == 2
        assert max(
            i for i, op in enumerate(operators) if op == 'EMC'
        ) < operators.index('ET')
        assert operators.index('ET') < operators.index('m')

    def test_font_selection_persists_across_text_objects(self, blank):
        page = blank.pages[0]
        page.obj.Resources = Dictionary(
            Font=Dictionary(F1=blank.make_indirect(Dictionary(BaseFont=Name.Helvetica)))
        )
        set_contents(
            blank,
            page,
            b'/F1 12 Tf BT (one) Tj ET BT (two) Tj ET\n',
        )

        result = mark_text_runs(page, {(Name.F1, Decimal(12)): Name.P})

        assert [item.tag for item in result] == [Name.P]
        data = page.obj.Contents.read_bytes()
        assert data.count(b'BDC') == 1
        assert data.index(b'BDC') < data.index(b'BT')
        assert data.rindex(b'EMC') > data.rindex(b'ET')

    def test_q_q_restores_the_selected_font(self, blank):
        page = blank.pages[0]
        page.obj.Resources = Dictionary(
            Font=Dictionary(
                F1=blank.make_indirect(Dictionary(BaseFont=Name.Helvetica)),
                F2=blank.make_indirect(Dictionary(BaseFont=Name.Courier)),
            )
        )
        set_contents(
            blank,
            page,
            b'/F1 12 Tf q /F2 10 Tf Q BT (restored) Tj ET\n',
        )

        result = mark_text_runs(
            page,
            {
                (Name.F1, Decimal(12)): Name.P,
                (Name.F2, Decimal(10)): Name.H1,
            },
        )

        assert [item.tag for item in result] == [Name.P]

    def test_extgstate_font_invalidates_a_stale_tf_selection(self, blank):
        page = blank.pages[0]
        font = blank.make_indirect(Dictionary(BaseFont=Name.Helvetica))
        page.obj.Resources = Dictionary(
            Font=Dictionary(F1=font),
            ExtGState=Dictionary(GS1=Dictionary(Font=Array([font, 9]))),
        )
        set_contents(
            blank,
            page,
            b'/F1 12 Tf /GS1 gs BT (not F1) Tj ET /F1 12 Tf BT (F1) Tj ET\n',
        )

        result = mark_text_runs(page, {(Name.F1, Decimal(12)): Name.P})

        assert [item.tag for item in result] == [Name.P]
        data = page.obj.Contents.read_bytes()
        assert data.index(b'BDC') > data.index(b'(not F1)')

    def test_artifact_mapping_is_rejected_before_children(self, text_pdf):
        page = text_pdf.pages[0]
        tree = text_pdf.open_structure_tree()
        parent = tree.add(Name.Document)
        object_count = len(text_pdf.objects)
        before = page.obj.Contents.read_bytes()

        with pytest.raises(ValueError, match="Artifact"):
            mark_text_runs(
                page,
                {
                    (Name.F2, Decimal(24)): Name.H1,
                    (Name.F1, Decimal(12)): Name.Artifact,
                },
                parent=parent,
            )

        assert Name.K not in parent.obj
        assert len(text_pdf.objects) == object_count
        assert page.obj.Contents.read_bytes() == before

    def test_existing_structural_scope_is_rejected_before_children(self, blank):
        page = blank.pages[0]
        page.obj.Resources = Dictionary(
            Font=Dictionary(F1=blank.make_indirect(Dictionary(BaseFont=Name.Helvetica)))
        )
        set_contents(
            blank,
            page,
            b"/P <</MCID 0>> BDC BT /F1 12 Tf (x) Tj ET EMC\n",
        )
        tree = blank.open_structure_tree()
        parent = tree.add(Name.Document)
        parent.add_child(Name.P, page=page).add_content(page, 0)
        object_count = len(blank.objects)

        with pytest.raises(StructureTreeError, match="must not be nested"):
            mark_text_runs(
                page,
                {(Name.F1, Decimal(12)): Name.P},
                parent=parent,
            )

        assert [child.tag for child in parent.children] == [Name.P]
        assert len(blank.objects) == object_count

    def test_invalid_later_tag_rolls_back_created_children(self, text_pdf):
        page = text_pdf.pages[0]
        before = page.obj.Contents.read_bytes()
        tree = text_pdf.open_structure_tree()
        parent = tree.add(Name.Document)
        object_count = len(text_pdf.objects)

        with pytest.raises(TypeError, match="pikepdf.Name"):
            mark_text_runs(
                page,
                {
                    (Name.F2, Decimal(24)): Name.H1,
                    (Name.F1, Decimal(12)): '/P',
                },
                parent=parent,
            )

        assert Name.K not in parent.obj
        assert len(text_pdf.objects) == object_count
        assert page.obj.Contents.read_bytes() == before
        assert Name.StructParents not in page.obj

    def test_apply_failure_restores_preexisting_children(self, text_pdf, monkeypatch):
        page = text_pdf.pages[0]
        before = page.obj.Contents.read_bytes()
        tree = text_pdf.open_structure_tree()
        parent = tree.add(Name.Document)
        retained = parent.add_child(Name.Sect)

        def fail_apply(_marker):
            raise RuntimeError("injected failure")

        monkeypatch.setattr(ContentMarker, 'apply', fail_apply)
        with pytest.raises(RuntimeError, match="injected failure"):
            mark_text_runs(
                page,
                {(Name.F2, Decimal(24)): Name.H1},
                parent=parent,
            )

        assert parent.children == [retained]
        assert page.obj.Contents.read_bytes() == before
        assert Name.StructParents not in page.obj
