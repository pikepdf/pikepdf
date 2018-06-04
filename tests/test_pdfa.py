import pytest
from pikepdf import Pdf
import os
import platform
import shutil
from pathlib import Path
from contextlib import suppress
from subprocess import run, PIPE, STDOUT, DEVNULL
import xml.etree.ElementTree as ET


try:
    VERAPDF = Path(os.environ['HOME']) / 'verapdf' / 'verapdf'
    NO_PDFA_VALIDATOR = not VERAPDF.is_file()
except Exception:
    NO_PDFA_VALIDATOR = True


def verapdf_validate(filename):
    with open(filename, 'rb') as f:
        proc = run([VERAPDF], stdin=f, stdout=PIPE, stderr=STDOUT, check=True)
        result = proc.stdout.decode('utf-8')

        xml_start = result.find('<?xml version')
        xml = result[xml_start:]

    root = ET.fromstring(xml)
    node = root.find(".//taskResult[@type='VALIDATE']")
    return node.attrib['isExecuted'] == 'true' and \
            node.attrib['isSuccess'] == 'true'


@pytest.mark.skipif(NO_PDFA_VALIDATOR, reason="can't find verapdf")
def test_pdfa_sanity(resources, outdir):
    filename = resources / 'veraPDF test suite 6-2-10-t02-pass-a.pdf'

    assert verapdf_validate(filename)

    pdf = Pdf.open(filename)
    pdf.save(outdir / 'pdfa.pdf')

    assert verapdf_validate(outdir / 'pdfa.pdf')
