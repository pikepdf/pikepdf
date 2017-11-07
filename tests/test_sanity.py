import pytest
from pikepdf import _qpdf as qpdf

import os
import platform
import shutil
import gc
from contextlib import suppress
from shutil import copy


def test_minimum_qpdf_version():
    assert qpdf.qpdf_version() >= '6.0.0'


def test_open_pdf(resources):
    pdf = qpdf.Pdf.open(resources / 'graph.pdf')
    assert '1.3' <= pdf.pdf_version <= '1.7'

    assert pdf.root['/Pages']['/Count'].as_int() == 1


def test_open_pdf_password(resources):
    pdf = qpdf.Pdf.open(resources / 'graph-encrypted.pdf', password='owner')
    assert pdf.root['/Pages']['/Count'].as_int() == 1


def test_open_pdf_wrong_password(resources):
    with pytest.raises(qpdf.PasswordError):
        qpdf.Pdf.open(resources / 'graph-encrypted.pdf', password='wrong')


def test_open_pdf_password_encoding(resources):
    with pytest.raises(qpdf.PasswordError):
        qpdf.Pdf.open(resources / 'graph-encrypted.pdf', password=b'\x01\xfe')


def test_open_pdf_no_password_but_needed(resources):
    with pytest.raises(qpdf.PasswordError):
        qpdf.Pdf.open(resources / 'graph-encrypted.pdf')


def test_stream(resources):
    with (resources / 'graph.pdf').open('rb') as stream:
        pdf = qpdf.Pdf.open(stream)
    assert pdf.root.Pages.Count == 1


def test_no_text_stream(resources):
    with pytest.raises(TypeError):
        with (resources / 'graph.pdf').open('r') as stream:
            qpdf.Pdf.open(stream)


def test_attr_access(resources):
    pdf = qpdf.Pdf.open(resources / 'graph.pdf')
    assert int(pdf.root.Pages.Count) == 1


def test_create_pdf(outdir):
    pdf = qpdf.Pdf.new()

    font = pdf.make_indirect(
        qpdf.Object.parse(b"""
            <<
                /Type /Font
                /Subtype /Type1
                /Name /F1
                /BaseFont /Helvetica
                /Encoding /WinAnsiEncoding
            >>"""))

    width, height = 100, 100
    image_data = b"\xff\x7f\x00" * (width * height)

    image = qpdf.Stream(pdf, image_data)
    image.stream_dict = qpdf.Object.parse(b"""
            <<
                /Type /XObject
                /Subtype /Image
                /ColorSpace /DeviceRGB
                /BitsPerComponent 8
                /Width 100
                /Height 100
            >>""")

    rfont = {'/F1': font}

    xobj = {'/Im1': image}

    resources = {
        '/Font': rfont,
        '/XObject': xobj
        }

    mediabox = [0, 0, 612, 792]

    stream = b"""
        BT /F1 24 Tf 72 720 Td (Hi there) Tj ET
        q 144 0 0 144 234 324 cm /Im1 Do Q
        """

    contents = qpdf.Stream(pdf, stream)

    page_dict = {
        '/Type': qpdf.Name('/Page'),
        '/MediaBox': mediabox,
        '/Contents': contents,
        '/Resources': resources
        }
    qpdf_page_dict = page_dict
    page = pdf.make_indirect(qpdf_page_dict)

    pdf.pages.append(page)
    pdf.save(outdir / 'hi.pdf')


def test_copy_semantics(resources):
    pdf = qpdf.Pdf.open(resources / 'graph.pdf')

    # Ensure that we can name a reference to a child object and view the
    # changes from the parent
    page = pdf.pages[0]
    mediabox = page['/MediaBox']
    assert mediabox[2].decode() != 0
    mediabox[2] = 0
    assert page['/MediaBox'][2] == mediabox[2]


def test_save_stream(resources, outdir):
    from io import BytesIO
    pdf = qpdf.Pdf.open(resources / 'graph.pdf')
    pdf.save(outdir / 'nostream.pdf', static_id=True)

    bio = BytesIO()
    pdf.save(bio, static_id=True)
    bio.seek(0)

    with (outdir / 'nostream.pdf').open('rb') as saved_file:
        saved_file_contents = saved_file.read()
    assert saved_file_contents == bio.read()


def test_copy_page_keepalive(resources, outdir):
    # str for py<3.6
    copy(str(resources / 'sandwich.pdf'), str(outdir / 'sandwich.pdf'))
    src = qpdf.Pdf.open(outdir / 'sandwich.pdf')
    pdf = qpdf.Pdf.open(resources / 'graph.pdf')

    pdf.pages.append(src.pages[0])

    del src
    src = None
    gc.collect()
    (outdir / 'sandwich.pdf').unlink()
    pdf.save(outdir / 'out.pdf')

