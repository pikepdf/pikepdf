import pytest
from pikepdf import _qpdf as qpdf

import os
import platform
import shutil
from contextlib import suppress


def test_split_pdf(resources, outdir):
    q = qpdf.QPDF.open(resources / "fourpages.pdf")

    for n, page in enumerate(q.pages):
        outpdf = qpdf.QPDF.new()
        outpdf.add_page(page, False)
        outpdf.save(outdir / "page{}.pdf".format(n + 1))

    assert len([f for f in outdir.iterdir() if f.name.startswith('page')]) == 4
