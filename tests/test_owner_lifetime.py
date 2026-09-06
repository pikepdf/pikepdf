# SPDX-FileCopyrightText: 2025 James R. Barlow
# SPDX-License-Identifier: CC0-1.0

"""Objects that outlive the Pdf they were removed from.

A direct object adopted by a Pdf records a raw pointer to that document. If the
object is detached from the object graph and the Pdf is then closed, qpdf's
destructor never disconnects it, leaving a dangling pointer. pikepdf must
notice that the owner is gone rather than hand the stale pointer back to qpdf.
"""

from __future__ import annotations

import gc

import pikepdf
from pikepdf import Dictionary, Name


class TestDetachedObjectOutlivesOwner:
    def test_dictionary_reinserted_into_new_pdf(self):
        pdf = pikepdf.new()
        d = Dictionary(A=1, B=Dictionary(C=2))
        pdf.Root.D = d
        assert d.is_owned_by(pdf)
        del pdf.Root.D
        pdf.close()
        del pdf
        gc.collect()  # the QPDF is now destroyed; d keeps a dangling owner

        pdf2 = pikepdf.new()
        assert not d.is_owned_by(pdf2)
        pdf2.Root.X = d
        assert d.is_owned_by(pdf2)
        assert int(d.A) == 1
        assert int(d.B.C) == 2

    def test_with_same_owner_as_after_owner_death(self):
        pdf = pikepdf.new()
        d = Dictionary(A=1, B=Dictionary(C=2))
        pdf.Root.D = d
        del pdf.Root.D
        pdf.close()
        del pdf
        gc.collect()  # the QPDF is now destroyed; d keeps a dangling owner

        pdf2 = pikepdf.new()
        adopted = d.with_same_owner_as(pdf2.Root)
        assert adopted.is_owned_by(pdf2)
        assert int(adopted.A) == 1
        assert int(adopted.B.C) == 2

    def test_same_owner_as_after_owner_death(self):
        pdf = pikepdf.new()
        d = Dictionary(A=1)
        pdf.Root.D = d
        del pdf.Root.D
        pdf.close()
        del pdf
        gc.collect()  # the QPDF is now destroyed; d keeps a dangling owner

        pdf2 = pikepdf.new()
        assert not d.same_owner_as(pdf2.Root)

    def test_make_indirect_after_owner_death(self):
        pdf = pikepdf.new()
        d = Dictionary(A=1)
        pdf.Root.D = d
        del pdf.Root.D
        pdf.close()
        del pdf
        gc.collect()  # the QPDF is now destroyed; d keeps a dangling owner

        pdf2 = pikepdf.new()
        indirect = pdf2.make_indirect(d)
        assert indirect.is_indirect
        assert indirect.is_owned_by(pdf2)

    def test_scalar_detached_from_dead_owner(self):
        pdf = pikepdf.new()
        pdf.Root.X = 42
        x = pdf.Root.get_raw('/X')
        assert x.is_owned_by(pdf)
        del pdf.Root.X
        pdf.close()
        del pdf
        gc.collect()  # the QPDF is now destroyed; d keeps a dangling owner

        pdf2 = pikepdf.new()
        assert not x.is_owned_by(pdf2)
        pdf2.Root.Y = x
        assert int(pdf2.Root.get_raw('/Y')) == 42

    def test_parsed_direct_object_outlives_file(self, resources):
        pdf = pikepdf.open(resources / 'graph.pdf')
        mediabox = pdf.pages[0].obj.get_raw('/MediaBox')
        assert mediabox.is_owned_by(pdf)
        del pdf.pages[0].obj['/MediaBox']
        pdf.close()
        del pdf
        gc.collect()  # the QPDF is now destroyed; d keeps a dangling owner

        pdf2 = pikepdf.new()
        assert not mediabox.is_owned_by(pdf2)
        pdf2.Root.Box = mediabox
        assert mediabox.is_owned_by(pdf2)
        assert len(mediabox) == 4

    def test_name_constant_still_usable(self):
        pdf = pikepdf.new()
        pdf.Root.T = Name.Page
        pdf.close()
        del pdf
        gc.collect()  # the QPDF is now destroyed; d keeps a dangling owner
        pdf2 = pikepdf.new()
        pdf2.Root.T = Name.Page
        assert pdf2.Root.T == Name.Page
