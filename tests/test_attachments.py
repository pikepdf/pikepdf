from hashlib import md5
from pathlib import Path

import pytest

from pikepdf import Dictionary, Name, Pdf
from pikepdf._qpdf import AttachedFileStream, Attachments, FileSpec


@pytest.fixture
def pal(resources):
    yield Pdf.open(resources / 'pal.pdf')


def test_attachment_crud(pal, resources, outpdf):
    assert hasattr(pal, 'attachments'), "no attachments interface"
    assert len(pal.attachments) == 0, "test file already has attachments"
    assert 'anything' not in pal.attachments, "attachment interface is quirky"

    with open(resources / 'rle.pdf', 'rb') as rle:
        rle_bytes = rle.read()
        rle.seek(0)
        fs = FileSpec(pal, rle)

    pal.attachments['rle.pdf'] = fs

    assert len(pal.attachments) == 1, "attachment count not incremented"
    assert 'rle.pdf' in pal.attachments, "attachment filename not registered"

    pal.save(outpdf)

    with Pdf.open(outpdf) as output:
        assert len(output.attachments) == 1, "output had no attachment"
        assert 'rle.pdf' in output.attachments, "filename not present"
        rle_spec = output.attachments['rle.pdf']
        rle_file = rle_spec.get_stream()
        assert (
            rle_bytes == rle_file.read_bytes()
        ), "attachment not reproduced bit for bit"


def test_filespec_types(pal, resources):
    some_bytes = b'just some bytes'
    some_path = resources / 'rle.pdf'
    assert isinstance(some_path, Path)

    fs_bytes = FileSpec(pal, some_bytes)
    assert fs_bytes.get_stream().read_bytes() == some_bytes

    fs_path = FileSpec(pal, some_path)
    assert fs_path.get_stream().read_bytes() == some_path.read_bytes()


def test_compound_attachment(pal):
    data = [b'data stream 1', b'data stream 2']
    filename = [b'filename of data stream 1', b'filename of data stream 2']

    fs = FileSpec(pal, data[0], description='test filespec')
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

    assert fs.get_stream().read_bytes() == data[0]
    assert fs.get_stream(Name.UF).read_bytes() == data[0]
    assert fs.get_stream(Name.F).read_bytes() == data[1]

    assert fs.get_stream().md5 == md5(data[0]).digest()
