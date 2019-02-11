import os
import xml.etree.ElementTree as ET
from pathlib import Path
from subprocess import PIPE, STDOUT, run

import pytest

from pikepdf import Pdf

try:
    VERAPDF = Path(os.environ['HOME']) / 'verapdf' / 'verapdf'
    if not VERAPDF.is_file():
        VERAPDF = None
except Exception:  # pylint: disable=w0703
    VERAPDF = None

pytestmark = pytest.mark.skipif(not VERAPDF, reason="verapdf not found")


def verapdf_validate(filename):
    proc = run([VERAPDF, filename], stdout=PIPE, stderr=STDOUT, check=True)
    result = proc.stdout.decode('utf-8')
    xml_start = result.find('<?xml version')
    xml = result[xml_start:]
    root = ET.fromstring(xml)
    node = root.find(".//validationReports")
    result = node.attrib['compliant'] == '1' and node.attrib['failedJobs'] == '0'
    if not result:
        print(proc.stdout.decode())
    return result


def test_pdfa_sanity(resources, outdir):
    filename = resources / 'veraPDF test suite 6-2-10-t02-pass-a.pdf'

    assert verapdf_validate(filename)

    pdf = Pdf.open(filename)
    pdf.save(outdir / 'pdfa.pdf')

    assert verapdf_validate(outdir / 'pdfa.pdf')
    assert pdf.open_metadata().pdfa_status == '1B'


def test_pdfa_modify(resources, outdir):
    sandwich = resources / 'sandwich.pdf'
    assert verapdf_validate(sandwich)

    pdf = Pdf.open(sandwich)
    with pdf.open_metadata(update_docinfo=False, set_pikepdf_as_editor=False) as meta:
        pass
    pdf.save(outdir / '1.pdf')
    assert verapdf_validate(outdir / '1.pdf')

    pdf = Pdf.open(sandwich)
    with pdf.open_metadata(update_docinfo=False, set_pikepdf_as_editor=True) as meta:
        pass
    pdf.save(outdir / '2.pdf')
    assert verapdf_validate(outdir / '2.pdf')

    pdf = Pdf.open(sandwich)
    with pdf.open_metadata(update_docinfo=True, set_pikepdf_as_editor=True) as meta:
        meta['dc:source'] = 'Test'
        meta['dc:title'] = 'Title Test'
    pdf.save(outdir / '3.pdf')
    assert verapdf_validate(outdir / '3.pdf')
