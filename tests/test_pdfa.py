# SPDX-FileCopyrightText: 2022 James R. Barlow
# SPDX-License-Identifier: CC0-1.0

from __future__ import annotations

import os
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
from subprocess import PIPE, STDOUT, run

import pytest

from pikepdf import Pdf

VERAPDF: list[str] = []
try:
    verapdf_path = Path(os.environ['HOME']) / 'verapdf' / 'verapdf'
    if verapdf_path.is_file():
        VERAPDF = [os.fspath(verapdf_path)]
    else:
        verapdf_flatpak = [
            'flatpak',
            'run',
            '--filesystem=host:ro',
            f'--filesystem={tempfile.gettempdir()}:ro',
            '--command=verapdf',
            'org.verapdf.veraPDF',
        ]
        run([*verapdf_flatpak, '--version'], check=True)
        VERAPDF = verapdf_flatpak
except Exception:  # pylint: disable=broad-except
    pass


def verapdf_validate(filename) -> bool:
    assert VERAPDF
    proc = run([*VERAPDF, os.fspath(filename)], stdout=PIPE, stderr=STDOUT, check=True)
    result = proc.stdout.decode('utf-8')
    xml_start = result.find('<?xml version')
    xml = result[xml_start:]
    root = ET.fromstring(xml)
    node = root.find(".//validationReport")
    if node is None:
        raise NotImplementedError("Unexpected XML returned by verapdf")

    compliant = node.attrib['isCompliant'] == 'true'
    if not compliant:
        print(result)
    return compliant


@pytest.fixture
def verapdf():
    if not VERAPDF:
        pytest.skip("verapdf not available")
    return verapdf_validate


@pytest.mark.parametrize(
    'filename, pdfa, pdfx',
    [
        ('veraPDF test suite 6-2-10-t02-pass-a.pdf', '1B', ''),
        ('pal.pdf', '', ''),
        ('pdfx.pdf', '', 'PDF/X-4'),
    ],
)
def test_pdfa_pdfx_status(resources, filename, pdfa, pdfx):
    with Pdf.open(resources / filename) as pdf:
        m = pdf.open_metadata()
        assert m.pdfa_status == pdfa
        assert m.pdfx_status == pdfx


def test_pdfa_sanity(resources, outdir, verapdf):
    filename = resources / 'veraPDF test suite 6-2-10-t02-pass-a.pdf'

    assert verapdf(filename)

    with Pdf.open(filename) as pdf:
        pdf.save(outdir / 'pdfa.pdf')

        assert verapdf(outdir / 'pdfa.pdf')
        m = pdf.open_metadata()
        assert m.pdfa_status == '1B'
        assert m.pdfx_status == ''

    with Pdf.open(resources / 'graph.pdf') as pdf:
        m = pdf.open_metadata()
        assert m.pdfa_status == ''


def test_pdfa_modify(resources, outdir, verapdf):
    sandwich = resources / 'sandwich.pdf'
    assert verapdf(sandwich)

    with Pdf.open(sandwich) as pdf:
        with pdf.open_metadata(
            update_docinfo=False, set_pikepdf_as_editor=False
        ) as meta:
            pass
        with pytest.raises(RuntimeError, match="not opened"):
            del meta['pdfaid:part']
        pdf.save(outdir / '1.pdf')
    assert verapdf(outdir / '1.pdf')

    with Pdf.open(sandwich) as pdf:
        with pdf.open_metadata(
            update_docinfo=False, set_pikepdf_as_editor=True
        ) as meta:
            pass
        pdf.save(outdir / '2.pdf')
    assert verapdf(outdir / '2.pdf')

    with Pdf.open(sandwich) as pdf:
        with pdf.open_metadata(update_docinfo=True, set_pikepdf_as_editor=True) as meta:
            meta['dc:source'] = 'Test'
            meta['dc:title'] = 'Title Test'
        pdf.save(outdir / '3.pdf')
    assert verapdf(outdir / '3.pdf')


def test_pdfa_creator(resources, caplog):
    sandwich = resources / 'sandwich.pdf'

    with Pdf.open(sandwich) as pdf:
        with pdf.open_metadata(
            update_docinfo=False, set_pikepdf_as_editor=False
        ) as meta:
            meta['dc:creator'] = 'The Creator'
        messages = [
            rec.message
            for rec in caplog.records
            if rec.message.startswith('dc:creator')
        ]
        if not messages:
            pytest.fail("Failed to warn about setting dc:creator to a string")
