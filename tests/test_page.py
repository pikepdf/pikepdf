import pytest

import pikepdf

Dictionary = pikepdf.Dictionary
Name = pikepdf.Name


@pytest.fixture
def graph(resources):
    return pikepdf.open(resources / 'graph.pdf')


@pytest.fixture
def graph_page(graph):
    return pikepdf.Page(graph.pages[0])


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

    page.cropbox = pikepdf.Array([0, 0, 50, 50])


def test_invalid_boxes(graph_page):
    page = graph_page
    with pytest.raises(ValueError):
        page.mediabox = 'hi'
    with pytest.raises(ValueError):
        page.mediabox = [0, 0, 0]
    with pytest.raises(ValueError):
        page.mediabox = [0, 0, 0, 0, 0, 0]


def test_add_resource(graph_page):
    d = Dictionary(Type=Name.XObject, Subtype=Name.Image, Width=1, Height=1)

    with pytest.raises(ValueError, match="already exists"):
        graph_page.add_resource(d, Name.XObject, Name.Im0, replace_existing=False)

    res = graph_page.add_resource(d, Name.XObject, Name.Im0, replace_existing=True)
    assert graph_page.resources.XObject[res].Width == 1

    res2 = graph_page.add_resource(d, Name.XObject, prefix='Im')
    assert str(res2).startswith("/Im")
    assert graph_page.resources.XObject[res2].Height == 1


def test_add_unowned_page():  # issue 174
    pdf = pikepdf.new()
    d = pikepdf.Dictionary(Type=pikepdf.Name.Page)
    pdf.pages.append(d)


def test_failed_add_page_cleanup():
    pdf = pikepdf.new()
    d = pikepdf.Dictionary(Type=pikepdf.Name.NotAPage)
    num_objects = len(pdf.objects)
    with pytest.raises(TypeError, match="only pages can be inserted"):
        pdf.pages.append(d)
    assert len(pdf.pages) == 0

    # If we fail to add a new page, we expect one new null object handle to be
    # be added (since QPDF does not remove the object outright)
    assert len(pdf.objects) == num_objects + 1, "QPDF semantics changed"
    assert pdf.objects[-1] is None, "Left a stale object behind without deleting"

    # But we'd better not delete an existing object...
    d2 = pdf.make_indirect(pikepdf.Dictionary(Type=pikepdf.Name.StillNotAPage))
    with pytest.raises(TypeError, match="only pages can be inserted"):
        pdf.pages.append(d2)
    assert len(pdf.pages) == 0

    assert d2.same_owner_as(pdf.Root)
