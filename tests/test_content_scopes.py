# SPDX-FileCopyrightText: 2026 James R. Barlow
# SPDX-License-Identifier: CC0-1.0

"""Enumerating the content streams of a page and the resources each uses."""

from __future__ import annotations

import pytest

import pikepdf
from pikepdf import (
    Array,
    ContentScope,
    Dictionary,
    Name,
    ObjectSet,
    Page,
    Pdf,
    Stream,
)

pytestmark = pytest.mark.timeout(60, method='thread')


def _form(pdf: Pdf, resources: Dictionary | None = None, data: bytes = b'') -> Stream:
    form = Stream(pdf, data)
    form.Type = Name.XObject
    form.Subtype = Name.Form
    form.BBox = Array([0, 0, 10, 10])
    if resources is not None:
        form.Resources = resources
    return form


def _pattern(pdf: Pdf, resources: Dictionary | None = None) -> Stream:
    pattern = Stream(pdf, b'')
    pattern.Type = Name.Pattern
    pattern.PatternType = 1
    if resources is not None:
        pattern.Resources = resources
    return pattern


def _type3(pdf: Pdf, glyphs: int = 2, resources: Dictionary | None = None):
    font = pdf.make_indirect(
        Dictionary(
            Type=Name.Font,
            Subtype=Name.Type3,
            CharProcs=Dictionary({f'/g{i}': Stream(pdf, b'') for i in range(glyphs)}),
        )
    )
    if resources is not None:
        font.Resources = resources
    return font


def _blank() -> tuple[Pdf, Page]:
    pdf = pikepdf.new()
    pdf.add_blank_page()
    return pdf, pdf.pages[0]


def _kinds(scopes) -> list[str]:
    return [scope.kind for scope in scopes]


class TestPageScope:
    def test_blank_page(self):
        pdf, page = _blank()
        scopes = list(page.content_scopes())
        assert _kinds(scopes) == ['page']
        scope = scopes[0]
        assert isinstance(scope, ContentScope)
        assert isinstance(scope.content, Dictionary)
        assert scope.content.is_same_object_as(page)
        assert scope.page.obj.is_same_object_as(page)
        assert scope.resources.is_same_object_as(page.get_resources())

    def test_returns_an_iterator(self):
        _pdf, page = _blank()
        scopes = page.content_scopes()
        assert iter(scopes) is scopes
        assert next(scopes).kind == 'page'
        with pytest.raises(StopIteration):
            next(scopes)

    def test_page_without_resources(self):
        _pdf, page = _blank()
        del page.obj.Resources
        (scope,) = page.content_scopes()
        assert scope.resources is None
        assert Name.Resources not in page.obj

    def test_inherited_resources(self):
        pdf, page = _blank()
        form = _form(pdf)
        pdf.Root.Pages.Resources = Dictionary(XObject=Dictionary(Fm0=form))
        del page.obj.Resources
        scopes = list(page.content_scopes())
        assert _kinds(scopes) == ['page', 'form']
        assert scopes[0].resources.is_same_object_as(pdf.Root.Pages.Resources)

    @pytest.mark.parametrize(
        'resources',
        [
            Array([1]),
            Name.Bogus,
            Dictionary(XObject=Array([1]), Pattern=Name.No, Font=1, ExtGState=[2]),
            Dictionary(
                XObject=Dictionary(A=1, B=Dictionary()),
                Pattern=Dictionary(A=Name.No, B=Dictionary(PatternType=1)),
                Font=Dictionary(
                    A=3,
                    B=Dictionary(Subtype=Name.Type3),
                    C=Dictionary(Subtype=Name.Type3, CharProcs=Array([1])),
                    D=Dictionary(Subtype=Name.Type3, CharProcs=Dictionary(a=1)),
                ),
                ExtGState=Dictionary(
                    A=4,
                    B=Dictionary(SMask=Name('/None')),
                    C=Dictionary(SMask=Dictionary(G=5)),
                    D=Dictionary(Font=7),
                    E=Dictionary(Font=Array([])),
                ),
            ),
        ],
    )
    def test_malformed_resources(self, resources):
        pdf, page = _blank()
        page.obj.Resources = resources
        assert _kinds(page.content_scopes()) == ['page']
        assert pdf.get_warnings() == []

    @pytest.mark.parametrize(
        'annots',
        [
            Name.Bogus,
            Array([1, Name.No]),
            Array([Dictionary(AP=3)]),
            Array([Dictionary(AP=Dictionary(N=4, D=Dictionary(On=5)))]),
            Array([Dictionary(MK=6), Dictionary(MK=Dictionary(I=7))]),
        ],
    )
    def test_malformed_annotations(self, annots):
        pdf, page = _blank()
        page.obj.Annots = annots
        assert _kinds(page.content_scopes()) == ['page']
        assert pdf.get_warnings() == []

    def test_scope_is_frozen_and_compares_by_identity(self):
        _pdf, page = _blank()
        (a,) = page.content_scopes()
        (b,) = page.content_scopes()
        with pytest.raises(AttributeError):
            a.kind = 'form'
        assert a == a
        assert a != b


class TestKindsOfScope:
    def test_forms(self):
        pdf, page = _blank()
        inner_resources = Dictionary(Marker=Name.Inner)
        inner = _form(pdf, inner_resources)
        outer = _form(pdf, Dictionary(XObject=Dictionary(Inner=inner)))
        page.obj.Resources = Dictionary(XObject=Dictionary(Outer=outer))
        scopes = list(page.content_scopes())
        assert _kinds(scopes) == ['page', 'form', 'form']
        assert scopes[1].content.is_same_object_as(outer)
        assert scopes[2].content.is_same_object_as(inner)
        assert scopes[2].resources.Marker == Name.Inner
        assert all(scope.page.obj.is_same_object_as(page) for scope in scopes)

    def test_form_without_resources_uses_those_of_the_page(self):
        # ISO 32000-2 8.10.2: not those of the form that draws it
        pdf, page = _blank()
        bare = _form(pdf)
        outer = _form(pdf, Dictionary(Marker=Name.Outer, XObject=Dictionary(B=bare)))
        page.obj.Resources = Dictionary(Marker=Name.Page, XObject=Dictionary(O=outer))
        scopes = list(page.content_scopes())
        assert _kinds(scopes) == ['page', 'form', 'form']
        assert scopes[2].content.is_same_object_as(bare)
        assert scopes[2].resources.Marker == Name.Page

    def test_appearance_streams(self):
        pdf, page = _blank()
        normal = _form(pdf, Dictionary(Marker=Name.N))
        on = _form(pdf, Dictionary(Marker=Name.On))
        off = _form(pdf)
        nested = _form(pdf)
        normal.Resources.XObject = Dictionary(Nested=nested)
        page.obj.Annots = Array(
            [
                pdf.make_indirect(
                    Dictionary(Subtype=Name.Stamp, AP=Dictionary(N=normal))
                ),
                pdf.make_indirect(
                    Dictionary(
                        Subtype=Name.Widget,
                        AP=Dictionary(N=Dictionary(On=on, Off=off)),
                    )
                ),
            ]
        )
        scopes = list(page.content_scopes())
        assert _kinds(scopes) == [
            'page',
            'appearance',
            'appearance',
            'appearance',
            'form',
        ]
        assert scopes[1].content.is_same_object_as(normal)
        assert scopes[4].content.is_same_object_as(nested)
        # An appearance stream does not use the page's resources
        by_content = {s.content.objgen: s for s in scopes[1:]}
        assert by_content[off.objgen].resources is None
        assert by_content[on.objgen].resources.Marker == Name.On

    def test_tiling_patterns(self):
        pdf, page = _blank()
        nested = _form(pdf)
        tiling = _pattern(pdf, Dictionary(XObject=Dictionary(Fm=nested)))
        shading = pdf.make_indirect(Dictionary(Type=Name.Pattern, PatternType=2))
        page.obj.Resources = Dictionary(Pattern=Dictionary(P0=tiling, P1=shading))
        scopes = list(page.content_scopes())
        assert _kinds(scopes) == ['page', 'pattern', 'form']
        assert scopes[1].content.is_same_object_as(tiling)

    def test_type3_glyphs_use_the_font_resources(self):
        pdf, page = _blank()
        font = _type3(pdf, 2, Dictionary(Marker=Name.FontOwn))
        page.obj.Resources = Dictionary(Font=Dictionary(F0=font))
        scopes = list(page.content_scopes())
        assert _kinds(scopes) == ['page', 'glyph', 'glyph']
        assert all(s.resources.Marker == Name.FontOwn for s in scopes[1:])
        assert all(isinstance(s.content, Stream) for s in scopes[1:])

    def test_type3_glyphs_without_font_resources_use_those_of_the_page(self):
        # ISO 32000-2 9.6.4
        pdf, page = _blank()
        font = _type3(pdf, 1)
        form = _form(pdf, Dictionary(Font=Dictionary(F0=font)))
        page.obj.Resources = Dictionary(XObject=Dictionary(Fm=form))
        scopes = list(page.content_scopes())
        assert _kinds(scopes) == ['page', 'form', 'glyph']
        assert scopes[2].resources.is_same_object_as(page.obj.Resources)

    def test_glyphs_shared_by_fonts_with_different_resources(self):
        pdf, page = _blank()
        hidden = _form(pdf, Dictionary())
        first = _type3(pdf, 1, Dictionary(Marker=Name.First))
        second = pdf.make_indirect(
            Dictionary(
                Type=Name.Font,
                Subtype=Name.Type3,
                CharProcs=first.CharProcs,
                Resources=Dictionary(
                    Marker=Name.Second, XObject=Dictionary(Hidden=hidden)
                ),
            )
        )
        page.obj.Resources = Dictionary(Font=Dictionary(F1=first, F2=second))
        scopes = list(page.content_scopes())
        assert _kinds(scopes) == ['page', 'glyph', 'glyph', 'form']
        assert scopes[1].content.is_same_object_as(scopes[2].content)
        assert {s.resources.Marker for s in scopes[1:3]} == {Name.First, Name.Second}
        assert scopes[3].content.is_same_object_as(hidden)

    def test_tiling_pattern_type_written_as_a_real(self):
        pdf, page = _blank()
        tiling = _pattern(pdf, Dictionary())
        tiling.PatternType = pikepdf.Real('1.0')
        page.obj.Resources = Dictionary(Pattern=Dictionary(P0=tiling))
        assert _kinds(page.content_scopes()) == ['page', 'pattern']

    def test_button_icons(self):
        pdf, page = _blank()
        normal = _form(pdf, Dictionary())
        rollover = _form(pdf, Dictionary())
        page.obj.Annots = Array(
            [
                pdf.make_indirect(
                    Dictionary(
                        Subtype=Name.Widget,
                        MK=Dictionary(I=normal, RI=rollover, IX=Name.Bogus),
                    )
                )
            ]
        )
        assert _kinds(page.content_scopes()) == ['page', 'appearance', 'appearance']

    def test_type3_font_selected_by_graphics_state(self):
        pdf, page = _blank()
        font = _type3(pdf, 1, Dictionary())
        page.obj.Resources = Dictionary(
            ExtGState=Dictionary(GS0=Dictionary(Font=Array([font, 12])))
        )
        assert _kinds(page.content_scopes()) == ['page', 'glyph']

    def test_other_fonts_are_not_scopes(self):
        pdf, page = _blank()
        font = pdf.make_indirect(Dictionary(Type=Name.Font, Subtype=Name.Type1))
        page.obj.Resources = Dictionary(Font=Dictionary(F0=font))
        assert _kinds(page.content_scopes()) == ['page']

    def test_soft_mask_groups(self):
        pdf, page = _blank()
        nested = _form(pdf)
        group = _form(pdf, Dictionary(XObject=Dictionary(Fm=nested)))
        page.obj.Resources = Dictionary(
            ExtGState=Dictionary(
                GS0=Dictionary(SMask=Dictionary(S=Name.Luminosity, G=group))
            )
        )
        scopes = list(page.content_scopes())
        assert _kinds(scopes) == ['page', 'softmask', 'form']
        assert scopes[1].content.is_same_object_as(group)

    def test_images_are_not_scopes(self):
        pdf, page = _blank()
        image = Stream(pdf, b'\xff')
        image.Subtype = Name.Image
        page.obj.Resources = Dictionary(XObject=Dictionary(Im0=image))
        assert _kinds(page.content_scopes()) == ['page']

    def test_starting_from_a_form(self):
        pdf = pikepdf.new()
        bare = _form(pdf)
        inner = _form(pdf, Dictionary(XObject=Dictionary(Bare=bare)))
        outer = _form(pdf, Dictionary(XObject=Dictionary(Inner=inner)))
        scopes = list(Page(outer).content_scopes())
        assert _kinds(scopes) == ['form', 'form', 'form']
        assert scopes[0].content.is_same_object_as(outer)
        assert all(scope.page is None for scope in scopes)
        # There is no page to lend its resources
        assert scopes[2].resources is None


class TestEachScopeOnce:
    def test_shared_resources(self):
        pdf, page = _blank()
        shared = pdf.make_indirect(Dictionary(XObject=Dictionary()))
        for i in range(12):
            shared.XObject[f'/Fm{i}'] = _form(pdf, shared)
        page.obj.Resources = shared
        assert _kinds(page.content_scopes()) == ['page'] + ['form'] * 12

    def test_everything_nests_in_everything(self):
        pdf, page = _blank()
        shared = pdf.make_indirect(Dictionary())
        shared.XObject = Dictionary(Fm0=_form(pdf, shared), Fm1=_form(pdf, shared))
        shared.Pattern = Dictionary(P0=_pattern(pdf, shared))
        shared.Font = Dictionary(F0=_type3(pdf, 2, shared))
        shared.ExtGState = Dictionary(
            GS0=Dictionary(SMask=Dictionary(G=_form(pdf, shared)))
        )
        page.obj.Resources = shared
        page.obj.Annots = Array(
            [pdf.make_indirect(Dictionary(AP=Dictionary(N=_form(pdf, shared))))]
        )
        assert sorted(_kinds(page.content_scopes())) == sorted(
            ['page', 'form', 'form', 'pattern', 'glyph', 'glyph', 'softmask']
            + ['appearance']
        )

    def test_stream_without_resources_once_per_page_resources(self):
        pdf, first = _blank()
        for _ in range(2):
            pdf.add_blank_page()
        second, third = pdf.pages[1], pdf.pages[2]
        bare = _form(pdf)
        holder = _form(pdf, Dictionary(XObject=Dictionary(Bare=bare)))
        first.obj.Resources = Dictionary(XObject=Dictionary(Holder=holder))
        second.obj.Resources = Dictionary(XObject=Dictionary(Holder=holder))
        third.obj.Resources = first.obj.Resources
        scopes = list(pdf.content_scopes())
        assert _kinds(scopes) == ['page', 'form', 'form', 'page', 'form', 'page']
        uses = [s for s in scopes if s.content.is_same_object_as(bare)]
        assert [s.page.index for s in uses] == [0, 1]
        assert uses[0].resources.is_same_object_as(first.obj.Resources)
        assert uses[1].resources.is_same_object_as(second.obj.Resources)

    def test_page_resources_reach_a_stream_nested_under_shared_forms(self):
        # Both pages reach the same chain of forms, which have resources of
        # their own, and at the end of it a form that has none.
        pdf, first = _blank()
        pdf.add_blank_page()
        second = pdf.pages[1]
        bare = _form(pdf)
        inner = _form(pdf, Dictionary(XObject=Dictionary(Bare=bare)))
        middle = _form(pdf, Dictionary(XObject=Dictionary(Inner=inner)))
        outer = _form(pdf, Dictionary(XObject=Dictionary(Middle=middle)))
        first.obj.Resources = Dictionary(XObject=Dictionary(Outer=outer))
        second.obj.Resources = Dictionary(XObject=Dictionary(Outer=outer))
        scopes = list(pdf.content_scopes())
        assert _kinds(scopes) == ['page'] + ['form'] * 4 + ['page', 'form']
        assert scopes[4].resources.is_same_object_as(first.obj.Resources)
        assert scopes[6].content.is_same_object_as(bare)
        assert scopes[6].resources.is_same_object_as(second.obj.Resources)

    def test_deeply_nested(self):
        pdf, page = _blank()
        form = _form(pdf, Dictionary())
        for _ in range(3000):
            form = _form(pdf, Dictionary(XObject=Dictionary(Fm=form)))
        page.obj.Resources = Dictionary(XObject=Dictionary(Fm=form))
        assert len(list(page.content_scopes())) == 3002


class TestKindsFilter:
    @pytest.fixture
    def pdf(self):
        pdf, page = _blank()
        in_appearance = _form(pdf, Dictionary())
        in_pattern = _form(pdf, Dictionary())
        page.obj.Resources = Dictionary(
            XObject=Dictionary(Fm0=_form(pdf, Dictionary())),
            Pattern=Dictionary(
                P0=_pattern(pdf, Dictionary(XObject=Dictionary(Fm=in_pattern)))
            ),
            Font=Dictionary(F0=_type3(pdf, 1, Dictionary())),
            ExtGState=Dictionary(
                GS0=Dictionary(SMask=Dictionary(G=_form(pdf, Dictionary())))
            ),
        )
        appearance = _form(pdf, Dictionary(XObject=Dictionary(Fm=in_appearance)))
        page.obj.Annots = Array(
            [pdf.make_indirect(Dictionary(AP=Dictionary(N=appearance)))]
        )
        return pdf

    @pytest.fixture
    def page(self, pdf):
        return pdf.pages[0]

    def test_default_is_everything(self, page):
        assert sorted(_kinds(page.content_scopes())) == sorted(
            ['page', 'form', 'form', 'form', 'pattern', 'glyph', 'softmask']
            + ['appearance']
        )
        assert sorted(_kinds(page.content_scopes(kinds=None))) == sorted(
            _kinds(page.content_scopes())
        )

    def test_everything_is_searched_whatever_is_reported(self, page):
        # including the forms inside the appearance stream and the pattern
        assert _kinds(page.content_scopes(kinds={'page', 'form'})) == [
            'page',
            'form',
            'form',
            'form',
        ]

    def test_one_kind(self, page):
        assert _kinds(page.content_scopes(kinds={'form'})) == ['form'] * 3
        assert _kinds(page.content_scopes(kinds={'glyph'})) == ['glyph']

    def test_single_kind_as_string(self, page):
        assert _kinds(page.content_scopes(kinds='pattern')) == ['pattern']

    def test_no_kinds(self, page):
        assert _kinds(page.content_scopes(kinds=())) == []

    @pytest.mark.parametrize('kinds', [{'forms'}, 'Page', ['page', 'xobject']])
    def test_unknown_kind(self, page, kinds):
        with pytest.raises(ValueError, match='kind'):
            page.content_scopes(kinds=kinds)

    def test_wrong_type(self, page):
        with pytest.raises(TypeError):
            page.content_scopes(kinds=[1])


class TestPdfScopes:
    def test_each_scope_once_for_the_document(self):
        pdf = pikepdf.new()
        shared = _form(pdf, Dictionary())
        for _ in range(3):
            pdf.add_blank_page()
        for page in pdf.pages:
            page.obj.Resources = Dictionary(XObject=Dictionary(Shared=shared))
        scopes = list(pdf.content_scopes())
        assert _kinds(scopes) == ['page', 'form', 'page', 'page']
        assert scopes[1].page.obj.is_same_object_as(pdf.pages[0])
        assert [s.page.index for s in scopes] == [0, 0, 1, 2]

    def test_some_pages(self):
        pdf = pikepdf.new()
        shared = _form(pdf, Dictionary())
        for _ in range(4):
            pdf.add_blank_page()
        for page in pdf.pages:
            page.obj.Resources = Dictionary(XObject=Dictionary(Shared=shared))
        scopes = list(pdf.content_scopes(pages=[pdf.pages[3], pdf.pages[1]]))
        assert _kinds(scopes) == ['page', 'form', 'page']
        assert [s.page.index for s in scopes] == [3, 3, 1]
        assert list(pdf.content_scopes(pages=[])) == []

    def test_is_lazy_across_pages(self):
        pdf = pikepdf.new()
        for _ in range(2):
            pdf.add_blank_page()
        scopes = pdf.content_scopes()
        assert next(scopes).page.index == 0
        # A change to a page not yet reached is seen
        pdf.pages[1].obj.Resources = Dictionary(
            XObject=Dictionary(Late=_form(pdf, Dictionary()))
        )
        assert _kinds(scopes) == ['page', 'form']

    def test_resources_shared_by_every_page_are_searched_once(self):
        # Every page uses one resource dictionary that lists every form. The
        # search must not list that dictionary again for each page.
        import time

        pdf = pikepdf.new()
        shared = pdf.make_indirect(Dictionary(XObject=Dictionary()))
        for i in range(20000):
            shared.XObject[f'/Fm{i}'] = _form(pdf, shared)
        for _ in range(2000):
            pdf.add_blank_page()
        for page in pdf.pages:
            page.obj.Resources = shared
        start = time.monotonic()
        count = sum(1 for _ in pdf.content_scopes())
        elapsed = time.monotonic() - start
        assert count == 22000
        # Listing 20000 forms for each of 2000 pages takes far longer
        assert elapsed < 10

    def test_kinds(self):
        pdf = pikepdf.new()
        pdf.add_blank_page()
        pdf.pages[0].obj.Resources = Dictionary(
            XObject=Dictionary(Fm=_form(pdf, Dictionary())),
            Pattern=Dictionary(P=_pattern(pdf, Dictionary())),
        )
        assert _kinds(pdf.content_scopes(kinds={'page', 'pattern'})) == [
            'page',
            'pattern',
        ]

    def test_unknown_kind_is_reported_when_called(self):
        pdf = pikepdf.new()
        with pytest.raises(ValueError, match='kind'):
            pdf.content_scopes(kinds={'nope'})

    def test_empty_document(self):
        assert list(pikepdf.new().content_scopes()) == []

    def test_fonts_of_a_real_file(self, resources):
        with pikepdf.open(resources / 'form_dd0293.pdf') as pdf:
            fonts = ObjectSet()
            for scope in pdf.content_scopes():
                if scope.resources is None:
                    continue
                for font in (scope.resources.get_dict(Name.Font) or {}).values():
                    if isinstance(font, Dictionary):
                        fonts.add(font)
            assert len(fonts) > 0
            kinds = set(_kinds(pdf.content_scopes()))
            assert {'page', 'appearance'} <= kinds

    def test_content_parses(self, resources):
        with pikepdf.open(resources / 'form_dd0293.pdf') as pdf:
            for scope in pdf.content_scopes():
                pikepdf.parse_content_stream(scope.content)


def test_appearance_stream_without_subtype():
    pdf, page = _blank()
    appearance = Stream(pdf, b'')
    page.obj.Annots = Array(
        [pdf.make_indirect(Dictionary(AP=Dictionary(N=appearance)))]
    )
    assert _kinds(page.content_scopes()) == ['page', 'appearance']


class TestFontCodes:
    """pikepdf.pdfa's scan of the codes shown in each font uses content scopes."""

    @staticmethod
    def _codes(pdf):
        from pikepdf.pdfa._fontuse import font_codes

        return font_codes(pdf)

    def test_text_in_every_kind_of_scope(self):
        pdf, page = _blank()
        font = pdf.make_indirect(Dictionary(Type=Name.Font, Subtype=Name.Type1))
        fonts = Dictionary(F0=font)

        def text(data: bytes) -> bytes:
            return b'BT /F0 12 Tf (' + data + b') Tj ET'

        form = _form(pdf, Dictionary(Font=fonts), text(b'b'))
        group = _form(pdf, Dictionary(Font=fonts), text(b'c'))
        appearance = _form(pdf, Dictionary(Font=fonts), text(b'd'))
        bare = _form(pdf, None, text(b'e'))  # uses the page's resources
        page.obj.Resources = Dictionary(
            Font=fonts,
            XObject=Dictionary(Fm0=form, Fm1=bare),
            ExtGState=Dictionary(GS0=Dictionary(SMask=Dictionary(G=group))),
        )
        page.obj.Contents = Stream(pdf, text(b'a'))
        page.obj.Annots = Array(
            [pdf.make_indirect(Dictionary(AP=Dictionary(N=appearance)))]
        )
        assert self._codes(pdf) == {font.objgen: set(b'abcde')}

    def test_unknown_font_makes_the_scan_incomplete(self):
        pdf, page = _blank()
        page.obj.Contents = Stream(pdf, b'BT /Missing 12 Tf (a) Tj ET')
        assert self._codes(pdf) is None

    def test_shared_resources(self):
        pdf, page = _blank()
        font = pdf.make_indirect(Dictionary(Type=Name.Font, Subtype=Name.Type1))
        shared = pdf.make_indirect(
            Dictionary(Font=Dictionary(F0=font), XObject=Dictionary())
        )
        for i in range(12):
            shared.XObject[f'/Fm{i}'] = _form(pdf, shared, b'BT /F0 9 Tf (x) Tj ET')
        page.obj.Resources = shared
        assert self._codes(pdf) == {font.objgen: {ord('x')}}


def test_kind_names_for_type_checkers_match_the_kinds():
    from typing import get_args

    from pikepdf._core import _ContentScopeKind

    assert list(get_args(pikepdf.ContentScopeKind)) == [
        kind.name for kind in _ContentScopeKind
    ]
