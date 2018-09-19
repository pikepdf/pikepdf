"""
Testing focused on pikepdf.Pdf
"""

import pytest
from pikepdf import Pdf, PasswordError, Stream

import sys
from io import StringIO
from unittest.mock import Mock


def test_non_filename():
    with pytest.raises(TypeError):
        Pdf.open(42)


def test_not_existing_file():
    with pytest.raises(FileNotFoundError):
        Pdf.open('does_not_exist.pdf')


class TestLinearization:
    def test_linearization(self, resources, outdir):
        pdf = Pdf.open(resources / 'graph.pdf')
        assert not pdf.is_linearized

        pdf.save(outdir / 'lin.pdf', linearize=True)

        pdf = Pdf.open(outdir / 'lin.pdf')
        assert pdf.is_linearized

        sio = StringIO()
        pdf.check_linearization(sio)


def test_objgen(resources):
    src = Pdf.open(resources / 'graph.pdf')
    im0 = src.pages[0].Resources.XObject['/Im0']
    assert im0.objgen == (5, 0)
    object5 = src.get_object((5, 0))
    assert object5.is_owned_by(src)
    assert object5 == im0


class TestPasswords:
    def test_open_pdf_wrong_password(self, resources):
        with pytest.raises(PasswordError):
            Pdf.open(resources / 'graph-encrypted.pdf', password='wrong')

    def test_open_pdf_password_encoding(self, resources):
        with pytest.raises(PasswordError):
            Pdf.open(resources / 'graph-encrypted.pdf', password=b'\x01\xfe')

    def test_open_pdf_no_password_but_needed(self, resources):
        with pytest.raises(PasswordError):
            Pdf.open(resources / 'graph-encrypted.pdf')


class TestStreams:
    def test_stream(self, resources):
        with (resources / 'pal-1bit-trivial.pdf').open('rb') as stream:
            pdf = Pdf.open(stream)
        assert pdf.root.Pages.Count == 1

    def test_no_text_stream(self, resources):
        with pytest.raises(TypeError):
            with (resources / 'pal-1bit-trivial.pdf').open('r') as stream:
                Pdf.open(stream)

    def test_save_stream(self, resources, outdir):
        from io import BytesIO
        pdf = Pdf.open(resources / 'pal-1bit-trivial.pdf')
        pdf.save(outdir / 'nostream.pdf', static_id=True)

        bio = BytesIO()
        pdf.save(bio, static_id=True)
        bio.seek(0)

        with (outdir / 'nostream.pdf').open('rb') as saved_file:
            saved_file_contents = saved_file.read()
        assert saved_file_contents == bio.read()


class TestMemory:
    def test_memory(self, resources):
        pdf = (resources / 'pal-1bit-trivial.pdf').read_bytes()
        with pytest.raises(Exception):
            pdf = Pdf.open(pdf)


def test_remove_unreferenced(resources, outdir):
    in_ = resources / 'sandwich.pdf'
    out1 = outdir / 'out1.pdf'
    out2 = outdir / 'out2.pdf'
    pdf = Pdf.open(in_)
    pdf.pages[0].Contents = Stream(pdf, b' ')
    pdf.save(out1)

    pdf.remove_unreferenced_resources()
    pdf.save(out2)

    assert out2.stat().st_size < out1.stat().st_size


def test_show_xref(resources):
    pdf = Pdf.open(resources / 'pal-1bit-trivial.pdf')
    pdf.show_xref_table()


@pytest.mark.skipif(sys.version_info < (3, 6),
                    reason='missing mock.assert_called')
def test_progress(resources, outdir):
    pdf = Pdf.open(resources / 'pal-1bit-trivial.pdf')
    mock = Mock()
    pdf.save(outdir / 'out.pdf', progress=mock)
    mock.assert_called()
