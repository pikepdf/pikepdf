"""
A bunch of quick tests that confirm nothing is horribly wrong
"""

import gc
from contextlib import suppress
from distutils.version import LooseVersion
from shutil import copy

import pytest

import pikepdf
from pikepdf import Name, Object, Pdf, Stream


def test_minimum_qpdf_version():
    from pikepdf import _qpdf

    assert LooseVersion(_qpdf.qpdf_version()) >= LooseVersion('10.0.0')


def test_open_pdf(resources):
    pdf = pikepdf.open(resources / 'graph.pdf')
    assert '1.3' <= pdf.pdf_version <= '1.7'

    assert pdf.Root['/Pages']['/Count'] == 1


def test_open_pdf_password(resources):
    pdf = Pdf.open(resources / 'graph-encrypted.pdf', password='owner')
    assert pdf.Root['/Pages']['/Count'] == 1


def test_attr_access(resources):
    pdf = Pdf.open(resources / 'graph.pdf')
    assert int(pdf.Root.Pages.Count) == 1


def test_root(resources):
    pdf = Pdf.open(resources / 'graph.pdf')
    with pytest.warns(DeprecationWarning):
        assert pdf.root == pdf.Root


def test_create_pdf(outdir):
    pdf = Pdf.new()

    font = pdf.make_indirect(
        Object.parse(
            b"""
            <<
                /Type /Font
                /Subtype /Type1
                /Name /F1
                /BaseFont /Helvetica
                /Encoding /WinAnsiEncoding
            >>"""
        )
    )

    width, height = 100, 100
    image_data = b"\xff\x7f\x00" * (width * height)

    image = Stream(pdf, image_data)
    image.stream_dict = Object.parse(
        b"""
            <<
                /Type /XObject
                /Subtype /Image
                /ColorSpace /DeviceRGB
                /BitsPerComponent 8
                /Width 100
                /Height 100
            >>"""
    )

    rfont = {'/F1': font}

    xobj = {'/Im1': image}

    resources = {'/Font': rfont, '/XObject': xobj}

    mediabox = [0, 0, 612, 792]

    stream = b"""
        BT /F1 24 Tf 72 720 Td (Hi there) Tj ET
        q 144 0 0 144 234 324 cm /Im1 Do Q
        """

    contents = Stream(pdf, stream)

    page_dict = {
        '/Type': Name('/Page'),
        '/MediaBox': mediabox,
        '/Contents': contents,
        '/Resources': resources,
    }
    qpdf_page_dict = page_dict
    page = pdf.make_indirect(qpdf_page_dict)

    pdf.pages.append(page)
    pdf.save(outdir / 'hi.pdf')


def test_copy_semantics(resources):
    pdf = Pdf.open(resources / 'graph.pdf')

    # Ensure that we can name a reference to a child object and view the
    # changes from the parent
    page = pdf.pages[0]
    mediabox = page['/MediaBox']
    assert mediabox[2] != 0
    mediabox[2] = 0
    assert page['/MediaBox'][2] == mediabox[2]


def test_copy_page_keepalive(resources, outdir):
    # str for py<3.6
    copy(str(resources / 'sandwich.pdf'), str(outdir / 'sandwich.pdf'))
    src = Pdf.open(outdir / 'sandwich.pdf')
    pdf = Pdf.open(resources / 'graph.pdf')

    pdf.pages.append(src.pages[0])

    del src
    src = None
    gc.collect()
    with suppress(PermissionError):
        (outdir / 'sandwich.pdf').unlink()
    pdf.save(outdir / 'out.pdf')


def test_open_save(resources, outdir):
    out = str(outdir / 'graph.pdf')
    copy(str(resources / 'graph.pdf'), out)
    src = Pdf.open(out)
    with pytest.raises(ValueError):
        src.save(out)
    src.save(outdir / 'graph2.pdf')


def test_readme_example(resources, outdir):
    # Elegant, Pythonic API
    pdf = pikepdf.open(resources / 'fourpages.pdf')
    assert len(pdf.pages) == 4
    del pdf.pages[-1]
    assert len(pdf.pages) == 3
    pdf.save(outdir / 'output.pdf')


def test_system_error():
    with pytest.raises(FileNotFoundError):
        pikepdf._qpdf._test_file_not_found()
