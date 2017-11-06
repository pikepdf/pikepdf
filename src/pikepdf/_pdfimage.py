# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
#
# Copyright (C) 2017, James R. Barlow (https://github.com/jbarlow83/)

from io import BytesIO
from subprocess import run, PIPE
from ._qpdf import Pdf, Object, ObjectType, Array, Name
from tempfile import NamedTemporaryFile


class DependencyError(Exception):
    pass


class PdfImage:
    def __init__(self, obj):
        if obj.type_code not in (ObjectType.stream, ObjectType.inlineimage):
            raise TypeError("can't construct PdfImage from non-image")

        if obj.type_code == ObjectType.stream and \
                obj.stream_dict.get("/Subtype") != "/Image":
            raise TypeError("can't construct PdfImage from non-image")
        
        self.obj = obj

    @property
    def mode(self):
        m = ''
        if self.obj.BitsPerComponent == 1:
            m = '1'
        elif self.obj.BitsPerComponent == 8:
            if self.obj.ColorSpace == '/DeviceRGB':
                m = 'RGB'
            elif self.obj.ColorSpace == '/DeviceGray':
                m = 'L'
        if m == '':
            raise NotImplementedError("Not sure how to handle PDF image of this type")
        return m

    @property
    def size(self):
        return self.width, self.height

    @property
    def width(self):
        return int(self.obj.Width)

    @property
    def height(self):
        return int(self.obj.Height)

    def topil(self):
        from PIL import Image

        im = None
        if self.obj.Filter == '/DCTDecode' or \
                self.obj.Filter == Array([Name('/DCTDecode')]):
            buffer = self.obj.get_raw_stream_buffer()
            # BytesIO will make a copy of buffer
            im = Image.open(BytesIO(buffer))  
            return im
                
        if self.mode == 'RGB':
            # No point in accessing the buffer here, size qpdf decodes to 3-byte
            # RGB and Pillow needs RGBX for raw access
            data = self.obj.read_bytes()
            im = Image.frombytes('RGB', self.size, data)
        elif self.mode == 'L':
            buffer = self.obj.get_stream_buffer()
            stride = 0  # tell Pillow to calculate stride from line width
            ystep = 1  # image is top to bottom in memory
            im = Image.frombuffer('L', self.size, buffer, "raw", stride, ystep)
        
        if not im:
            raise TypeError("don't how to convert to this image type")

        return im
    
    def show(self):
        self.topil().show()

    def __repr__(self):
        return '<pikepdf.PdfImage image mode={} size={}x{} at {}>'.format(
            self.mode, self.width, self.height, hex(id(self)))

    def _repr_png_(self):
        "Display hook for IPython/Jupyter"
        b = BytesIO()
        im = self.topil()
        im.save(b, 'PNG')
        return b.getvalue()


def page_to_svg(page):
    pdf = Pdf.new()
    pdf.pages.append(page)
    with NamedTemporaryFile(suffix='.pdf') as tmp_in, \
            NamedTemporaryFile(mode='w+b', suffix='.svg') as tmp_out:
        pdf.save(tmp_in)
        tmp_in.seek(0)

        try:
            proc = run(['mudraw', '-F', 'svg', '-o', tmp_out.name, tmp_in.name], stderr=PIPE)
        except FileNotFoundError as e:
            raise DependencyError("Could not find the required executable 'mutool'")

        if proc.stderr:
            print(proc.stderr.decode())            
        tmp_out.flush()
        tmp_out2 = open(tmp_out.name, 'rb')  # Not sure why re-opening is need, but it is
        svg = tmp_out2.read()
        return svg.decode()