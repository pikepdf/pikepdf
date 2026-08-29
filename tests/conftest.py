# SPDX-FileCopyrightText: 2022 James R. Barlow
# SPDX-License-Identifier: CC0-1.0

from __future__ import annotations

import os
import platform
import shutil
import sys
import tempfile
import xml.etree.ElementTree as ET
from functools import cache
from pathlib import Path
from subprocess import PIPE, STDOUT, CalledProcessError, run

from packaging.version import Version

try:
    from pikepdf import __libqpdf_version__
except ImportError:
    __libqpdf_version__ = '0.0.0'


import pytest

from pikepdf import Array, Dictionary, Name, Pdf, StructElem

TESTS_ROOT = os.path.abspath(os.path.dirname(__file__))
PROJECT_ROOT = os.path.dirname(TESTS_ROOT)

STRUCTURE_TEXT = b"""BT /F2 24 Tf 72 700 Td (Heading) Tj ET
BT /F1 12 Tf 72 660 Td (Body one) Tj ET
BT /F1 12 Tf 72 640 Td (Body two) Tj ET
q 1 0 0 1 0 0 cm 0 0 10 10 re f Q
"""


def set_structure_contents(pdf, page, data):
    page.obj.Contents = Array([])
    page.contents_add(data)
    page.contents_coalesce()


def structure_registration_failure(target):
    original = StructElem._add_content_prechecked

    def fail_target(
        element,
        page_arg,
        mcid,
        *,
        stream_obj,
        stream_owner_obj=None,
        state,
        prechecked_k=False,
    ):
        if element is target:
            raise RuntimeError("injected failure")
        return original(
            element,
            page_arg,
            mcid,
            stream_obj=stream_obj,
            stream_owner_obj=stream_owner_obj,
            state=state,
            prechecked_k=prechecked_k,
        )

    return fail_target


@pytest.fixture(name="blank")
def structure_blank():
    with Pdf.new() as pdf:
        pdf.add_blank_page()
        yield pdf


@pytest.fixture(name="text_pdf")
def structure_text_pdf():
    with Pdf.new() as pdf:
        page = pdf.add_blank_page()
        page.obj.Resources = Dictionary(
            Font=Dictionary(
                F1=pdf.make_indirect(
                    Dictionary(
                        Type=Name.Font,
                        Subtype=Name.Type1,
                        BaseFont=Name.Helvetica,
                    )
                ),
                F2=pdf.make_indirect(
                    Dictionary(
                        Type=Name.Font,
                        Subtype=Name.Type1,
                        BaseFont=Name('/Helvetica-Bold'),
                    )
                ),
            )
        )
        set_structure_contents(pdf, page, STRUCTURE_TEXT)
        yield pdf


@pytest.fixture(scope="session")
def resources():
    return Path(TESTS_ROOT) / 'resources'


@pytest.fixture(scope="function")
def outdir(tmp_path):
    return tmp_path


@pytest.fixture(scope="function")
def outpdf(tmp_path):
    return tmp_path / 'out.pdf'


@pytest.fixture
def refcount():
    if platform.python_implementation() == 'PyPy':
        pytest.skip(reason="test isn't valid for PyPy")
    return sys.getrefcount


skip_if_pypy = pytest.mark.skipif(
    platform.python_implementation() == 'PyPy', reason="test isn't valid for PyPy"
)
fails_if_pypy = pytest.mark.xfail(
    platform.python_implementation() == 'PyPy', reason="test known to fail on PyPy"
)
skip_if_ci = pytest.mark.skipif(
    os.environ.get('CI', '') == 'true', reason="test too slow for CI"
)
fails_if_no_mutool = pytest.mark.xfail(
    shutil.which("mutool") is None, reason="test fails without mutool"
)


def needs_libqpdf_v(version: str, *, reason=None):
    if reason is None:
        reason = "installed libqpdf is too old for this test"
    return pytest.mark.skipif(
        Version(__libqpdf_version__) <= Version(version),
        reason=reason,
    )


def needs_python_v(version: str, *, reason=None):
    if reason is None:
        reason = "only works on newer Python versions"
    return pytest.mark.skipif(
        Version(platform.python_version()) <= Version(version), reason=reason
    )


@cache
def _find_verapdf() -> list[str]:
    on_path = shutil.which('verapdf')
    if on_path:
        return [on_path]
    home = os.environ.get('HOME')
    if home:
        installed = Path(home) / 'verapdf' / 'verapdf'
        if installed.is_file():
            return [os.fspath(installed)]
    flatpak = [
        'flatpak',
        'run',
        '--filesystem=host:ro',
        f'--filesystem={tempfile.gettempdir()}:ro',
        '--command=verapdf',
        'org.verapdf.veraPDF',
    ]
    try:
        run([*flatpak, '--version'], check=True, stdout=PIPE, stderr=STDOUT)
    except (OSError, CalledProcessError):
        return []
    return flatpak


def verapdf_report(filename, flavour: str | None = None) -> ET.Element:
    """Run veraPDF and return the parsed <validationReport> element."""
    verapdf = _find_verapdf()
    assert verapdf
    args = [*verapdf, '--format', 'xml']
    if flavour:
        args += ['--flavour', flavour]
    # veraPDF exits non-zero for a non-compliant file, which is a result, not
    # an error, so the report is parsed regardless of the exit status.
    proc = run([*args, os.fspath(filename)], stdout=PIPE, stderr=STDOUT, check=False)
    result = proc.stdout.decode('utf-8')
    start = result.find('<?xml version')
    node = (
        ET.fromstring(result[start:]).find(".//validationReport")
        if start >= 0
        else None
    )
    if node is None:
        raise NotImplementedError(f"Unexpected output from verapdf: {result[:400]}")
    return node


def verapdf_validate(filename) -> bool:
    node = verapdf_report(filename)
    compliant = node.attrib['isCompliant'] == 'true'
    if not compliant:
        print(ET.tostring(node, encoding='unicode'))
    return compliant


@pytest.fixture
def verapdf():
    if not _find_verapdf():
        pytest.skip("verapdf not available")
    return verapdf_validate


@pytest.fixture
def verapdf_rules():
    if not _find_verapdf():
        pytest.skip("verapdf not available")
    return verapdf_report
