from pathlib import Path

import pytest

from pikepdf import Dictionary, Name, Pdf
from pikepdf._qpdf import AttachedFile, Attachments, FileSpec


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
        fs = FileSpec(pal, 'rle.pdf', rle)

    pal.attachments['rle.pdf'] = fs

    assert len(pal.attachments) == 1, "attachment count not incremented"
    assert 'rle.pdf' in pal.attachments, "attachment filename not registered"

    pal.save(outpdf)

    with Pdf.open(outpdf) as output:
        assert len(output.attachments) == 1, "output had no attachment"
        assert 'rle.pdf' in output.attachments, "filename not present"
        rle_spec = output.attachments['rle.pdf']
        rle_file = rle_spec.get_attached_file()
        assert (
            rle_bytes == rle_file.read_bytes()
        ), "attachment not reproduced bit for bit"


def test_filespec_types(pal, resources):
    some_bytes = b'just some bytes'
    some_path = resources / 'rle.pdf'
    assert isinstance(some_path, Path)

    fs_bytes = FileSpec(pal, 'somebytes.dat', some_bytes)
    assert fs_bytes.get_attached_file().read_bytes() == some_bytes

    fs_path = FileSpec(pal, 'resources/rle.pdf', some_path)
    assert fs_path.get_attached_file().read_bytes() == some_path.read_bytes()
