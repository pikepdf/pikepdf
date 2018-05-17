import pytest
from pikepdf import Pdf


@pytest.fixture
def vera(resources):
    pdf = Pdf.open(resources / 'veraPDF test suite 6-2-10-t02-pass-a.pdf')
    return pdf


@pytest.fixture
def graph(resources):
    return Pdf.open(resources / 'graph.pdf')


def test_no_info(vera, outdir):
    assert vera.trailer.get('/Info') is None, 'need a test file with no /Info'

    assert len(vera.metadata) == 0
    creator = 'pikepdf test suite'
    vera.metadata['/Creator'] = creator
    vera.save(outdir / 'out.pdf')

    new = Pdf.open(outdir / 'out.pdf')
    assert new.metadata['/Creator'] == creator


def test_update_info(graph, outdir):
    new_title = '我敢打赌，你只是想看看这意味着什么'
    graph.metadata['/Title'] = new_title
    graph.save(outdir / 'out.pdf')

    new = Pdf.open(outdir / 'out.pdf')
    assert new.metadata['/Title'] == new_title
    assert graph.metadata['/Author'] == new.metadata['/Author']


def test_copy_info(vera, graph, outdir):
    vera.metadata = vera.copy_foreign(graph.metadata)
    vera.save(outdir / 'out.pdf')
