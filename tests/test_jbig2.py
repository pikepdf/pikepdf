# SPDX-FileCopyrightText: 2023 James R. Barlow
# SPDX-License-Identifier: CC0-1.0

from __future__ import annotations

import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

import pikepdf
from pikepdf import (
    DataDecodingError,
    DependencyError,
    Name,
    Object,
    Pdf,
    PdfImage,
)
from pikepdf.jbig2 import JBIG2Decoder


@pytest.fixture
def first_image_in(resources, request):
    pdf = None

    def opener(filename):
        nonlocal pdf
        pdf = Pdf.open(resources / filename)
        pdfimagexobj = next(iter(pdf.pages[0].get_images(recursive=False).values()))
        return pdfimagexobj, pdf

    def closer():
        if pdf:
            pdf.close()

    request.addfinalizer(closer)

    return opener


@pytest.fixture
def jbig2(first_image_in):
    return first_image_in('jbig2.pdf')


@pytest.fixture
def patch_jbig2dec():
    original = pikepdf.jbig2.get_decoder()

    def _patch_jbig2dec(runner):
        pikepdf.jbig2.set_decoder(JBIG2Decoder(subprocess_run=runner))

    yield _patch_jbig2dec
    pikepdf.jbig2.set_decoder(original)


def test_check_specialized_decoder_fallback(
    resources: Path, patch_jbig2dec: Callable[..., None]
):
    def run_claim_notfound(args, *pargs, **kwargs):
        raise FileNotFoundError(args[0])

    patch_jbig2dec(run_claim_notfound)

    with pikepdf.open(resources / 'jbig2.pdf') as pdf:
        with pytest.warns(UserWarning, match=r".*missing some specialized.*"):
            problems = pdf.check_pdf_syntax()
        assert len(problems) == 0


def test_jbig2_not_available(jbig2: Any, patch_jbig2dec: Callable[..., None]):
    xobj, _pdf = jbig2
    pim = PdfImage(xobj)

    def run_claim_notfound(args, *pargs, **kwargs):
        raise FileNotFoundError('jbig2dec')

    patch_jbig2dec(run_claim_notfound)

    assert not pikepdf.jbig2.get_decoder().available()

    with pytest.raises(DependencyError):
        pim.as_pil_image()


needs_jbig2dec = pytest.mark.skipif(
    not pikepdf.jbig2.get_decoder().available(), reason="jbig2dec not installed"
)


@needs_jbig2dec
def test_jbig2_extractor(jbig2: Any):
    xobj, _pdf = jbig2
    pikepdf.jbig2.get_decoder().decode_jbig2(xobj.read_raw_bytes(), b'')


@needs_jbig2dec
def test_jbig2(jbig2: Any):
    xobj, _pdf = jbig2
    pim = PdfImage(xobj)
    im = pim.as_pil_image()
    assert im.size == (1000, 1520)
    assert im.getpixel((0, 0)) == 0  # Ensure loaded


@needs_jbig2dec
def test_jbig2_decodeparms_null_issue317(jbig2: Any):
    xobj, _pdf = jbig2
    xobj.stream_dict = Object.parse(
        b'''<< /BitsPerComponent 1
               /ColorSpace /DeviceGray
               /Filter [ /JBIG2Decode ]
               /DecodeParms null
               /Height 1520
               /Length 19350
               /Subtype /Image
               /Type /XObject
               /Width 1000
            >>'''
    )
    pim = PdfImage(xobj)
    im = pim.as_pil_image()
    assert im.size == (1000, 1520)
    assert im.getpixel((0, 0)) == 0  # Ensure loaded


@needs_jbig2dec
def test_jbig2_global(first_image_in):
    xobj, _pdf = first_image_in('jbig2global.pdf')
    pim = PdfImage(xobj)
    im = pim.as_pil_image()
    assert im.size == (4000, 2864)
    assert im.getpixel((0, 0)) == 255  # Ensure loaded


@needs_jbig2dec
def test_jbig2_global_palette(first_image_in):
    xobj, _pdf = first_image_in('jbig2global.pdf')
    xobj.ColorSpace = pikepdf.Array(
        [Name.Indexed, Name.DeviceRGB, 1, b'\x00\x00\x00\xff\xff\xff']
    )
    pim = PdfImage(xobj)
    im = pim.as_pil_image()
    assert im.size == (4000, 2864)
    assert im.getpixel((0, 0)) == 255  # Ensure loaded


def test_jbig2_error(first_image_in, patch_jbig2dec: Callable[..., None]):
    xobj, _pdf = first_image_in('jbig2global.pdf')
    pim = PdfImage(xobj)

    def run_claim_broken(args, *pargs, **kwargs):
        if args[1] == '--version':
            return subprocess.CompletedProcess(args, 0, stdout='0.15', stderr='')
        raise subprocess.CalledProcessError(1, 'jbig2dec')

    patch_jbig2dec(run_claim_broken)

    pim = PdfImage(xobj)
    with pytest.raises(DataDecodingError, match="jbig2dec failed to decode"):
        pim.as_pil_image()


def test_jbig2_too_old(first_image_in, patch_jbig2dec: Callable[..., None]):
    xobj, _pdf = first_image_in('jbig2global.pdf')
    pim = PdfImage(xobj)

    def run_claim_old(args, *pargs, **kwargs):
        return subprocess.CompletedProcess(args, 0, stdout='0.12', stderr='')

    patch_jbig2dec(run_claim_old)

    pim = PdfImage(xobj)
    with pytest.raises(DependencyError, match='too old'):
        pim.as_pil_image()


def test_jbig2_reports_no_version(first_image_in, patch_jbig2dec: Callable[..., None]):
    xobj, _pdf = first_image_in('jbig2global.pdf')
    pim = PdfImage(xobj)

    # We patch jbig2dec to return a blank version string, or raise an error.
    # Some compiled versions of jbig2dec in the wild such as DietPi OS don't
    # return a version string.
    def run_claim_no_version(args, *pargs, **kwargs):
        if args[1] == '--version':
            return subprocess.CompletedProcess(args, 0, stdout='', stderr='')
        raise subprocess.CalledProcessError(1, 'jbig2dec')

    patch_jbig2dec(run_claim_no_version)

    # Blank version is treated as unknown-but-present; decode then fails.
    pim = PdfImage(xobj)
    with pytest.raises(DataDecodingError, match="jbig2dec failed to decode"):
        pim.as_pil_image()


def test_decode_jbig2_wraps_called_process_error(patch_jbig2dec: Callable[..., None]):
    def run_claim_broken(args, *pargs, **kwargs):
        if args[1] == '--version':
            return subprocess.CompletedProcess(args, 0, stdout='0.15', stderr='')
        raise subprocess.CalledProcessError(1, 'jbig2dec', stderr=b'segment too short')

    patch_jbig2dec(run_claim_broken)
    decoder = pikepdf.jbig2.get_decoder()
    with pytest.raises(DataDecodingError, match="segment too short") as excinfo:
        decoder.decode_jbig2(b'\x00' * 20, b'')
    assert isinstance(excinfo.value.__cause__, subprocess.CalledProcessError)


@needs_jbig2dec
def test_jbig2_invalid_payload_is_data_decoding_error():
    """Owner repro from #735: invalid JBIG2 data must not leak RuntimeError."""
    pdf = Pdf.new()
    st = pdf.make_stream(b'\x00' * 50)
    st.Type, st.Subtype = Name.XObject, Name.Image
    st.Width, st.Height, st.BitsPerComponent = 20, 20, 1
    st.ColorSpace = Name.DeviceGray
    st.Filter = pikepdf.Array([Name.JBIG2Decode])
    with pytest.raises(DataDecodingError):
        PdfImage(st).as_pil_image()
