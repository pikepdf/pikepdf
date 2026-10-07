# SPDX-FileCopyrightText: 2022 James R. Barlow
# SPDX-License-Identifier: CC0-1.0

from __future__ import annotations

import logging
from io import BytesIO

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


def test_unclassified_qpdf_error_is_a_pikepdf_error(vera):
    # qpdf reports this with a bare std::runtime_error. It must be catchable as
    # a pikepdf error without ceasing to be a RuntimeError. See #240.
    with pytest.raises(pikepdf.QpdfRuntimeError, match="not linearized") as excinfo:
        vera.check_linearization()
    assert isinstance(excinfo.value, pikepdf.PikepdfError)
    assert isinstance(excinfo.value, RuntimeError)
    assert not isinstance(excinfo.value, PdfError)


def test_malformed_job_json_is_a_pikepdf_error():
    with pytest.raises(pikepdf.QpdfRuntimeError) as excinfo:
        pikepdf.Job('{')
    assert isinstance(excinfo.value, RuntimeError)


def corrupt_flate_stream(pdf: Pdf) -> Stream:
    return pdf.make_stream(b'not flate data at all', Filter=Name.FlateDecode)


def reopened(pdf: Pdf, **kwargs) -> Pdf:
    """Round-trip through a file so stream data is read from an input source.

    qpdf treats a decode failure differently depending on where the stream's
    data lives: for data read from a file it traps the failure and records a
    warning, where for data set from memory the failure reaches the caller.
    """
    bio = BytesIO()
    pdf.save(
        bio,
        compress_streams=False,
        stream_decode_level=pikepdf.StreamDecodeLevel.none,
    )
    bio.seek(0)
    return Pdf.open(bio, **kwargs)


def test_corrupt_stream_in_memory_is_data_decoding_error():
    with Pdf.new() as pdf:
        stream = corrupt_flate_stream(pdf)
        with pytest.raises(DataDecodingError, match="incorrect header check"):
            stream.read_bytes()


@pytest.mark.parametrize('method', ['read_bytes', 'get_stream_buffer'])
def test_corrupt_stream_from_file_is_data_decoding_error(method):
    with Pdf.new() as pdf:
        pdf.Root.Corrupt = corrupt_flate_stream(pdf)
        with reopened(pdf) as pdf2:
            stream = pdf2.Root.Corrupt
            with pytest.raises(DataDecodingError) as excinfo:
                getattr(stream, method)()
            msg = str(excinfo.value)
            # The reason qpdf gave, not just "unfilterable stream"...
            assert 'incorrect header check' in msg
            assert 'unfilterable' not in msg
            # ...and which object it was.
            objgen = stream.objgen
            assert f'object {objgen[0]},{objgen[1]}' in msg
            # qpdf's warnings are still there for callers that read them.
            assert any('incorrect header check' in w for w in pdf2.get_warnings())


def test_earlier_warnings_survive_a_decode_failure():
    # Recovering the cause means reading qpdf's warning list, which qpdf can
    # only hand over destructively. Nothing may be lost or reordered.
    with Pdf.new() as pdf:
        pdf.Root.Corrupt = corrupt_flate_stream(pdf)
        with reopened(pdf) as pdf2:
            stream = pdf2.Root.Corrupt
            with pytest.raises(DataDecodingError):
                stream.read_bytes()
            first = pdf2.get_warnings()
            assert first
            with pytest.raises(DataDecodingError):
                stream.read_bytes()
            with pytest.raises(DataDecodingError):
                stream.read_bytes()
            again = pdf2.get_warnings()
            assert again == first * 2
            assert pdf2.get_warnings() == []


def test_decode_failure_does_not_log_warnings_twice(caplog):
    # With suppress_warnings=False qpdf logs each warning as it is issued.
    # Recovering the cause must not issue them again.
    caplog.set_level(logging.WARNING, logger='pikepdf._core')
    with Pdf.new() as pdf:
        pdf.Root.Corrupt = corrupt_flate_stream(pdf)
        with reopened(pdf, suppress_warnings=False) as pdf2:
            caplog.clear()
            with pytest.raises(DataDecodingError):
                pdf2.Root.Corrupt.read_bytes()
            logged = [r for r in caplog.records if 'header check' in r.getMessage()]
            assert len(logged) == 1
            assert len(pdf2.get_warnings()) == 1


def test_genuinely_unfilterable_stream_is_still_a_plain_pdf_error():
    # No decode was attempted, so there is no cause to recover: qpdf has no
    # filter for this at the default decode level.
    with Pdf.new() as pdf:
        stream = pdf.make_stream(b'\xff\xd8 not really a jpeg', Filter=Name.DCTDecode)
        with pytest.raises(PdfError, match="unfilterable") as excinfo:
            stream.read_bytes()
        assert not isinstance(excinfo.value, DataDecodingError)


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
    def test_qpdf_runtime_error_is_also_a_runtime_error(self):
        # Errors that used to surface as a bare RuntimeError must still be
        # caught by handlers written for RuntimeError.
        assert issubclass(pikepdf.QpdfRuntimeError, RuntimeError)
        assert issubclass(pikepdf.QpdfRuntimeError, pikepdf.PikepdfError)
        assert not issubclass(pikepdf.QpdfRuntimeError, PdfError)
        assert pikepdf.exceptions.QpdfRuntimeError is pikepdf.QpdfRuntimeError

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
