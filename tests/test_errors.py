# SPDX-FileCopyrightText: 2022 James R. Barlow
# SPDX-License-Identifier: CC0-1.0

from __future__ import annotations

import pytest
from conftest import skip_if_pypy

import pikepdf
import pikepdf.exceptions
from pikepdf import (
    DataDecodingError,
    DeletedObjectError,
    Name,
    Pdf,
    PdfError,
    Stream,
    _core,
)


@pytest.fixture
def vera(resources):
    # A file that is not linearized
    with Pdf.open(resources / 'veraPDF test suite 6-2-10-t02-pass-a.pdf') as pdf:
        yield pdf


def test_foreign_linearization(vera):
    assert not vera.is_linearized
    with pytest.raises(RuntimeError, match="not linearized"):
        vera.check_linearization()


@pytest.mark.abi3_smoke
@pytest.mark.parametrize('msg, expected', [('QPDF', 'pikepdf.Pdf')])
def test_translate_qpdf_logic_error(msg, expected):
    assert _core._translate_qpdf_logic_error(msg) == expected


@pytest.mark.parametrize(
    'filter_,data,msg',
    [
        ('/ASCII85Decode', b'\xba\xad', 'character out of range'),
        ('/ASCII85Decode', b'fooz', 'unexpected z'),
        ('/ASCIIHexDecode', b'1g', 'character out of range'),
        ('/FlateDecode', b'\xba\xad', 'incorrect header check'),
    ],
)
@pytest.mark.abi3_smoke
def test_data_decoding_errors(filter_: str, data: bytes, msg: str):
    p = Pdf.new()
    st = Stream(p, data, Filter=Name(filter_))
    with pytest.raises(DataDecodingError, match=msg):
        st.read_bytes()


@pytest.mark.abi3_smoke
def test_system_error():
    with pytest.raises(FileNotFoundError):
        pikepdf._core._test.fopen_nonexistent_file()


@skip_if_pypy
def test_return_object_from_closed():
    p = Pdf.new()
    obj = p.Root.TestObject = p.make_stream(b'test stream')
    p.close()
    del p
    assert repr(obj) != ''
    with pytest.raises(DeletedObjectError):
        obj.read_bytes()


def test_object_type_assertion(resources):
    with pytest.raises(PdfError):
        with Pdf.open(resources / 'fuzz' / '378014596.pdf') as p:
            p.check_pdf_syntax()


def test_pdf_syntax_check_progress(resources):
    called = False

    def progress_fn(update):
        nonlocal called
        called = True

    with Pdf.open(resources / 'outlines.pdf') as p:
        p.check_pdf_syntax(progress_fn)

    assert called, "progress function not called"


class TestExceptionHierarchy:
    """Lock down the exception hierarchy documented in docs/api/exceptions.md.

    The shape here is API. It was flattened once by accident during the
    nanobind migration (see 6ab7f528), so assert the whole tree rather than
    the individual relationship that happened to break that time.

    ``pikepdf.exceptions`` is the canonical surface for these names; not all of
    them are re-exported from the top-level package.
    """

    @pytest.mark.abi3_smoke
    def test_everything_derives_from_pikepdf_error(self):
        for name in pikepdf.exceptions.__all__:
            cls = getattr(pikepdf.exceptions, name)
            base = (
                pikepdf.PikepdfWarning
                if issubclass(cls, Warning)
                else pikepdf.PikepdfError
            )
            assert issubclass(cls, base), f"{name} does not derive from {base.__name__}"

    @pytest.mark.abi3_smoke
    def test_pikepdf_error_roots(self):
        assert issubclass(pikepdf.PikepdfError, Exception)
        assert not issubclass(pikepdf.PikepdfError, Warning)
        assert issubclass(pikepdf.PikepdfWarning, UserWarning)

    @pytest.mark.abi3_smoke
    @pytest.mark.parametrize(
        'name',
        ['DataDecodingError', 'PdfParsingError', 'ReferenceCycleError'],
    )
    def test_document_defects_derive_from_pdf_error(self, name):
        # A defective document is a PdfError, so `except PdfError` around
        # parsing or stream decoding means what it appears to mean.
        assert issubclass(getattr(pikepdf.exceptions, name), PdfError)

    @pytest.mark.abi3_smoke
    def test_password_error_is_not_a_pdf_error(self):
        # A wrong password is not a document defect. ocrmypdf orders
        #     except PdfError: ...
        #     except PasswordError: ...
        # and relies on the first handler not swallowing the second.
        assert not issubclass(pikepdf.PasswordError, PdfError)
        assert issubclass(pikepdf.PasswordError, pikepdf.PikepdfError)

    @pytest.mark.abi3_smoke
    @pytest.mark.parametrize(
        'name',
        ['ForeignObjectError', 'DeletedObjectError', 'JobUsageError'],
    )
    def test_api_misuse_errors_are_not_pdf_errors(self, name):
        # These report a bug in the caller, not a problem with the document.
        assert not issubclass(getattr(pikepdf.exceptions, name), PdfError)

    @pytest.mark.abi3_smoke
    def test_not_extractable_error_is_public(self):
        # It is the base class of the exported HifiPrintImageNotTranscodableError,
        # so it must be catchable by name.
        assert issubclass(
            pikepdf.HifiPrintImageNotTranscodableError, pikepdf.NotExtractableError
        )

    # Not abi3_smoke: the rest of this class is pure C-extension surface, but
    # this one needs Pillow.
    def test_decompression_bomb_keeps_pillow_bases(self):
        pytest.importorskip('PIL')
        from PIL import Image

        assert issubclass(pikepdf.DecompressionBombError, Image.DecompressionBombError)
        assert issubclass(pikepdf.DecompressionBombError, pikepdf.PikepdfError)
        assert issubclass(
            pikepdf.DecompressionBombWarning, Image.DecompressionBombWarning
        )
        assert issubclass(pikepdf.DecompressionBombWarning, pikepdf.PikepdfWarning)

    @pytest.mark.abi3_smoke
    def test_undecodable_stream_caught_by_pdf_error(self):
        # The motivating case from #739.
        p = Pdf.new()
        st = Stream(p, b'\xba\xad', Filter=Name('/FlateDecode'))
        with pytest.raises(PdfError):
            st.read_bytes()
