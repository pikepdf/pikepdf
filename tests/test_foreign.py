import pytest

from pikepdf import Dictionary, ForeignObjectError, Name, Object, Pdf, Stream


@pytest.fixture
def vera(resources):
    # Has XMP but no docinfo
    return Pdf.open(resources / 'veraPDF test suite 6-2-10-t02-pass-a.pdf')


@pytest.fixture
def outlines(resources):
    return Pdf.open(resources / 'outlines.pdf')


def test_no_foreign_on_direct(vera):
    direct_object = Dictionary()
    with pytest.raises(ForeignObjectError, match="called with direct object"):
        vera.copy_foreign(direct_object)


def test_must_use_copy_foreign(vera, outlines, outpdf):
    vera.Root.Names = Dictionary()
    vera.Root.Names.Dests = outlines.Root.Names.Dests
    with pytest.raises(ForeignObjectError, match="add objects from another file"):
        vera.save(outpdf)


def test_self_copy_foreign(vera):
    direct_object = Dictionary()
    indirect_object = vera.make_indirect(direct_object)
    assert indirect_object.is_indirect
    with pytest.raises(ForeignObjectError, match="called with object from"):
        vera.Root.IndirectObj = vera.copy_foreign(indirect_object)


def test_copy_foreign_copies(vera, outlines, outpdf):
    assert outlines.Root.Names.is_indirect
    assert outlines.Root.Names.is_owned_by(outlines)

    vera.Root.Names = vera.copy_foreign(outlines.Root.Names)
    assert vera.Root.Names.is_owned_by(vera)
    assert not outlines.Root.Names.is_owned_by(vera)
    vera.save(outpdf)
