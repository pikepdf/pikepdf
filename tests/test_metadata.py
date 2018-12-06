import pytest
from pathlib import Path
import pikepdf
from pikepdf import Pdf, Dictionary, Name, PasswordError
from pikepdf.models.metadata import decode_pdf_date, encode_pdf_date


@pytest.fixture
def vera(resources):
    return Pdf.open(resources / 'veraPDF test suite 6-2-10-t02-pass-a.pdf')


@pytest.fixture
def graph(resources):
    return Pdf.open(resources / 'graph.pdf')


@pytest.fixture
def trivial(resources):
    return Pdf.open(resources / 'pal-1bit-trivial.pdf')


def test_no_info(vera, outdir):
    assert vera.trailer.get('/Info') is None, 'need a test file with no /Info'

    assert len(vera.docinfo) == 0
    creator = 'pikepdf test suite'
    vera.docinfo['/Creator'] = creator
    assert vera.docinfo.is_indirect, "/Info must be an indirect object"
    vera.save(outdir / 'out.pdf')

    new = Pdf.open(outdir / 'out.pdf')
    assert new.docinfo['/Creator'] == creator


def test_update_info(graph, outdir):
    new_title = '我敢打赌，你只是想看看这意味着什么'
    graph.docinfo['/Title'] = new_title
    graph.save(outdir / 'out.pdf')

    new = Pdf.open(outdir / 'out.pdf')
    assert new.docinfo['/Title'] == new_title
    assert graph.docinfo['/Author'] == new.docinfo['/Author']

    with pytest.raises(ValueError):
        new.docinfo = Dictionary({'/Keywords': 'bob'})

    new.docinfo = graph.make_indirect(Dictionary({'/Keywords': 'bob'}))
    assert new.docinfo.is_indirect, "/Info must be an indirect object"


def test_copy_info(vera, graph, outdir):
    vera.docinfo = vera.copy_foreign(graph.docinfo)
    assert vera.docinfo.is_indirect, "/Info must be an indirect object"
    vera.save(outdir / 'out.pdf')


def test_add_new_xmp_and_mark(trivial):
    with trivial.open_metadata(
        set_pikepdf_as_editor=False, update_docinfo=False
    ) as xmp_view:
        assert not xmp_view

    with trivial.open_metadata(update_docinfo=False
    ) as xmp:
        assert not xmp  # No changes at this point
    del xmp

    with trivial.open_metadata(update_docinfo=False
    ) as xmp:
        assert 'pikepdf' in xmp['pdf:Producer']
        assert 'xmp:MetadataDate' in xmp


def test_update_docinfo(vera):
    with vera.open_metadata(set_pikepdf_as_editor=False, update_docinfo=True) as xmp:
        pass
    assert xmp['pdf:Producer'] == vera.docinfo[Name.Producer]
    assert xmp['xmp:CreatorTool'] == vera.docinfo[Name.Creator]
    assert xmp['dc:creator'][0] == vera.docinfo[Name.Authors]

    # Test delete propagation
    with vera.open_metadata(set_pikepdf_as_editor=False, update_docinfo=True) as xmp:
        del xmp['dc:creator']
    assert Name.Authors not in vera.docinfo


@pytest.mark.filterwarnings('ignore:XMP metadata key')
@pytest.mark.parametrize('filename', list((Path(__file__).parent / 'resources').glob('*.pdf')))
def test_roundtrip(filename):
    try:
        pdf = Pdf.open(filename)
    except PasswordError:
        return
    with pdf.open_metadata() as xmp:
        xmp._changed = set(k for k in xmp._records.keys() if '[' not in k)


def test_build_metadata(trivial, outdir):
    with trivial.open_metadata(set_pikepdf_as_editor=False) as xmp:
        xmp.load_from_docinfo(trivial.docinfo)
    trivial.save(outdir / 'tmp.pdf')

    pdf = pikepdf.open(outdir / 'tmp.pdf')
    assert pdf.Root.Metadata.Type == Name.Metadata
    assert pdf.Root.Metadata.Subtype == Name.XML
    with pdf.open_metadata(set_pikepdf_as_editor=False) as xmp:
        assert xmp['pdf:Producer'] == trivial.docinfo[Name.Producer]
        xmp_date = xmp['xmp:CreateDate']
        docinfo_date = decode_pdf_date(trivial.docinfo[Name.CreationDate])
        assert xmp_date == docinfo_date.isoformat()
