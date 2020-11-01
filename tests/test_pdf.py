"""
Testing focused on pikepdf.Pdf
"""

import locale
import shutil
import sys
from io import BytesIO, StringIO
from os import fspath
from pathlib import Path
from unittest.mock import Mock

import pytest

import pikepdf
from pikepdf import PasswordError, Pdf, PdfError, Stream

# pylint: disable=redefined-outer-name


@pytest.fixture
def trivial(resources):
    return Pdf.open(
        resources / 'pal-1bit-trivial.pdf', access_mode=pikepdf.AccessMode.mmap
    )


def test_new(outdir):
    pdf = pikepdf.new()
    pdf.save(outdir / 'new-empty.pdf')


def test_non_filename():
    with pytest.raises(TypeError):
        Pdf.open(42.0)


def test_file_descriptor(resources):
    with (resources / 'pal-1bit-trivial.pdf').open('rb') as f:
        with pytest.raises(TypeError):
            Pdf.open(f.fileno())


def test_save_to_file_descriptor_fails(trivial):
    with pytest.raises(TypeError):
        trivial.save(2)


def test_not_existing_file():
    with pytest.raises(FileNotFoundError):
        Pdf.open('does_not_exist.pdf')


def test_empty(outdir):
    target = outdir / 'empty.pdf'
    target.touch()
    with pytest.raises(PdfError):
        Pdf.open(target)


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
    assert object5 == src.get_object(5, 0)


class TestPasswords:
    def test_open_pdf_wrong_password(self, resources):
        # The correct passwords are "owner" and "user"
        with pytest.raises(PasswordError):
            Pdf.open(resources / 'graph-encrypted.pdf', password='wrong')

    def test_open_pdf_password_encoding(self, resources):
        with pytest.raises(PasswordError):
            Pdf.open(resources / 'graph-encrypted.pdf', password=b'\x01\xfe')

    def test_open_pdf_no_password_but_needed(self, resources):
        with pytest.raises(PasswordError):
            Pdf.open(resources / 'graph-encrypted.pdf')


class TestPermissions:
    def test_some_permissions_missing(self, resources):
        pdf = Pdf.open(resources / 'graph-encrypted.pdf', 'owner')
        assert pdf.allow.print_highres == pdf.allow.modify_annotation == False

    def test_permissions_all_true_not_encrypted(self, trivial):
        assert all(trivial.allow)


class TestStreams:
    def test_stream(self, resources):
        with (resources / 'pal-1bit-trivial.pdf').open('rb') as stream:
            pdf = Pdf.open(stream)
        assert pdf.Root.Pages.Count == 1

    def test_no_text_stream(self, resources):
        with pytest.raises(TypeError):
            with (resources / 'pal-1bit-trivial.pdf').open('r') as stream:
                Pdf.open(stream)

    def test_save_stream(self, trivial, outdir):
        pdf = trivial
        pdf.save(outdir / 'nostream.pdf', static_id=True)

        bio = BytesIO()
        pdf.save(bio, static_id=True)
        bio.seek(0)

        with (outdir / 'nostream.pdf').open('rb') as saved_file:
            saved_file_contents = saved_file.read()
        assert saved_file_contents == bio.read()

    def test_read_not_readable_file(self, outdir):
        writable = (Path(outdir) / 'writeme.pdf').open('wb')
        with pytest.raises(ValueError, match=r'not readable'):
            Pdf.open(writable)

    def test_open_not_seekable_stream(self, resources):
        class UnseekableBytesIO(BytesIO):
            def seekable(self):
                return False

        testio = UnseekableBytesIO((resources / 'pal-1bit-trivial.pdf').read_bytes())

        with pytest.raises(ValueError, match=r'not seekable'):
            Pdf.open(testio)


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


def test_show_xref(trivial):
    trivial.show_xref_table()


def test_progress(trivial, outdir):
    pdf = trivial
    mock = Mock()
    pdf.save(outdir / 'out.pdf', progress=mock)
    mock.assert_called()


@pytest.mark.skipif(locale.getpreferredencoding() != 'UTF-8', reason="Unicode check")
def test_unicode_filename(resources, outdir):
    target1 = outdir / '测试.pdf'
    target2 = outdir / '通过考试.pdf'
    shutil.copy(fspath(resources / 'pal-1bit-trivial.pdf'), fspath(target1))
    pdf = Pdf.open(target1)
    pdf.save(target2)
    assert target2.exists()


def test_min_and_force_version(trivial, outdir):
    pdf = trivial
    pdf.save(outdir / '1.7.pdf', min_version='1.7')

    pdf17 = Pdf.open(outdir / '1.7.pdf')
    assert pdf17.pdf_version == '1.7'

    pdf.save(outdir / '1.2.pdf', force_version='1.2')
    pdf12 = Pdf.open(outdir / '1.2.pdf')
    assert pdf12.pdf_version == '1.2'


def test_normalize_linearize(trivial, outdir):
    with pytest.raises(ValueError):
        trivial.save(outdir / 'no.pdf', linearize=True, normalize_content=True)


def test_make_stream(trivial, outdir):
    pdf = trivial
    stream = pdf.make_stream(b'q Q')
    pdf.pages[0].Contents = stream
    pdf.save(outdir / 's.pdf')


def test_add_blank_page(trivial):
    assert len(trivial.pages) == 1

    invalid = [-1, 0, 2, 15000]
    for n in invalid:
        with pytest.raises(ValueError):
            trivial.add_blank_page(page_size=(n, n))
    trivial.add_blank_page()
    assert len(trivial.pages) == 2


def test_object_stream_mode_generated(trivial, outdir):
    trivial.save(
        outdir / '1.pdf',
        fix_metadata_version=True,
        object_stream_mode=pikepdf.ObjectStreamMode.generate,
    )
    assert b'/ObjStm' in (outdir / '1.pdf').read_bytes()

    trivial.save(
        outdir / '2.pdf',
        fix_metadata_version=False,
        object_stream_mode=pikepdf.ObjectStreamMode.generate,
    )
    assert b'/ObjStm' in (outdir / '2.pdf').read_bytes()


def test_with_block(resources):
    desc = ''
    with pikepdf.open(resources / 'pal-1bit-trivial.pdf') as pdf:
        desc = pdf.filename
    assert pdf.filename != desc


def test_with_block_abuse(resources):
    with pikepdf.open(resources / 'pal-1bit-trivial.pdf') as pdf:
        im0 = pdf.pages[0].Resources.XObject['/Im0']
    with pytest.raises(PdfError):
        im0.read_bytes()


def test_allow_overwriting_input(resources, tmp_path):
    orig_pdf_path = fspath(resources / 'pal-1bit-trivial.pdf')
    tmp_pdf_path = fspath(tmp_path / 'pal-1bit-trivial.pdf')
    shutil.copy(orig_pdf_path, tmp_pdf_path)
    with pikepdf.open(tmp_pdf_path, allow_overwriting_input=True) as pdf:
        with pdf.open_metadata() as meta:
            meta['dc:title'] = 'New Title'
        pdf.save('other.pdf', encryption=dict(owner="owner"))
        pdf.save()
        pdf.save(linearize=True)
    with pikepdf.open(tmp_pdf_path) as pdf:
        with pdf.open_metadata() as meta:
            assert meta['dc:title'] == 'New Title'
    with pikepdf.open(orig_pdf_path) as pdf:
        with pdf.open_metadata() as meta:
            assert 'dc:title' not in meta


def test_allow_overwriting_input_ko(resources):
    with pytest.raises(ValueError):
        with pikepdf.open(BytesIO(), allow_overwriting_input=True):
            pass


def test_check(resources):
    with pikepdf.open(resources / 'content-stream-errors.pdf') as pdf:
        problems = pdf.check()
        assert all(isinstance(prob, str) for prob in problems)
        assert 'parse error while reading' in problems[0]


def test_repr(trivial):
    assert repr(trivial).startswith('<')
