import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest
from hypothesis import assume, example, given, settings
from hypothesis import strategies as st
from hypothesis.strategies import integers
from lxml.etree import XMLSyntaxError

import pikepdf
from pikepdf import Dictionary, Name, PasswordError, Pdf, Stream
from pikepdf.models.metadata import (
    XMP_NS_DC,
    XMP_NS_PDF,
    XMP_NS_XMP,
    DateConverter,
    decode_pdf_date,
)

try:
    from libxmp import XMPError, XMPMeta
except Exception:  # throws libxmp.ExempiLoadError pylint: disable=broad-except
    XMPMeta, XMPError = None, None

needs_libxmp = pytest.mark.skipif(
    os.name == 'nt' or not XMPMeta, reason="test requires libxmp"
)

pytestmark = pytest.mark.filterwarnings('ignore:.*XMLParser.*:DeprecationWarning')

# pylint: disable=redefined-outer-name,pointless-statement


@pytest.fixture
def vera(resources):
    # Has XMP but no docinfo
    return Pdf.open(resources / 'veraPDF test suite 6-2-10-t02-pass-a.pdf')


@pytest.fixture
def graph(resources):
    # Has XMP and docinfo, all standard format XMP
    return Pdf.open(resources / 'graph.pdf')


@pytest.fixture
def sandwich(resources):
    # Has XMP, docinfo, <?adobe-xap-filters esc="CRLF"?>, shorthand attribute XMP
    return Pdf.open(resources / 'sandwich.pdf')


@pytest.fixture
def trivial(resources):
    # Has no XMP or docinfo
    return Pdf.open(resources / 'pal-1bit-trivial.pdf')


@pytest.fixture
def invalid_creationdate(resources):
    # Has nuls in docinfo, old PDF
    return Pdf.open(resources / 'invalid_creationdate.pdf')


def test_lowlevel(sandwich):
    meta = sandwich.open_metadata()
    assert meta._qname('pdf:Producer') == '{http://ns.adobe.com/pdf/1.3/}Producer'
    assert (
        meta._prefix_from_uri('{http://ns.adobe.com/pdf/1.3/}Producer')
        == 'pdf:Producer'
    )
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

    with trivial.open_metadata(update_docinfo=False) as xmp:
        assert not xmp  # No changes at this point
    del xmp

    print(trivial.Root.Metadata.read_bytes())

    with trivial.open_metadata(update_docinfo=False) as xmp:
        assert xmp['pdf:Producer'] == 'pikepdf ' + pikepdf.__version__
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


@pytest.mark.parametrize(
    'filename', list((Path(__file__).parent / 'resources').glob('*.pdf'))
)
def test_roundtrip(filename):
    try:
        pdf = Pdf.open(filename)
    except PasswordError:
        return
    with pdf.open_metadata() as xmp:
        for k in xmp.keys():
            if not 'Date' in k:
                xmp[k] = 'A'
    assert '<?xpacket' not in str(xmp)


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


@needs_libxmp
def test_python_xmp_validate_add(trivial):
    with trivial.open_metadata() as xmp:
        xmp['dc:creator'] = ['Bob', 'Doug']
        xmp['dc:title'] = 'Title'
        xmp['dc:publisher'] = {'Mackenzie'}

    xmp_str = str(xmp).replace('\n', '')
    assert '<rdf:Seq><rdf:li>Bob</rdf:li><rdf:li>Doug</rdf:li>' in xmp_str
    assert '<rdf:Bag><rdf:li>Mackenzie</rdf:li>' in xmp_str

    xmpmeta = XMPMeta(xmp_str=str(xmp))
    DC = XMP_NS_DC
    assert xmpmeta.does_array_item_exist(DC, 'creator', 'Bob')
    assert xmpmeta.does_array_item_exist(DC, 'creator', 'Doug')
    assert xmpmeta.get_localized_text(DC, 'title', None, 'x-default') == 'Title'
    assert xmpmeta.does_array_item_exist(DC, 'publisher', 'Mackenzie')


@needs_libxmp
def test_python_xmp_validate_change_list(graph):
    with graph.open_metadata() as xmp:
        assert 'dc:creator' in xmp
        xmp['dc:creator'] = ['Dobby', 'Kreacher']
    assert str(xmp)
    if not XMPMeta:
        pytest.skip(msg='needs libxmp')
    xmpmeta = XMPMeta(xmp_str=str(xmp))
    DC = XMP_NS_DC
    assert xmpmeta.does_array_item_exist(DC, 'creator', 'Dobby')
    assert xmpmeta.does_array_item_exist(DC, 'creator', 'Kreacher')


@needs_libxmp
def test_python_xmp_validate_change(sandwich):
    with sandwich.open_metadata() as xmp:
        assert 'xmp:CreatorTool' in xmp
        xmp['xmp:CreatorTool'] = 'Creator'  # Exists as a xml tag text
        xmp['pdf:Producer'] = 'Producer'  # Exists as a tag node
    assert str(xmp)
    xmpmeta = XMPMeta(xmp_str=str(xmp))
    assert xmpmeta.does_property_exist(XMP_NS_XMP, 'CreatorTool')
    assert xmpmeta.does_property_exist(XMP_NS_PDF, 'Producer')


def test_decode_pdf_date():
    VALS = [
        ('20160220040559', datetime(2016, 2, 20, 4, 5, 59)),
        ("20180101010101Z00'00'", datetime(2018, 1, 1, 1, 1, 1, tzinfo=timezone.utc)),
        ("20180101010101Z", datetime(2018, 1, 1, 1, 1, 1, tzinfo=timezone.utc)),
        ("20180101010101+0000", datetime(2018, 1, 1, 1, 1, 1, tzinfo=timezone.utc)),
        (
            "20180101010101+0100",
            datetime(2018, 1, 1, 1, 1, 1, tzinfo=timezone(timedelta(hours=1))),
        ),
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


@given(
    integers(-9999, 9999),
    integers(0, 99),
    integers(0, 99),
    integers(0, 99),
    integers(0, 99),
    integers(0, 99),
)
@example(1, 1, 1, 0, 0, 0)
def test_random_dates(year, month, day, hour, mins, sec):
    date_args = year, month, day, hour, mins, sec
    xmp = '{:04d}-{:02d}-{:02d}T{:02d}:{:02d}:{:02d}'.format(*date_args)
    docinfo = '{:04d}{:02d}{:02d}{:02d}{:02d}{:02d}'.format(*date_args)

    try:
        converted = DateConverter.docinfo_from_xmp(xmp)
    except ValueError:
        pass
    else:
        assert converted == docinfo

    try:
        converted = DateConverter.xmp_from_docinfo(docinfo)
    except ValueError:
        pass
    else:
        assert converted == xmp


def test_bad_char_rejection(trivial):
    with trivial.open_metadata() as xmp:
        xmp['dc:description'] = 'Bad characters \x00 \x01 \x02'
        xmp['dc:creator'] = ['\ue001bad', '\ufff0bad']
    ET.fromstring(str(xmp))


def test_xpacket_generation(sandwich):
    xmpstr1 = sandwich.Root.Metadata.read_bytes()
    xpacket_begin = b'<?xpacket begin='
    xpacket_end = b'<?xpacket end='
    assert xmpstr1.startswith(xpacket_begin)

    with sandwich.open_metadata() as xmp:
        xmp['dc:creator'] = 'Foo'

    xmpstr2 = sandwich.Root.Metadata.read_bytes()
    assert xmpstr2.startswith(xpacket_begin)

    def only_one_substring(s, subs):
        return s.find(subs) == s.rfind(subs)

    assert only_one_substring(xmpstr2, xpacket_begin)
    assert only_one_substring(xmpstr2, xpacket_end)


def test_no_rdf_subtags(graph):
    xmp = graph.open_metadata()
    assert '{http://www.w3.org/1999/02/22-rdf-syntax-ns#}Alt' not in xmp.keys()
    assert '{http://www.w3.org/1999/02/22-rdf-syntax-ns#}Bag' not in xmp.keys()
    assert '{http://www.w3.org/1999/02/22-rdf-syntax-ns#}li' not in xmp.keys()


def test_remove_attribute_metadata(sandwich):
    with sandwich.open_metadata() as xmp:
        del xmp['pdfaid:part']
    assert 'pdfaid:part' not in xmp
    assert 'pdfaid:conformance' in xmp

    with sandwich.open_metadata() as xmp:
        del xmp['pdfaid:conformance']

    # Ensure the whole node was deleted
    assert not re.search(r'rdf:Description xmlns:[^\s]+ rdf:about=""/', str(xmp))


def test_docinfo_problems(sandwich, invalid_creationdate):
    sandwich.Root.Metadata = Stream(
        sandwich,
        b"""
        <?xpacket begin='\xc3\xaf\xc2\xbb\xc2\xbf' id='W5M0MpCehiHzreSzNTczkc9d'?>
        <?adobe-xap-filters esc="CRLF"?>
        <x:xmpmeta xmlns:x='adobe:ns:meta/' x:xmptk='XMP toolkit 2.9.1-13, framework 1.6'>
        <rdf:RDF xmlns:rdf='http://www.w3.org/1999/02/22-rdf-syntax-ns#' xmlns:iX='http://ns.adobe.com/iX/1.0/'>
        <rdf:Description rdf:about='uuid:873a76ba-4819-11f4-0000-5c5716666531' xmlns:pdf='http://ns.adobe.com/pdf/1.3/' pdf:Producer='GPL Ghostscript 9.26'/>
        <rdf:Description rdf:about='uuid:873a76ba-4819-11f4-0000-5c5716666531' xmlns:xmp='http://ns.adobe.com/xap/1.0/'><xmp:ModifyDate>2019-01-04T00:44:42-08:00</xmp:ModifyDate>
        <xmp:CreateDate>2019-01-04T00:44:42-08:00</xmp:CreateDate>
        <xmp:CreatorTool>Acrobat 4.0 Scan Plug-in for Windows&#0;</xmp:CreatorTool></rdf:Description>
        <rdf:Description rdf:about='uuid:873a76ba-4819-11f4-0000-5c5716666531' xmlns:xapMM='http://ns.adobe.com/xap/1.0/mm/' xapMM:DocumentID='uuid:873a76ba-4819-11f4-0000-5c5716666531'/>
        <rdf:Description rdf:about='uuid:873a76ba-4819-11f4-0000-5c5716666531' xmlns:dc='http://purl.org/dc/elements/1.1/' dc:format='application/pdf'><dc:title><rdf:Alt><rdf:li xml:lang='x-default'>Untitled</rdf:li></rdf:Alt></dc:title></rdf:Description>
        </rdf:RDF>
        </x:xmpmeta>
        """,
    )
    meta = sandwich.open_metadata()
    meta._load()  # File has invalid XML sequence &#0;
    with meta:
        with pytest.warns(UserWarning) as warned:
            meta.load_from_docinfo(invalid_creationdate.docinfo)
        assert 'could not be copied' in warned[0].message.args[0]
        with pytest.raises(ValueError):
            meta.load_from_docinfo(invalid_creationdate.docinfo, raise_failure=True)

    with pytest.warns(UserWarning) as warned:
        with meta as xmp:
            xmp['xmp:CreateDate'] = 'invalid date'
        assert 'could not be updated' in warned[0].message.args[0]


def test_present_bug_empty_tags(trivial):
    trivial.Root.Metadata = Stream(
        trivial,
        b"""
        <?xpacket begin='\xc3\xaf\xc2\xbb\xc2\xbf' id='W5M0MpCehiHzreSzNTczkc9d'?>
        <?adobe-xap-filters esc="CRLF"?>
        <x:xmpmeta xmlns:x='adobe:ns:meta/' x:xmptk='XMP toolkit 2.9.1-13, framework 1.6'>
        <rdf:RDF xmlns:rdf='http://www.w3.org/1999/02/22-rdf-syntax-ns#' xmlns:iX='http://ns.adobe.com/iX/1.0/'>
        <rdf:Description rdf:about=""><dc:creator xmlns:dc="http://purl.org/dc/elements/1.1/"><rdf:Seq><rdf:li/></rdf:Seq></dc:creator></rdf:Description>
        </rdf:RDF>
        </x:xmpmeta>
        """,
    )
    with trivial.open_metadata(update_docinfo=True) as meta:
        pass
    assert Name.Author not in trivial.docinfo


def test_wrong_xml(sandwich):
    sandwich.Root.Metadata = Stream(
        sandwich,
        b"""
        <test><xml>This is valid xml but not valid XMP</xml></test>
    """.strip(),
    )
    meta = sandwich.open_metadata(strict=True)
    with pytest.raises(ValueError, match='not XMP'):
        with meta:
            pass
    with pytest.raises(ValueError, match='not XMP'):
        meta['pdfaid:part']


def test_no_x_xmpmeta(trivial):
    trivial.Root.Metadata = Stream(
        trivial,
        b"""
        <?xpacket begin="\xef\xbb\xbf" id="W5M0MpCehiHzreSzNTczkc9d"?>
        <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
                xmlns:xmp="http://ns.adobe.com/xap/1.0/">
        <rdf:Description rdf:about=""
                        xmlns:pdfaid="http://www.aiim.org/pdfa/ns/id/"
                        xmlns:xmp="http://ns.adobe.com/xap/1.0/">
            <pdfaid:part>1</pdfaid:part>
            <pdfaid:conformance>A</pdfaid:conformance>
            <xmp:CreatorTool>Simple Scan 3.30.2</xmp:CreatorTool>
            <xmp:CreateDate>2019-02-05T07:08:46+01:00</xmp:CreateDate>
            <xmp:ModifyDate>2019-02-05T07:08:46+01:00</xmp:ModifyDate>
            <xmp:MetadataDate>2019-02-05T07:08:46+01:00</xmp:MetadataDate>
        </rdf:Description>
        </rdf:RDF>
        <?xpacket end="w"?>
    """.strip(),
    )

    with trivial.open_metadata() as xmp:
        assert xmp._get_rdf_root() is not None
        xmp['pdfaid:part'] = '2'
    assert xmp['pdfaid:part'] == '2'


@pytest.mark.parametrize(
    'xml',
    [
        (b"      \n   "),
        (b" <"),
        (
            b'<?xpacket begin="\xef\xbb\xbf" id="W5M0MpCehiHzreSzNTczkc9d"?>\n'
            b'<?xpacket end=""?>\n'
        ),
        (
            b'<?xpacket begin="" id=""?>\n'
            b'<x:xmpmeta xmlns:x="adobe:ns:meta/" x:xmptk="">\n'
            b'</x:xmpmeta>\n'
            b'<?xpacket end=""?>\n'
        ),
    ],
)
def test_degenerate_xml_recoverable(trivial, xml):
    trivial.Root.Metadata = trivial.make_stream(xml)
    with trivial.open_metadata(strict=False) as xmp:
        xmp['pdfaid:part'] = '2'
    assert xmp['pdfaid:part'] == '2'

    with trivial.open_metadata(strict=True) as xmp:
        xmp['pdfaid:part'] = '5'


@settings(deadline=None)
@given(st.integers(min_value=1, max_value=1350))
@example(548)
@example(1154)
@example(1155)
@example(1195)
@example(1303)
@pytest.mark.filterwarnings('ignore:The DocumentInfo field')
def test_truncated_xml(resources, idx):
    sandwich = Pdf.open(resources / 'sandwich.pdf')
    data = sandwich.Root.Metadata.read_bytes()
    assume(idx < len(data))

    sandwich.Root.Metadata = sandwich.make_stream(data[0:idx])
    try:
        with sandwich.open_metadata(strict=True) as xmp:
            xmp['pdfaid:part'] = '5'
    except (XMLSyntaxError, AssertionError):
        pass

    with sandwich.open_metadata(strict=False) as xmp:
        xmp['pdfaid:part'] = '7'


@needs_libxmp
def test_pdf_version_update(graph, outdir):
    def get_xmp_version(filename):
        meta = pikepdf.open(filename).open_metadata()
        xmp = XMPMeta(xmp_str=str(meta))
        try:
            return xmp.get_property('http://ns.adobe.com/pdf/1.3/', 'PDFVersion')
        except XMPError:
            return ''

    # We don't update PDFVersion unless it is present, even if we change the PDF version
    graph.save(
        outdir / 'empty_xmp_pdfversion.pdf',
        force_version='1.7',
        fix_metadata_version=True,
    )
    assert get_xmp_version(outdir / 'empty_xmp_pdfversion.pdf') == ''

    # Add PDFVersion field for remaining tests
    with graph.open_metadata() as m:
        m['pdf:PDFVersion'] = graph.pdf_version

    # Confirm we don't update the field when the flag is false
    graph.save(
        outdir / 'inconsistent_version.pdf',
        force_version='1.6',
        fix_metadata_version=False,
    )
    assert get_xmp_version(outdir / 'inconsistent_version.pdf') == '1.3'

    # Confirm we update if present
    graph.save(outdir / 'consistent_version.pdf', force_version='1.5')
    assert get_xmp_version(outdir / 'consistent_version.pdf') == '1.5'


def test_extension_level(trivial, outpdf):
    trivial.save(outpdf, min_version=('1.6', 314159))
    pdf = pikepdf.open(outpdf)
    assert pdf.pdf_version >= '1.6' and pdf.extension_level == 314159

    trivial.save(outpdf, force_version=('1.7', 42))
    pdf = pikepdf.open(outpdf)
    assert pdf.pdf_version == '1.7' and pdf.extension_level == 42

    with pytest.raises(TypeError):
        trivial.save(outpdf, force_version=('1.7', 'invalid extension level'))


@given(
    st.dictionaries(
        keys=st.sampled_from(
            [
                "/Author",
                "/Subject",
                "/Title",
                "/Keywords",
                "/Producer",
                "/CreationDate",
                "/Creator",
                "/ModDate",
                "/Dummy",
            ]
        ),
        values=st.binary(),
    )
)
def test_random_docinfo(docinfo):
    p = pikepdf.new()
    with p.open_metadata() as m:
        pdf_docinfo = pikepdf.Dictionary(docinfo)

        try:
            m.load_from_docinfo(pdf_docinfo, raise_failure=True)
        except ValueError as e:
            assert 'could not be copied to XMP' in str(e) or '/Dummy' in str(e)
        else:
            ET.fromstring(str(m))  # ensure we can parse it


def test_set_empty_string(graph):
    with graph.open_metadata() as m:
        m['dc:title'] = 'a'

    generated_xmp = graph.Root.Metadata.read_bytes()
    print(generated_xmp)
    assert generated_xmp.count(b'<dc:title>') == 1


@pytest.mark.parametrize('fix_metadata', [True, False])
def test_dont_create_empty_xmp(trivial, outpdf, fix_metadata):
    trivial.save(outpdf, fix_metadata_version=fix_metadata)

    with pikepdf.open(outpdf) as p:
        assert Name.Metadata not in p.Root


@pytest.mark.parametrize('fix_metadata', [True, False])
def test_dont_create_empty_docinfo(trivial, outpdf, fix_metadata):
    del trivial.trailer.Info
    trivial.save(outpdf, fix_metadata_version=fix_metadata)

    with pikepdf.open(outpdf) as p:
        assert Name.Info not in p.trailer


def test_issue_100(trivial):
    with trivial.open_metadata() as m, pytest.warns(
        UserWarning, match="no XMP equivalent"
    ):
        m.load_from_docinfo({'/AAPL:Example': pikepdf.Array([42])})


def test_issue_135_title_rdf_bag(trivial):
    with trivial.open_metadata(update_docinfo=True) as xmp, pytest.warns(
        UserWarning, match="Merging elements"
    ):
        xmp['dc:title'] = {'Title 1', 'Title 2'}
    with trivial.open_metadata(update_docinfo=False) as xmp:
        assert b'Title 1; Title 2</rdf:li></rdf:Alt></dc:title>' in xmp._get_xml_bytes()
