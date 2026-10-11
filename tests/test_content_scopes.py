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
        assert isinstance(scope.content, Page)
        assert scope.content.obj.is_same_object_as(page)
        assert scope.page.obj.is_same_object_as(page)
        assert scope.resources.is_same_object_as(page.get_resources())

    def test_is_lazy(self):
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
        _pdf, page = _blank()
        page.obj.Resources = resources
        assert _kinds(page.content_scopes()) == ['page']

    @pytest.mark.parametrize(
        'annots',
        [
            Name.Bogus,
            Array([1, Name.No]),
            Array([Dictionary(AP=3)]),
            Array([Dictionary(AP=Dictionary(N=4, D=Dictionary(On=5)))]),
        ],
    )
    def test_malformed_annotations(self, annots):
        _pdf, page = _blank()
        page.obj.Annots = annots
        assert _kinds(page.content_scopes()) == ['page']

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

    def test_form_without_resources_uses_those_of_its_context(self):
        pdf, page = _blank()
        form = _form(pdf)
        page.obj.Resources = Dictionary(XObject=Dictionary(Fm0=form))
        scopes = list(page.content_scopes())
        assert _kinds(scopes) == ['page', 'form']
        assert scopes[1].resources.is_same_object_as(page.obj.Resources)

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

    def test_type3_glyphs_without_font_resources_use_the_context(self):
        pdf, page = _blank()
        font = _type3(pdf, 1)
        page.obj.Resources = Dictionary(Font=Dictionary(F0=font))
        scopes = list(page.content_scopes())
        assert _kinds(scopes) == ['page', 'glyph']
        assert scopes[1].resources.is_same_object_as(page.obj.Resources)

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
        inner = _form(pdf, Dictionary())
        outer = _form(pdf, Dictionary(XObject=Dictionary(Inner=inner)))
        scopes = list(Page(outer).content_scopes())
        assert _kinds(scopes) == ['form', 'form']
        assert isinstance(scopes[0].content, Stream)
        assert scopes[0].content.is_same_object_as(outer)
        assert scopes[0].page.obj.is_same_object_as(outer)


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

    def test_stream_without_resources_once_per_context(self):
        pdf, page = _blank()
        bare = _form(pdf)  # uses the resources of whatever draws it
        first = _form(pdf, Dictionary(XObject=Dictionary(Bare=bare)))
        second = _form(pdf, Dictionary(XObject=Dictionary(Bare=bare)))
        third = _form(pdf, first.Resources)
        page.obj.Resources = Dictionary(XObject=Dictionary(A=first, B=second, C=third))
        scopes = [s for s in page.content_scopes() if s.content.objgen == bare.objgen]
        assert len(scopes) == 2
        assert not scopes[0].resources.is_same_object_as(scopes[1].resources)

    def test_deeply_nested(self):
        pdf, page = _blank()
        form = _form(pdf, Dictionary())
        for _ in range(3000):
            form = _form(pdf, Dictionary(XObject=Dictionary(Fm=form)))
        page.obj.Resources = Dictionary(XObject=Dictionary(Fm=form))
        assert len(list(page.content_scopes())) == 3002

    def test_seen_shared_between_pages(self):
        pdf, first = _blank()
        pdf.add_blank_page()
        second = pdf.pages[1]
        shared = _form(pdf, Dictionary())
        own = _form(pdf, Dictionary())
        first.obj.Resources = Dictionary(XObject=Dictionary(Shared=shared))
        second.obj.Resources = Dictionary(XObject=Dictionary(Shared=shared, Own=own))
        seen = ObjectSet()
        assert _kinds(first.content_scopes(seen=seen)) == ['page', 'form']
        scopes = list(second.content_scopes(seen=seen))
        assert _kinds(scopes) == ['page', 'form']
        assert scopes[1].content.is_same_object_as(own)
        # A page already reported is searched again but not reported again
        assert _kinds(second.content_scopes(seen=seen)) == []

    def test_context_dependent_scope_remembered_across_pages(self):
        pdf, first = _blank()
        pdf.add_blank_page()
        second = pdf.pages[1]
        shared = pdf.make_indirect(Dictionary(XObject=Dictionary(Bare=_form(pdf))))
        first.obj.Resources = shared
        second.obj.Resources = shared
        seen = ObjectSet()
        assert _kinds(first.content_scopes(seen=seen)) == ['page', 'form']
        assert _kinds(second.content_scopes(seen=seen)) == ['page']


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

    def test_unlisted_kinds_are_not_entered(self, page):
        # The forms inside the appearance stream and the pattern are not found
        assert _kinds(page.content_scopes(kinds={'page', 'form'})) == ['page', 'form']

    def test_entering_more_kinds_finds_more_forms(self, page):
        kinds = _kinds(page.content_scopes(kinds=['page', 'form', 'appearance']))
        assert sorted(kinds) == ['appearance', 'form', 'form', 'page']

    def test_page_is_searched_even_when_not_reported(self, page):
        assert _kinds(page.content_scopes(kinds={'form'})) == ['form']
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
