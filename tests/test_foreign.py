import pytest

from pikepdf import Dictionary, ForeignObjectError, Name, Object, Pdf, Stream


@pytest.fixture
def vera(resources):
    # Has XMP but no docinfo
    return Pdf.open(resources / 'veraPDF test suite 6-2-10-t02-pass-a.pdf')


@pytest.fixture
def outlines(resources):
    return Pdf.open(resources / 'outlines.pdf')


def test_must_use_copy_foreign(vera, outlines, outpdf):
    vera.Root.Names = Dictionary()
    vera.Root.Names.Dests = outlines.Root.Names.Dests
    with pytest.raises(ForeignObjectError):
        vera.save(outpdf)
