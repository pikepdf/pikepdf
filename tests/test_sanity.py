# SPDX-FileCopyrightText: 2022 James R. Barlow
# SPDX-License-Identifier: CC0-1.0

"""
A bunch of quick tests that confirm nothing is horribly wrong
"""

from __future__ import annotations

import ast
import gc
import sys
from contextlib import suppress
from pathlib import Path
from shutil import copy

import pytest

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib  # type: ignore

from packaging.version import Version

import pikepdf
from pikepdf import Name, Object, Page, Pdf, Stream


def test_minimum_qpdf_version():
    from pikepdf import _core

    with open(Path(__file__).parent / '../pyproject.toml', 'rb') as f:
        pyproject_toml = tomllib.load(f)
    toml_env = pyproject_toml['tool']['cibuildwheel']['environment']
    assert Version(_core.qpdf_version()) >= Version(toml_env['QPDF_MIN_VERSION'])


def test_inspection_mode():
    from pikepdf.settings import get_inspection_mode, set_inspection_mode
    assert get_inspection_mode() is False
    set_inspection_mode(False)
    assert get_inspection_mode() is False


def test_inspection_mode_enable():
    import subprocess
    import textwrap

    # do not pollute main process with irreversible global flag
    script = textwrap.dedent("""\
        from pikepdf.settings import get_inspection_mode, set_inspection_mode
        from sys import exit
        if get_inspection_mode():
            sys.exit(1)
        set_inspection_mode(True)
        if not get_inspection_mode():
            sys.exit(1)
        try:
            set_inspection_mode(False)
        except RuntimeError:
            pass
        else:
            sys.exit(1)
        if not get_inspection_mode():
            sys.exit(1)
        else:
            print("ok")
            sys.exit(0)
    """)
    result = subprocess.run(
        [sys.executable, '-c', script],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == 'ok'


def test_open_pdf(resources):
    pdf = pikepdf.open(resources / 'graph.pdf')
    assert '1.3' <= pdf.pdf_version <= '1.7'
    assert pdf.Root['/Pages']['/Count'] == 1
    pdf.close()


def test_open_pdf_password(resources):
    with Pdf.open(resources / 'graph-encrypted.pdf', password='owner') as pdf:
        assert pdf.Root['/Pages']['/Count'] == 1


def test_attr_access(resources):
    with Pdf.open(resources / 'graph.pdf') as pdf:
        assert int(pdf.Root.Pages.Count) == 1


def test_create_pdf(outdir):
    pdf = Pdf.new()

    font = pdf.make_indirect(
        Object.parse(
            b"""
            <<
                /Type /Font
                /Subtype /Type1
                /Name /F1
                /BaseFont /Helvetica
                /Encoding /WinAnsiEncoding
            >>"""
        )
    )

    width, height = 100, 100
    image_data = b"\xff\x7f\x00" * (width * height)

    image = Stream(pdf, image_data)
    image.stream_dict = Object.parse(
        b"""
            <<
                /Type /XObject
                /Subtype /Image
                /ColorSpace /DeviceRGB
                /BitsPerComponent 8
                /Width 100
                /Height 100
            >>"""
    )

    rfont = {'/F1': font}

    xobj = {'/Im1': image}

    resources = {'/Font': rfont, '/XObject': xobj}

    mediabox = [0, 0, 612, 792]

    stream = b"""
        BT /F1 24 Tf 72 720 Td (Hi there) Tj ET
        q 144 0 0 144 234 324 cm /Im1 Do Q
        """

    contents = Stream(pdf, stream)

    page_dict = {
        '/Type': Name('/Page'),
        '/MediaBox': mediabox,
        '/Contents': contents,
        '/Resources': resources,
    }
    qpdf_page_dict = page_dict
    page = Page(pdf.make_indirect(qpdf_page_dict))

    pdf.pages.append(page)
    pdf.save(outdir / 'hi.pdf')


def test_copy_semantics(resources):
    with Pdf.open(resources / 'graph.pdf') as pdf:
        # Ensure that we can name a reference to a child object and view the
        # changes from the parent
        page = pdf.pages[0]
        mediabox = page['/MediaBox']
        assert mediabox[2] != 0
        mediabox[2] = 0
        assert page['/MediaBox'][2] == mediabox[2]


def test_copy_page_keepalive(resources, outdir):
    copy(resources / 'sandwich.pdf', outdir / 'sandwich.pdf')
    src = Pdf.open(outdir / 'sandwich.pdf')  # no with clause
    pdf = Pdf.open(resources / 'graph.pdf')

    pdf.pages.append(src.pages[0])

    del src

    gc.collect()
    with suppress(PermissionError):
        (outdir / 'sandwich.pdf').unlink()
    pdf.save(outdir / 'out.pdf')
    pdf.close()


def test_open_save(resources, outdir):
    out = str(outdir / 'graph.pdf')
    copy(str(resources / 'graph.pdf'), out)
    with Pdf.open(out) as src:
        with pytest.raises(ValueError):
            src.save(out)
        src.save(outdir / 'graph2.pdf')


def test_readme_examples():
    readme_filename = Path(__file__).parent.with_name('README.md')
    if not readme_filename.exists():  # In case it's not in some sdist/wheel/etc.
        pytest.skip('no README')
    readme = readme_filename.read_text()

    # Extract all Python code blocks from README
    blocks = []
    current_block: list[str] = []
    in_block = False
    for line in readme.splitlines():
        if line.startswith('```python'):
            in_block = True
            current_block = []
            continue
        elif line.startswith('```') and in_block:
            in_block = False
            blocks.append('\n'.join(current_block))
            continue
        if in_block:
            current_block.append(line)

    assert blocks, "No Python code blocks found in README.md"
    for i, code in enumerate(blocks):
        ast.parse(code, filename=f'README.md block {i + 1}')
        compile(code, filename=f'README.md block {i + 1}', mode='exec')
