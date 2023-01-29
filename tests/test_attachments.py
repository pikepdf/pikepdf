# SPDX-FileCopyrightText: 2022 James R. Barlow
# SPDX-License-Identifier: CC0-1.0

from __future__ import annotations

import datetime
import os
from hashlib import md5
from pathlib import Path

import pytest

import pikepdf
from pikepdf import Name, Pdf
from pikepdf._core import AttachedFile, AttachedFileSpec, Attachments


@pytest.fixture
def pal(resources):
    yield Pdf.open(resources / 'pal.pdf')


def test_attachment_crud(pal, resources, outpdf):
    assert hasattr(pal, 'attachments'), "no attachments interface"
    assert len(pal.attachments) == 0, "test file already has attachments"
    assert 'anything' not in pal.attachments, "attachment interface is quirky"

    rle = resources / 'rle.pdf'
    fs = AttachedFileSpec.from_filepath(pal, rle)
    rle_bytes = rle.read_bytes()

    pal.attachments['rle.pdf'] = fs

    assert len(pal.attachments) == 1, "attachment count not incremented"
    assert 'rle.pdf' in pal.attachments, "attachment filename not registered"
    assert 'attached' in repr(pal.attachments)

    pal.save(outpdf)

    with Pdf.open(outpdf) as output:
        assert len(output.attachments) == 1, "output had no attachment"
        assert 'rle.pdf' in output.attachments, "filename not present"
        rle_spec = output.attachments['rle.pdf']
        rle_file = rle_spec.get_file()
        assert (
            rle_bytes == rle_file.read_bytes()
        ), "attachment not reproduced bit for bit"

        del output.attachments['rle.pdf']
        assert 'rle.pdf' not in output.attachments, "del failed"
        assert len(output.attachments) == 0, "not removed"

    with Pdf.open(outpdf) as output:
        output.attachments.pop('rle.pdf')


def test_attachment_iter(pal):
    inputs = ['1', '2']

    for input_ in inputs:
        pal.attachments[f'filename {input_}'] = AttachedFileSpec(
            pal, input_.encode('ascii')
        )

    for filename in pal.attachments:
        fileno = filename.replace('filename ', '')
        assert fileno in inputs
        filespec = pal.attachments[filename]
        assert filespec.get_file().read_bytes().decode('ascii') in inputs


def test_filespec_types(pal, resources):
    some_bytes = b'just some bytes'
    some_path = resources / 'rle.pdf'
    assert isinstance(some_path, Path)

    fs_bytes = AttachedFileSpec(pal, some_bytes)
    assert fs_bytes.get_file().read_bytes() == some_bytes
    assert fs_bytes.filename == ''

    fs_path = AttachedFileSpec.from_filepath(pal, some_path)
    assert fs_path.get_file().read_bytes() == some_path.read_bytes()

    with pytest.raises(TypeError):
        fs_path.get_file(pikepdf.Array([1]))


def test_attachment_metadata(pal, data=b'some data', description='test filespec'):
    fs = AttachedFileSpec(pal, data, description=description)

    assert fs.description == description
    fs.description = 'xyz'
    assert fs.description == 'xyz'

    attached_stream = fs.get_file()
    assert attached_stream.creation_date is None
    assert attached_stream.mod_date is None

    june_1 = datetime.datetime(2021, 6, 1, 1, 2, 3)

    attached_stream.creation_date = june_1
    attached_stream.mod_date = june_1
    assert attached_stream.creation_date == june_1
    assert attached_stream.mod_date == june_1

    assert attached_stream.size == len(data)

    assert attached_stream.mime_type == ''
    attached_stream.mime_type = 'text/plain'
    assert attached_stream.mime_type == 'text/plain'


def test_compound_attachment(pal):
    data = [b'data stream 1', b'data stream 2']
    filename = [b'filename of data stream 1', b'filename of data stream 2']

    fs = AttachedFileSpec(pal, data[0], description='test filespec')
    fs.filename = 'compound filespec'
    fs.obj.UF = filename[0]

    # Add another data stream to the underlying object
    fs.obj.EF.F = pal.make_stream(data[1], Type=Name.EmbeddedFile)
    fs.obj.F = filename[1]

    all_filenames = fs.get_all_filenames()
    assert len(all_filenames) == 2
    assert Name.F in all_filenames
    assert Name.UF in all_filenames
    assert all_filenames[Name.UF] == filename[0]
    assert all_filenames[Name.F] == filename[1]

    assert fs.get_file().read_bytes() == data[0]
    assert fs.get_file(Name.UF).read_bytes() == data[0]
    assert fs.get_file(Name.F).read_bytes() == data[1]

    assert fs.get_file().md5 == md5(data[0]).digest()

    pal.attachments['compound'] = fs


def test_from_str_filepath(pal, outdir):
    foofile = outdir / 'foo'
    foofile.touch()
    fs = AttachedFileSpec.from_filepath(pal, str(foofile), description='bar')
    assert os.sep not in fs.filename
    assert 'foo' in repr(fs)
    fs.filename = ''
    assert 'foo' not in repr(fs)
    assert 'AttachedFile' in repr(fs.get_file())
