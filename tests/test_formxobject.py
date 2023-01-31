# SPDX-FileCopyrightText: 2022 James R. Barlow
# SPDX-License-Identifier: CC0-1.0

from __future__ import annotations

from pikepdf import Dictionary, Name, Object, Pdf, Stream

# pylint: disable=e1137


def test_create_form_xobjects(outdir):
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
            >>
        """
        )
    )

    width, height = 100, 100
    image_data = b"\xff\x7f\x00" * (width * height)

    image = Stream(pdf, image_data)
    image.stream_dict = Object.parse(
        """
            <<
                /Type /XObject
                /Subtype /Image
                /ColorSpace /DeviceRGB
                /BitsPerComponent 8
                /Width 100
                /Height 100
            >>
    """
    )
    xobj_image = Dictionary({'/Im1': image})

    form_xobj_res = Dictionary({'/XObject': xobj_image})
    form_xobj = Stream(
        pdf,
        b"""
        /Im1 Do
    """,
    )
    form_xobj['/Type'] = Name('/XObject')
    form_xobj['/Subtype'] = Name('/Form')
    form_xobj['/FormType'] = 1
    form_xobj['/Matrix'] = [1, 0, 0, 1, 0, 0]
    form_xobj['/BBox'] = [0, 0, 1, 1]
    form_xobj['/Resources'] = form_xobj_res

    rfont = {'/F1': font}

    resources = {'/Font': rfont, '/XObject': {'/Form1': form_xobj}}

    mediabox = [0, 0, 612, 792]

    stream = b"""
        BT /F1 24 Tf 72 720 Td (Hi there) Tj ET
        q 144 0 0 144 234 324 cm /Form1 Do Q
        q 72 0 0 72 378 180 cm /Form1 Do Q
        """

    contents = Stream(pdf, stream)

    page = pdf.make_indirect(
        {
            '/Type': Name('/Page'),
            '/MediaBox': mediabox,
            '/Contents': contents,
            '/Resources': resources,
        }
    )

    pdf.pages.append(page)
    pdf.save(outdir / 'formxobj.pdf')
