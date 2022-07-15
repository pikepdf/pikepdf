import pytest

from pikepdf import Array, Dictionary, Name, NumberTree, Pdf

# pylint: disable=redefined-outer-name


@pytest.fixture
def pagelabels_pdf():
    with Pdf.new() as pdf:
        for _ in range(5):
            pdf.add_blank_page()
        pdf.Root.PageLabels = pdf.make_indirect(
            Dictionary(
                Nums=Array(
                    [
                        0,  # new label rules begin at index 0
                        Dictionary(S=Name.r),  # use lowercase roman numerals, until...
                        2,  # new label rules begin at index 2
                        Dictionary(
                            S=Name.D, St=42, P='Prefix-'
                        ),  # label pages as 'Prefix-42', 'Prefix-43', ...
                    ]
                )
            )
        )
        yield pdf


def test_numbertree_crud(pagelabels_pdf):
    pdf = pagelabels_pdf
    nt = NumberTree(pdf.Root.PageLabels)
    assert nt.obj == pdf.Root.PageLabels
    assert 0 in nt
    assert isinstance(nt[0], Dictionary)
    assert 'foo' not in nt

    assert 2 in nt
    del nt[2]
    assert 2 not in nt

    message = "Life, universe, everything"
    nt[42] = Dictionary(Entry=message)
    assert 42 in nt
    assert nt[42].Entry == message


def test_numbertree_iter(pagelabels_pdf):
    pdf = pagelabels_pdf
    count = 0
    nt = NumberTree(pdf.Root.PageLabels)
    for name in nt:
        count += 1
        assert name in nt
    assert count == len(nt)

    assert 2 in nt.keys()
    assert len(nt.keys()) == len(nt.values()) == len(nt.items())
    assert nt == NumberTree(pdf.Root.PageLabels)


def test_numbertree_without_pdf():
    d = Dictionary()
    with pytest.raises(ValueError, match="owned"):
        _nt = NumberTree(d)


def test_numbertree_relabeling(pagelabels_pdf):
    pdf = pagelabels_pdf
    nt = NumberTree(pdf.Root.PageLabels)

    assert pdf.pages[1].label == 'ii'
    nt[0] = Dictionary(S=Name.R)
    assert pdf.pages[1].label == 'II'
