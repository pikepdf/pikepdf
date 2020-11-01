# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
#
# Copyright (C) 2017, James R. Barlow (https://github.com/jbarlow83/)

"""
Support functions called by the C++ library binding layer. Not intended to be
called from Python, and subject to change at any time.
"""


from pikepdf import Name, Pdf


def update_xmp_pdfversion(pdf: Pdf, version: str):

    if Name.Metadata not in pdf.Root:
        return  # Don't create an empty XMP object just to store the version

    with pdf.open_metadata(set_pikepdf_as_editor=False, update_docinfo=False) as meta:
        if 'pdf:PDFVersion' in meta:
            meta['pdf:PDFVersion'] = version
