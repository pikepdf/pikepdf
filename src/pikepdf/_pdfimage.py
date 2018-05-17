# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
#
# Copyright (C) 2017, James R. Barlow (https://github.com/jbarlow83/)

from io import BytesIO
from subprocess import run, PIPE
from tempfile import NamedTemporaryFile
from itertools import zip_longest
import struct

from ._objects import Name
from . import Pdf, Object, ObjectType, Array

class DependencyError(Exception):
    pass

class UnsupportedImageTypeError(Exception):
    pass


class _PdfImageDescriptor:
    def __init__(self, name, type_, default):
        self.name = name
        self.type = type_
        self.default = default

    def __get__(self, wrapper, wrapperclass):
        val = getattr(wrapper.obj, self.name, self.default)
        if self.type == bool:
            return val.as_bool() if isinstance(val, Object) else bool(val)
        return self.type(val)

    def __set__(self, wrapper, val):
        setattr(wrapper.obj, self.name, val)


def array_str(value):
    if value.type_code == ObjectType.array:
        return [str(item) for item in value]
    elif value.type_code == ObjectType.name:
        return [str(value)]
    raise NotImplementedError(value)


def dict_or_array_dict(value):
    if isinstance(value, list):
        return value
    if value.type_code == ObjectType.dictionary:
        return [value.as_dict()]
    elif value.type_code == ObjectType.array:
        return [v.as_dict() for v in value]


class PdfImage:
    SIMPLE_COLORSPACES = ('/DeviceRGB', '/DeviceGray', '/CalRGB', '/CalGray')

    def __init__(self, obj):
        if obj.type_code not in (ObjectType.stream, ObjectType.inlineimage):
            raise TypeError("can't construct PdfImage from non-image")
        if obj.type_code == ObjectType.stream and \
                obj.stream_dict.get("/Subtype") != "/Image":
            raise TypeError("can't construct PdfImage from non-image")

        self.obj = obj

    width = _PdfImageDescriptor('Width', int, None)
    height = _PdfImageDescriptor('Height', int, None)
    image_mask = _PdfImageDescriptor('ImageMask', bool, False)
    _bpc = _PdfImageDescriptor('BitsPerComponent', int, None)
    _colorspaces = _PdfImageDescriptor('ColorSpace', array_str, [])
    filters = _PdfImageDescriptor('Filter', array_str, [])
    decode_parms = _PdfImageDescriptor('DecodeParms', dict_or_array_dict, [])

    @property
    def bits_per_component(self):
        if self._bpc is None:
            return 1 if self.image_mask else 8
        return self._bpc

    @bits_per_component.setter
    def bits_per_component(self, val):
        self._bpc = val

    @property
    def colorspace(self):
        if self._colorspaces[0] in self.SIMPLE_COLORSPACES:
            return self._colorspaces[0]
        if self._colorspaces[0] == '/Indexed' \
                and self._colorspaces[1] in self.SIMPLE_COLORSPACES:
            return self._colorspaces[1]
        if self._colorspaces[0] == '/ICCBased':
            icc = self.obj.ColorSpace[1]
            return icc.stream_dict.get('/Alternate', '')
        raise NotImplementedError("not sure how to get colorspace")

    @property
    def indexed(self):
        return self._colorspaces[0] == '/Indexed'

    @property
    def size(self):
        return self.width, self.height

    @property
    def mode(self):
        m = ''
        if self.bits_per_component == 1:
            m = '1'
        elif self.bits_per_component == 8:
            if self.colorspace == '/DeviceRGB':
                m = 'RGB'
            elif self.colorspace == '/DeviceGray':
                m = 'L'
        if m == '':
            raise NotImplementedError("Not sure how to handle PDF image of this type")
        return m

    @property
    def filter_decodeparms(self):
        """
        PDF has a lot of optional data structures concerning /Filter and
        /DecodeParms. /Filter can be absent or a name or an array, /DecodeParms
        can be absent or a dictionary (if /Filter is a name) or an array (if
        /Filter is an array). When both are arrays the lengths match.

        Normalize this into:
        [(/FilterName, {/DecodeParmName: Value, ...}), ...]

        The order of /Filter matters as indicates the encoding/decoding sequence.

        """
        return list(zip_longest(self.filters, self.decode_parms, fillvalue={}))

    def extract_to(self, *, stream):
        """
        Attempt to extract the image directly to a usable image file

        If there is no way to extract the image without decompressing or
        transcoding then raise an exception. The type and format of image
        generated will vary.

        :param stream: Writable stream to write data to
        """

        if self.filters == ['/CCITTFaxDecode']:
            data = self.obj.read_raw_bytes()
            stream.write(self._generate_ccitt_header(data))
            stream.write(data)
            return '.tif'
        elif self.filters == ['/DCTDecode'] and \
                self.mode == 'RGB' and \
                self.filter_decodeparms[0][1].get('/ColorTransform', 1):
            buffer = self.obj.get_raw_stream_buffer()
            stream.write(buffer)
            return '.jpg'

        raise UnsupportedImageTypeError()


    def as_pil_image(self):
        """
        Extract the image as a Pillow Image, using decompression as necessary

        """
        from PIL import Image

        try:
            bio = BytesIO()
            self.extract_to(stream=bio)
            bio.seek(0)
            return Image.open(bio)
        except UnsupportedImageTypeError:
            pass

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
            raise UnsupportedImageTypeError(repr(self))

        return im

    def _generate_ccitt_header(self, data):
        # https://stackoverflow.com/questions/2641770/
        # https://www.itu.int/itudoc/itu-t/com16/tiff-fx/docs/tiff6.pdf

        if not self.decode_parms:
            raise ValueError("/CCITTFaxDecode without /DecodeParms")

        if self.decode_parms[0].get("/K", 1) < 0:
            ccitt_group = 4  # Pure two-dimensional encoding (Group 4)
        else:
            ccitt_group = 3
        black_is_one = self.decode_parms[0].get("/BlackIs1", False)
        white_is_zero = 1 if black_is_one else 0

        img_size = len(data)
        tiff_header_struct = '<' + '2s' + 'H' + 'L' + 'H' + 'HHLL' * 8 + 'L'
        tiff_header = struct.pack(
            tiff_header_struct,
            b'II',  # Byte order indication: Little endian
            42,  # Version number (always 42)
            8,  # Offset to first IFD
            8,  # Number of tags in IFD
            256, 4, 1, self.width,  # ImageWidth, LONG, 1, width
            257, 4, 1, self.height,  # ImageLength, LONG, 1, length
            258, 3, 1, 1,  # BitsPerSample, SHORT, 1, 1
            259, 3, 1, ccitt_group,  # Compression, SHORT, 1, 4 = CCITT Group 4 fax encoding
            262, 3, 1, int(white_is_zero),  # Thresholding, SHORT, 1, 0 = WhiteIsZero
            273, 4, 1, struct.calcsize(tiff_header_struct),  # StripOffsets, LONG, 1, length of header
            278, 4, 1, self.height,
            279, 4, 1, img_size,  # StripByteCounts, LONG, 1, size of image
            0  # last IFD
        )
        return tiff_header

    def show(self):
        self.as_pil_image().show()

    def __repr__(self):
        return '<pikepdf.PdfImage image mode={} size={}x{} at {}>'.format(
            self.mode, self.width, self.height, hex(id(self)))

    def _repr_png_(self):
        "Display hook for IPython/Jupyter"
        b = BytesIO()
        im = self.as_pil_image()
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
