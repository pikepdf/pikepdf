# SPDX-FileCopyrightText: 2022 James R. Barlow
# SPDX-License-Identifier: CC0-1.0

from __future__ import annotations

import copy

import pytest

from pikepdf import (
    Array,
    ContentStreamInlineImage,
    Dictionary,
    Name,
    Object,
    Operator,
    Page,
    Pdf,
    PdfMatrix,
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
    assert page.mediabox == page.cropbox == page.trimbox
    page.cropbox = [0, 0, page.mediabox[2] - 100, page.mediabox[3] - 100]
    page.mediabox = [
        page.mediabox[0] - 50,
        page.mediabox[1] - 50,
        page.mediabox[2] + 50,
        page.mediabox[3] + 50,
    ]
    page.trimbox = [50, 50, page.mediabox[2] - 50, page.mediabox[3] - 50]

    assert page.mediabox != page.cropbox
    assert page.cropbox != page.mediabox

    page.cropbox = Array([0, 0, 50, 50])


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
    pdf.pages.append(d)


def test_failed_add_page_cleanup():
    pdf = Pdf.new()
    d = Dictionary(Type=Name.NotAPage)
    num_objects = len(pdf.objects)
    with pytest.raises(TypeError, match="only pages can be inserted"):
        pdf.pages.append(d)
    assert len(pdf.pages) == 0

    # If we fail to add a new page, we expect one new null object handle to be
    # be added (since QPDF does not remove the object outright)
    assert len(pdf.objects) == num_objects + 1, "QPDF semantics changed"
    assert pdf.objects[-1] is None, "Left a stale object behind without deleting"

    # But we'd better not delete an existing object...
    d2 = pdf.make_indirect(Dictionary(Type=Name.StillNotAPage))
    with pytest.raises(TypeError, match="only pages can be inserted"):
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
    ctm = PdfMatrix.identity()
    stack: list[PdfMatrix] = []
    for instruction in parse_content_stream(page, operators='q Q cm Do'):
        if isinstance(instruction, ContentStreamInlineImage):
            continue
        operands, op = instruction.operands, instruction.operator
        if op == Operator('q'):
            stack.append(ctm)
        elif op == Operator('Q'):
            ctm = stack.pop()
        elif op == Operator('cm'):
            ctm = PdfMatrix(operands) @ ctm
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
        AttributeError, match=r"can't delete|property of 'Page' object has no deleter"
    ):
        del graph.pages[0].obj
    del graph.pages[0]['/Contents']

    assert Name.Contents not in graph.pages[0] and Name.Resources not in graph.pages[0]


def test_block_make_indirect_page(graph: Pdf):
    with pytest.raises(TypeError, match='implicitly'):
        graph.make_indirect(graph.pages[0])

    assert isinstance(graph.make_indirect(graph.pages[0].obj), Object)
