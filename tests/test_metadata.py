from pathlib import Path
from datetime import datetime, tzinfo, timezone, timedelta

import pytest
import pikepdf
from pikepdf import Pdf, Dictionary, Name, PasswordError
from pikepdf.models.metadata import (
    decode_pdf_date, encode_pdf_date,
    XMP_NS_DC, XMP_NS_PDF, XMP_NS_XMP,
    DateConverter
)

import defusedxml.ElementTree as ET

try:
    from libxmp import XMPMeta
except ImportError:
    XMPMeta = None

pytestmark = pytest.mark.filterwarnings('ignore:.*XMLParser.*:DeprecationWarning')


@pytest.fixture
def vera(resources):
    return Pdf.open(resources / 'veraPDF test suite 6-2-10-t02-pass-a.pdf')


@pytest.fixture
def graph(resources):
    return Pdf.open(resources / 'graph.pdf')


@pytest.fixture
def sandwich(resources):
    return Pdf.open(resources / 'sandwich.pdf')


@pytest.fixture
def trivial(resources):
    return Pdf.open(resources / 'pal-1bit-trivial.pdf')


def test_lowlevel(sandwich):
    meta = sandwich.open_metadata()
    assert meta._qname('pdf:Producer') == '{http://ns.adobe.com/pdf/1.3/}Producer'
    assert meta._prefix_from_uri('{http://ns.adobe.com/pdf/1.3/}Producer') == 'pdf:Producer'
    assert 'pdf:Producer' in meta
    assert '{http://ns.adobe.com/pdf/1.3/}Producer' in meta
    assert 'xmp:CreateDate' in meta
    assert meta['xmp:ModifyDate'].startswith('2017')
    assert len(meta) > 0
    assert meta['dc:title'] == 'Untitled'

    assert 'pdf:invalid' not in meta
    assert '{http://ns.adobe.com/pdf/1.3/}invalid' not in meta
    with pytest.raises(TypeError):
        assert ['hi'] in meta

    with pytest.raises(KeyError):
        meta['dc:invalid']
    with pytest.raises(KeyError):
        meta['{http://ns.adobe.com/pdf/1.3/}invalid']
    with pytest.raises(KeyError):
        meta['{http://invalid.com/ns/}doublyinvalid']


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

    print(trivial.Root.Metadata.read_bytes())

    with trivial.open_metadata(update_docinfo=False
    ) as xmp:
        assert 'pikepdf' in xmp['pdf:Producer']
        assert 'xmp:MetadataDate' in xmp


def test_update_docinfo(vera):
    with vera.open_metadata(set_pikepdf_as_editor=False, update_docinfo=True) as xmp:
        pass
    assert xmp['pdf:Producer'] == vera.docinfo[Name.Producer]
    assert xmp['xmp:CreatorTool'] == vera.docinfo[Name.Creator]
    assert xmp['dc:creator'][0] == vera.docinfo[Name.Author]

    # Test delete propagation
    with vera.open_metadata(set_pikepdf_as_editor=False, update_docinfo=True) as xmp:
        del xmp['dc:creator']
    assert 'dc:creator' not in xmp
    assert Name.Author not in vera.docinfo


@pytest.mark.parametrize('filename', list((Path(__file__).parent / 'resources').glob('*.pdf')))
def test_roundtrip(filename):
    try:
        pdf = Pdf.open(filename)
    except PasswordError:
        return
    with pdf.open_metadata() as xmp:
        for k in xmp.keys():
            if not 'Date' in k:
                xmp[k] = 'A'


def test_build_metadata(trivial, graph, outdir):
    with trivial.open_metadata(set_pikepdf_as_editor=False) as xmp:
        xmp.load_from_docinfo(graph.docinfo)
    trivial.save(outdir / 'tmp.pdf')

    pdf = pikepdf.open(outdir / 'tmp.pdf')
    assert pdf.Root.Metadata.Type == Name.Metadata
    assert pdf.Root.Metadata.Subtype == Name.XML
    with pdf.open_metadata(set_pikepdf_as_editor=False) as xmp:
        assert 'pdf:Producer' not in xmp
        xmp_date = xmp['xmp:CreateDate']
        docinfo_date = decode_pdf_date(trivial.docinfo[Name.CreationDate])
        assert xmp_date == docinfo_date.isoformat()


def test_python_xmp_validate_add(trivial):
    with trivial.open_metadata() as xmp:
        xmp['dc:creator'] = ['Bob', 'Doug']
        xmp['dc:title'] = 'Title'
        xmp['dc:publisher'] = {'Mackenzie'}

    xmp_str = str(xmp).replace('\n', '')
    assert '<dc:creator><rdf:Seq><rdf:li>Bob</rdf:li><rdf:li>Doug</rdf:li>' in xmp_str
    assert '<dc:publisher><rdf:Bag><rdf:li>Mackenzie</rdf:li>' in xmp_str

    if not XMPMeta:
        pytest.skip(msg='needs libxmp')

    xmpmeta = XMPMeta(xmp_str=str(xmp))
    DC = XMP_NS_DC
    assert xmpmeta.does_array_item_exist(DC, 'creator', 'Bob')
    assert xmpmeta.does_array_item_exist(DC, 'creator', 'Doug')
    assert xmpmeta.get_localized_text(DC, 'title', None, 'x-default') == 'Title'
    assert xmpmeta.does_array_item_exist(DC, 'publisher', 'Mackenzie')


def test_python_xmp_validate_change_list(graph):
    with graph.open_metadata() as xmp:
        assert 'dc:creator' in xmp
        xmp['dc:creator'] = ['Dobby', 'Kreacher']

    xmp_str = str(xmp).replace('\n', '')

    if not XMPMeta:
        pytest.skip(msg='needs libxmp')
    xmpmeta = XMPMeta(xmp_str=str(xmp))
    DC = XMP_NS_DC
    assert xmpmeta.does_array_item_exist(DC, 'creator', 'Dobby')
    assert xmpmeta.does_array_item_exist(DC, 'creator', 'Kreacher')


def test_python_xmp_validate_change(sandwich):
    with sandwich.open_metadata() as xmp:
        assert 'xmp:CreatorTool' in xmp
        xmp['xmp:CreatorTool'] = 'Creator'  # Exists as a xml tag text
        xmp['pdf:Producer'] = 'Producer'  # Exists as a tag node

    xmp_str = str(xmp).replace('\n', '')

    if not XMPMeta:
        pytest.skip(msg='needs libxmp')
    xmpmeta = XMPMeta(xmp_str=str(xmp))
    assert xmpmeta.does_property_exist(XMP_NS_XMP, 'CreatorTool')
    assert xmpmeta.does_property_exist(XMP_NS_PDF, 'Producer')


def test_decode_pdf_date():
    VALS = [
        ('20160220040559', datetime(2016, 2, 20, 4, 5, 59)),
        ("20180101010101Z00'00'", datetime(2018, 1, 1, 1, 1, 1, tzinfo=timezone.utc)),
        ("20180101010101Z", datetime(2018, 1, 1, 1, 1, 1, tzinfo=timezone.utc)),
        ("20180101010101+0000", datetime(2018, 1, 1, 1, 1, 1, tzinfo=timezone.utc)),
        ("20180101010101+0100", datetime(2018, 1, 1, 1, 1, 1, tzinfo=timezone(timedelta(hours=1)))),
    ]
    for s, d in VALS:
        assert decode_pdf_date(s) == d


def test_date_docinfo_from_xmp():
    VALS = [
        ('2018-12-04T03:02:01', "20181204030201"),
        ('2018-12-15T07:36:43Z', "20181215073643+00'00'"),
        ('2018-12-04T03:02:01-01:00', "20181204030201-01'00'"),
    ]
    for xmp_val, docinfo_val in VALS:
        assert DateConverter.docinfo_from_xmp(xmp_val) == docinfo_val


def test_bad_char_rejection(trivial):
    with trivial.open_metadata() as xmp:
        xmp['dc:description'] = 'Bad characters \x00 \x01 \x02'
        xmp['dc:creator'] = ['\ue001bad', '\ufff0bad']
    ET.fromstring(str(xmp))
