# SPDX-FileCopyrightText: 2022 James R. Barlow
# SPDX-License-Identifier: CC0-1.0

from __future__ import annotations

import copy

import pytest
from conftest import needs_libqpdf_v

from pikepdf import (
    Array,
    ContentStreamInlineImage,
    Dictionary,
    Matrix,
    Name,
    Object,
    Operator,
    Page,
    Pdf,
    Rectangle,
    parse_content_stream,
)

# pylint: disable=redefined-outer-name


@pytest.fixture
def graph(resources):
    with Pdf.open(resources / 'graph.pdf') as pdf:
        yield pdf


@pytest.fixture
def fourpages(resources):
    with Pdf.open(resources / 'fourpages.pdf') as pdf:
        yield pdf


@pytest.fixture
def graph_page(graph):
    return graph.pages[0]


def test_page_boxes(graph_page):
    page = graph_page
    assert page.mediabox == page.cropbox == page.trimbox == page.artbox == page.bleedbox
    page.mediabox = [
        page.mediabox[0],
        page.mediabox[1],
        page.mediabox[2],
        page.mediabox[3],
    ]
    inset = 10
    page.bleedbox = [inset, inset, page.mediabox[2] - inset, page.mediabox[3] - inset]
    inset = 20
    page.trimbox = [inset, inset, page.mediabox[2] - inset, page.mediabox[3] - inset]
    inset = 30
    page.cropbox = Array(
        [inset, inset, page.mediabox[2] - inset, page.mediabox[3] - inset]
    )
    inset = 40
    page.artbox = Rectangle(
        inset, inset, page.mediabox[2] - inset, page.mediabox[3] - inset
    )

    assert page.mediabox != page.bleedbox
    assert page.mediabox != page.artbox
    assert page.mediabox != page.cropbox
    assert page.mediabox != page.trimbox


def test_invalid_boxes(graph_page):
    page = graph_page
    with pytest.raises(ValueError):
        page.mediabox = 'hi'
    with pytest.raises(ValueError):
        page.mediabox = [0, 0, 0]
    with pytest.raises(ValueError):
        page.mediabox = [0, 0, 0, 0, 0, 0]


def test_page_repr(graph_page):
    r = repr(graph_page)
    assert r.startswith('<pikepdf.Page')
    assert '(Type="/Page")' not in r


class TestAddResource:
    def _make_simple_dict(self):
        return Dictionary(Type=Name.XObject, Subtype=Name.Image, Width=1, Height=1)

    def test_basic(self, graph_page):
        d = self._make_simple_dict()

        with pytest.raises(ValueError, match="already exists"):
            graph_page.add_resource(d, Name.XObject, Name.Im0, replace_existing=False)

        res = graph_page.add_resource(d, Name.XObject, Name.Im0, replace_existing=True)
        assert graph_page.resources.XObject[res].Width == 1

        res2 = graph_page.add_resource(d, Name.XObject, prefix='Im')
        assert str(res2).startswith("/Im")
        assert graph_page.resources.XObject[res2].Height == 1

    def test_resources_exists_but_wrong_type(self, graph_page):
        d = self._make_simple_dict()

        del graph_page.obj.Resources
        graph_page.obj.Resources = Name.Dummy
        with pytest.raises(TypeError, match='exists but is not a dictionary'):
            graph_page.add_resource(d, Name.XObject, Name.Im0, replace_existing=False)

    def test_create_resource_dict_if_not_exists(self, graph_page):
        d = self._make_simple_dict()

        del graph_page.obj.Resources
        graph_page.add_resource(d, Name.XObject, Name.Im0, replace_existing=False)
        assert Name.Resources in graph_page.obj

    def test_name_and_prefix(self, graph_page):
        d = self._make_simple_dict()

        with pytest.raises(ValueError, match="one of"):
            graph_page.add_resource(d, Name.XObject, name=Name.X, prefix='y')

    def test_unrecognized_object_not_disturbed(self, graph_page):
        d = self._make_simple_dict()

        graph_page.obj.Resources.InvalidItem = Array([42])
        graph_page.add_resource(d, Name.Pattern)
        assert Name.InvalidItem in graph_page.obj.Resources


def test_add_unowned_page():  # issue 174
    pdf = Pdf.new()
    d = Dictionary(Type=Name.Page)
    pdf.pages.append(Page(d))


def test_failed_add_page_cleanup():
    pdf = Pdf.new()
    d = Dictionary(Type=Name.NotAPage)
    num_objects = len(pdf.objects)
    with pytest.raises(TypeError, match="pikepdf.Page"):
        pdf.pages.append(d)
    assert len(pdf.pages) == 0

    # If we fail to add a new page, confirm we did not create a new object
    assert len(pdf.objects) == num_objects, "A dangling page object was created"
    assert pdf.objects[-1] is not None, "Left a stale object behind without deleting"

    # But we'd better not delete an existing object...
    d2 = pdf.make_indirect(Dictionary(Type=Name.StillNotAPage))
    with pytest.raises(TypeError, match="pikepdf.Page"):
        pdf.pages.append(d2)
    assert len(pdf.pages) == 0

    assert d2.same_owner_as(pdf.Root)


def test_formx(graph, outpdf):
    formx = graph.pages[0].as_form_xobject()
    graph.add_blank_page()
    new_page = graph.pages[-1]
    formx_placed_name = new_page.add_resource(formx, Name.XObject)
    cs = new_page.calc_form_xobject_placement(
        formx, formx_placed_name, Rectangle(0, 0, 200, 200)
    )
    assert bytes(formx_placed_name) in cs
    new_page.obj.Contents = graph.make_stream(cs)
    graph.save(outpdf)

    assert formx_placed_name in new_page.form_xobjects
    assert new_page.form_xobjects[formx_placed_name] == formx


def test_fourpages_to_4up(fourpages, graph, outpdf):
    pdf = Pdf.new()
    pdf.add_blank_page(page_size=(1000, 1000))
    page = pdf.pages[0]

    pdf.pages.extend(fourpages.pages)

    # Keep explicit Page(pdf.pages[..]) here
    page.add_overlay(pdf.pages[1], Rectangle(0, 500, 500, 1000))
    page.add_overlay(Page(pdf.pages[2]), Rectangle(500, 500, 1000, 1000))
    page.add_overlay(Page(pdf.pages[3]).as_form_xobject(), Rectangle(0, 0, 500, 500))
    page.add_underlay(pdf.pages[4], Rectangle(500, 0, 1000, 500))

    page.add_underlay(graph.pages[0].obj)

    with pytest.raises(TypeError):
        page.add_overlay(Dictionary(Key=123))

    del pdf.pages[1:]

    pdf.save(outpdf)


def _simple_interpret_content_stream(page: Page | Object):
    ctm = Matrix()
    stack: list[Matrix] = []
    for instruction in parse_content_stream(page, operators='q Q cm Do'):
        if isinstance(instruction, ContentStreamInlineImage):
            continue
        operands, op = instruction.operands, instruction.operator
        if op == Operator('q'):
            stack.append(ctm)
        elif op == Operator('Q'):
            ctm = stack.pop()
        elif op == Operator('cm'):
            ctm = Matrix(operands) @ ctm
        elif op == Operator('Do'):
            xobj_name = operands[0]
            yield (xobj_name, ctm)


def test_push_stack(fourpages, outpdf):
    pdf = Pdf.new()
    pdf.add_blank_page(page_size=(1000, 1000))
    page = pdf.pages[0]

    pdf.pages.extend(fourpages.pages)

    page.Contents = pdf.make_stream(
        b"0.4 G\n"
        b"0 500 500 1000 re s\n"
        b"500 500 1000 1000 re s\n"
        b"-1 0 0 1 500 0 cm\n"
    )

    xobj1 = page.add_overlay(
        pdf.pages[1], Rectangle(0, 500, 500, 1000), push_stack=False
    )
    xobj2 = page.add_overlay(
        pdf.pages[2], Rectangle(500, 500, 1000, 1000), push_stack=True
    )

    draw_events = _simple_interpret_content_stream(page)
    # First page should be mirrored horizontally since stack was not pushed
    xobj, ctm = next(draw_events)
    assert xobj == xobj1
    assert ctm.a < 0 and ctm.d > 0, "Not horizontally mirrored as expected"

    # Second page should be in upper right corner, properly positioned for a 4-up
    xobj, ctm = next(draw_events)
    assert xobj == xobj2
    assert ctm.e >= 500 and ctm.f >= 500

    # Test requires visual confirmation
    del pdf.pages[1:]
    pdf.save(outpdf)


def test_page_equal(fourpages, graph):
    assert fourpages.pages[0] == fourpages.pages[0]
    assert fourpages.pages[0] != fourpages.pages[1]
    assert graph.pages[0] != fourpages.pages[2]

    graph.pages.append(graph.pages[0])
    assert graph.pages[1] == graph.pages[0]
    assert copy.copy(graph.pages[1]) == graph.pages[0]

    assert graph.pages[0] != "dissimilar type"


def test_cant_hash_page(graph):
    with pytest.raises(TypeError, match="unhashable"):
        hash(graph.pages[0])


def test_contents_add(graph):
    graph.pages[0].contents_add(b'q Q', prepend=True)

    new_cs = graph.make_stream(b'q Q')
    graph.pages[0].contents_add(new_cs, prepend=False)

    graph.pages[0].contents_coalesce()
    assert graph.pages[0].Contents.read_bytes().startswith(b'q Q')
    assert graph.pages[0].Contents.read_bytes().endswith(b'q Q')


def test_remove_unrefed(graph):
    assert len(graph.pages[0].Resources.XObject) != 0
    graph.pages[0].Contents = graph.make_stream(b'')
    graph.pages[0].remove_unreferenced_resources()
    assert len(graph.pages[0].Resources.XObject) == 0


def test_page_attrs(graph):
    # Test __getattr__
    assert isinstance(graph.pages[0].Resources, Dictionary)

    del graph.pages[0].Resources
    with pytest.raises(
        AttributeError, match=r"can't delete|property( '')? of 'Page' object has no deleter"
    ):
        del graph.pages[0].obj
    del graph.pages[0]['/Contents']

    assert Name.Contents not in graph.pages[0] and Name.Resources not in graph.pages[0]


def test_block_make_indirect_page(graph: Pdf):
    with pytest.raises(TypeError, match='implicitly'):
        graph.make_indirect(graph.pages[0])

    assert isinstance(graph.make_indirect(graph.pages[0].obj), Object)


@pytest.fixture
def formxobject_pdf(resources):
    with Pdf.open(resources / 'formxobject.pdf') as pdf:
        yield pdf


def test_flatten_rotation(graph_page):
    graph_page.rotate(90, relative=True)
    assert graph_page.obj.get('/Rotate', 0) == 90
    graph_page.flatten_rotation()
    assert '/Rotate' not in graph_page.obj


def test_get_matrix_for_transformations(graph_page):
    m = graph_page.get_matrix_for_transformations()
    assert isinstance(m, Matrix)
    graph_page.rotate(90, relative=True)
    rotated = graph_page.get_matrix_for_transformations()
    assert rotated != m
    # invert should differ from the non-inverted form for a rotated page
    assert graph_page.get_matrix_for_transformations(invert=True) != rotated


def test_get_matrix_for_form_xobject_placement(graph, graph_page):
    fo = graph_page.as_form_xobject()
    blank = graph.add_blank_page(page_size=(500, 500))
    name = blank.add_resource(fo, Name.XObject)
    m = blank.get_matrix_for_form_xobject_placement(fo, Rectangle(0, 0, 250, 250))
    assert isinstance(m, Matrix)
    # The companion content-generating method should also succeed
    assert blank.calc_form_xobject_placement(
        fo,
        name,
        Rectangle(0, 0, 250, 250),
        invert_transformations=True,
        allow_shrink=True,
        allow_expand=False,
    )


def test_copy_annotations(resources):
    with Pdf.open(resources / 'form.pdf') as src:
        dst = Pdf.new()
        dst.add_blank_page(page_size=(612, 792))
        assert '/Annots' not in dst.pages[0].obj
        dst.pages[0].copy_annotations(src.pages[0], Matrix())
        assert '/Annots' in dst.pages[0].obj
        assert len(dst.pages[0].obj.Annots) == len(src.pages[0].obj.Annots)


def test_copy_annotations_default_matrix(resources):
    with Pdf.open(resources / 'form.pdf') as src:
        dst = Pdf.new()
        dst.add_blank_page(page_size=(612, 792))
        dst.pages[0].copy_annotations(src.pages[0])
        assert '/Annots' in dst.pages[0].obj


def test_get_images_recursive_finds_nested(formxobject_pdf):
    page = formxobject_pdf.pages[0]
    flat = page.get_images(recursive=False)
    recursive = page.get_images()  # default recursive=True
    # This file draws its image only through a nested form XObject
    assert len(flat) == 0
    assert len(recursive) >= 1


def test_get_images_matches_legacy_when_flat(graph_page):
    with pytest.warns(DeprecationWarning):
        legacy = dict(graph_page.images)
    assert dict(graph_page.get_images(recursive=False)) == legacy


def test_images_property_deprecated(graph_page):
    with pytest.warns(DeprecationWarning, match='get_images'):
        graph_page.images


class TestRotation:
    def test_rotation_default_zero(self, graph_page):
        assert graph_page.rotation == 0

    def test_rotation_set_absolute(self, graph_page):
        graph_page.rotation = 90
        assert graph_page.rotation == 90
        assert graph_page.obj.Rotate == 90

    def test_rotation_normalizes_negative(self, graph_page):
        graph_page.obj.Rotate = -90
        assert graph_page.rotation == 270

    def test_rotation_normalizes_over_360(self, graph_page):
        graph_page.obj.Rotate = 450
        assert graph_page.rotation == 90

    def test_rotation_resolves_inherited_attribute(self, graph):
        page = graph.pages[0]
        if Name.Rotate in page.obj:
            del page.obj.Rotate
        # /Rotate is inheritable; set it on the page tree node, not the page
        graph.Root.Pages.Rotate = 90
        assert Name.Rotate not in graph.pages[0].obj
        assert graph.pages[0].rotation == 90

    def test_rotate_keyword_relative(self, graph_page):
        graph_page.rotation = 90
        graph_page.rotate(90, relative=True)
        assert graph_page.rotation == 180

    def test_rotate_default_is_absolute(self, graph_page):
        graph_page.rotation = 90
        graph_page.rotate(180)  # no relative -> set absolute rotation
        assert graph_page.rotation == 180

    def test_rotate_positional_relative_deprecated(self, graph_page):
        with pytest.warns(DeprecationWarning, match='keyword'):
            graph_page.rotate(90, True)
        assert graph_page.rotation == 90

    def test_rotate_keyword_emits_no_warning(self, graph_page, recwarn):
        graph_page.rotate(90, relative=True)
        assert not any(issubclass(w.category, DeprecationWarning) for w in recwarn)

    @needs_libqpdf_v(
        '12.4.0',
        reason=(
            'qpdf normalizes a negative /Rotate when baking it into a form '
            'XObject /Matrix only after 12.4.0 (qpdf commit 67b042cd)'
        ),
    )
    def test_negative_rotation_overlay_matches_positive(self, graph_page):
        # Regression test for #717: a page rotated -90 must produce the same
        # form XObject (and therefore the same add_overlay placement) as a page
        # rotated 270, since they are the same rotation. On qpdf without the fix,
        # -90 was not normalized to [0, 360) and produced an unrotated /Matrix.
        graph_page.obj.Rotate = -90
        matrix_neg = list(graph_page.as_form_xobject().Matrix)

        graph_page.obj.Rotate = 270
        matrix_pos = list(graph_page.as_form_xobject().Matrix)

        assert matrix_neg == matrix_pos
