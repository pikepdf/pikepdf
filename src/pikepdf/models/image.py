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

from decimal import Decimal

from .. import (
    Pdf, Object, Array, PdfError, Name, Dictionary, Stream
)

class DependencyError(Exception):
    pass

class UnsupportedImageTypeError(Exception):
    pass


class _PdfImageDescriptor:
    def __init__(self, name, type_, default, inline_name=None, inline_map=None):
        self.name = name
        self.type = type_
        self.default = default
        self.inline_name = inline_name
        self.inline_map = inline_map

    def __get__(self, wrapper, wrapperclass):
        sentinel = object()
        val = sentinel
        if self.inline_name:
            val = getattr(wrapper.obj, self.inline_name, sentinel)
        if val is sentinel:
            val = getattr(wrapper.obj, self.name, self.default)
        if self.type == bool:
            return val.as_bool() if isinstance(val, Object) else bool(val)

        try:
            return self.type(val)
        except TypeError:
            if val is None:
                return None
        raise NotImplementedError("__get__")


    def __set__(self, wrapper, val):
        if self.inline_name:
            raise NotImplementedError("editing inline images")
        setattr(wrapper.obj, self.name, val)


def array_str(value):
    if isinstance(value, list):
        return [str(item) for item in value]
    elif isinstance(value, Array):
        return [str(item) for item in value]
    elif isinstance(value, Name):
        return [str(value)]
    raise NotImplementedError(value)


def dict_or_array_dict(value):
    if isinstance(value, list):
        return value
    elif isinstance(value, Dictionary):
        return [value.as_dict()]
    elif isinstance(value, Array):
        return [v.as_dict() for v in value]
    raise NotImplementedError(value)


class PdfImage:
    """
    Support class to provide a consistent API for manipulating PDF images

    The data structure for images inside PDFs is irregular and flexible,
    making it difficult to work with without introducing errors for less
    typical cases. This class addresses these difficulties by providing a
    regular, Pythonic API similar in spirit (and convertible to) the Python
    Pillow imaging library.
    """
    SIMPLE_COLORSPACES = ('/DeviceRGB', '/DeviceGray', '/CalRGB', '/CalGray')

    def __init__(self, obj):
        """
        Construct a PDF image from a Image XObject inside a PDF

        ``pim = PdfImage(page.Resources.XObject['/ImageNN'])``

        :param obj: an Image XObject
        :type obj: pikepdf.Object

        """
        if isinstance(obj, Stream) and \
                obj.stream_dict.get("/Subtype") != "/Image":
            raise TypeError("can't construct PdfImage from non-image")
        self.obj = obj

    width = _PdfImageDescriptor('Width', int, None)
    """Width of the image data in pixels"""

    height = _PdfImageDescriptor('Height', int, None)
    """Height of the image data in pixels"""

    image_mask = _PdfImageDescriptor('ImageMask', bool, False)
    """``True`` if this is an image mask"""

    _bpc = _PdfImageDescriptor('BitsPerComponent', int, None)
    _colorspaces = _PdfImageDescriptor('ColorSpace', array_str, [])

    filters = _PdfImageDescriptor('Filter', array_str, [])
    """List of names of the filters that we applied to encode this image"""

    decode_parms = _PdfImageDescriptor('DecodeParms', dict_or_array_dict, [])
    """List of the /DecodeParms, arguments to filters"""

    @property
    def bits_per_component(self):
        """Bits per component of this image"""
        if self._bpc is None:
            return 1 if self.image_mask else 8
        return self._bpc

    @bits_per_component.setter
    def bits_per_component(self, val):
        self._bpc = val

    @property
    def colorspace(self):
        """PDF name of the colorspace that best describes this image"""
        if self.image_mask:
            return None  # Undefined for image masks
        if self._colorspaces[0] in self.SIMPLE_COLORSPACES:
            return self._colorspaces[0]
        if self._colorspaces[0] == '/DeviceCMYK':
            return self._colorspaces[0]
        if self._colorspaces[0] == '/Indexed' \
                and self._colorspaces[1] in self.SIMPLE_COLORSPACES:
            return self._colorspaces[1]
        if self._colorspaces[0] == '/ICCBased':
            icc = self.obj.ColorSpace[1]
            return icc.stream_dict.get('/Alternate', '')
        raise NotImplementedError(
            "not sure how to get colorspace: " + repr(self._colorspaces))

    @property
    def is_inline(self):
        """``False`` for image XObject"""
        return False

    @property
    def indexed(self):
        """``True`` if the image has a defined color palette"""
        return self._colorspaces[0] == '/Indexed'

    @property
    def palette(self):
        """
        Retrieves the color palette for this image

        :returns: (base_colorspace: str, palette: bytes)
        :rtype: tuple
        """

        if not self.indexed:
            return None
        _idx, base, hival, lookup = None, None, None, None
        try:
            _idx, base, hival, lookup = self.obj.ColorSpace.as_list()
        except ValueError as e:
            raise ValueError('Not sure how to interpret this palette') from e
        base = str(base)
        hival = int(hival)
        lookup = bytes(lookup)
        if not base in self.SIMPLE_COLORSPACES:
            raise NotImplementedError("not sure how to interpret this palette")
        if base == '/DeviceRGB':
            base = 'RGB'
        elif base == '/DeviceGray':
            base = 'L'
        return base, lookup

    @property
    def size(self):
        """Size of image as (width, height)"""
        return self.width, self.height

    @property
    def mode(self):
        """``PIL.Image.mode`` equivalent for this image"""
        m = ''
        if self.indexed:
            m = 'P'
        elif self.bits_per_component == 1:
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

    def _extract_direct(self, *, stream):
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

    def _extract_transcoded(self):
        from PIL import Image
        im = None
        if self.mode == 'RGB' and self.bits_per_component == 8:
            # No point in accessing the buffer here, size qpdf decodes to 3-byte
            # RGB and Pillow needs RGBX for raw access
            data = self.read_bytes()
            im = Image.frombytes('RGB', self.size, data)
        elif self.mode in ('L', 'P') and self.bits_per_component == 8:
            buffer = self.get_stream_buffer()
            stride = 0  # tell Pillow to calculate stride from line width
            ystep = 1  # image is top to bottom in memory
            im = Image.frombuffer('L', self.size, buffer, "raw", 'L', stride,
                                  ystep)
            if self.mode == 'P':
                base_mode, palette_data = self.palette
                if base_mode in ('RGB', 'L'):
                    im.putpalette(palette_data, rawmode=base_mode)
                else:
                    raise NotImplementedError('palette with ' + base_mode)
        elif self.mode in ('1', 'P') and self.bits_per_component == 1:
            try:
                data = self.read_bytes()
            except PdfError:
                return None
            # 1bpp gets extracted as 8bpp by read_bytes()
            im = Image.frombytes('1', self.size, data)
            if self.mode == 'P':
                base_mode, palette_data = self.palette
                if (palette_data == b'\x00\x00\x00\xff\xff\xff'
                        or palette_data == b'\x00\xff'):
                    pass  # Some PDFs embed a trivial palette
                elif base_mode in ('RGB', 'L'):
                    im.putpalette(palette_data, rawmode=base_mode)
                else:
                    raise NotImplementedError('palette with ' + base_mode)

        return im

    def extract_to(self, *, stream):
        """
        Attempt to extract the image directly to a usable image file

        If possible, the compressed data is extracted and inserted into
        a compressed image file format without transcoding the compressed
        content. If this is not possible, the data will be decompressed
        and extracted to an appropriate format.

        :param stream: Writable stream to write data to
        :returns: str -- The file format extension
        """

        try:
            return self._extract_direct(stream=stream)
        except UnsupportedImageTypeError:
            pass

        im = self._extract_transcoded()
        if im:
            im.save(stream, format='png')
            return '.png'

        raise UnsupportedImageTypeError(repr(self))


    def read_bytes(self):
        """Decompress this image and return it as unencoded bytes"""
        return self.obj.read_bytes()

    def get_stream_buffer(self):
        """Access this image with the buffer protocol"""
        return self.obj.get_stream_buffer()

    def as_pil_image(self):
        """
        Extract the image as a Pillow Image, using decompression as necessary

        :rtype: :class:`PIL.Image.Image`
        """
        from PIL import Image

        try:
            bio = BytesIO()
            self._extract_direct(stream=bio)
            bio.seek(0)
            return Image.open(bio)
        except UnsupportedImageTypeError:
            pass

        im = self._extract_transcoded()
        if not im:
            raise UnsupportedImageTypeError(repr(self))

        return im

    def _generate_ccitt_header(self, data):
        """
        Construct a CCITT G3 or G4 header from the PDF metadata
        """
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
        """Show the image however PIL wants to"""
        self.as_pil_image().show()

    def __repr__(self):
        return '<pikepdf.PdfImage image mode={} size={}x{} at {}>'.format(
            self.mode, self.width, self.height, hex(id(self)))

    def _repr_png_(self):
        """Display hook for IPython/Jupyter"""
        b = BytesIO()
        im = self.as_pil_image()
        im.save(b, 'PNG')
        return b.getvalue()


def inline_remove_abbrevs(value):
    abbrevs = {
        '/G': '/DeviceGray',
        '/RGB': '/DeviceRGB',
        '/CMYK': '/DeviceCMYK',
        '/I': '/Indexed',
        '/AHx': '/ASCIIHexDecode',
        '/A85': '/ASCII85Decode',
        '/LZW': '/LZWDecode',
        '/RL': '/RunLengthDecode',
        '/CCF': '/CCITTFaxDecode',
        '/DCT': '/DCTDecode'
    }
    return [abbrevs.get(value, value) for value in array_str(value)]


class PdfInlineImage(PdfImage):
    """Support class for PDF inline images"""

    def __init__(self, *, image_data, image_object: tuple):
        """
        :param image_data: data stream for image, extracted from content stream
        :param image_object: the metadata for image, also from content stream
        """

        self._data = image_data
        self._image_object = image_object

        def unparse(obj):
            if isinstance(obj, Object):
                return obj.unparse_resolved()
            elif isinstance(obj, (int, bool, Decimal, float)):
                return str(obj).encode('ascii')
            else:
                raise NotImplementedError(repr(obj))
        reparse = b' '.join(unparse(obj) for obj in image_object)
        super().__init__(Object.parse(b'<< ' + reparse + b' >>'))

    width = _PdfImageDescriptor('Width', int, None, 'W')
    height = _PdfImageDescriptor('Height', int, None, 'H')
    image_mask = _PdfImageDescriptor('ImageMask', bool, False, 'IM')
    _bpc = _PdfImageDescriptor('BitsPerComponent', int, None, 'BPC')
    _colorspaces = _PdfImageDescriptor('ColorSpace', inline_remove_abbrevs, [], 'CS')
    filters = _PdfImageDescriptor('Filter', inline_remove_abbrevs, [], 'F')
    decode_parms = _PdfImageDescriptor('DecodeParms', dict_or_array_dict, [], 'DP')

    @property
    def is_inline(self):
        return True

    def __repr__(self):
        return '<pikepdf.PdfInlineImage image mode={} size={}x{} at {}>'.format(
            self.mode, self.width, self.height, hex(id(self)))

    def extract_to(self, *, stream):  # pylint: disable=unused-argument
        raise UnsupportedImageTypeError("inline images don't support extract")

    def read_bytes(self):
        raise NotImplementedError("qpdf returns compressed")
        #return self._data._inline_image_bytes()

    def get_stream_buffer(self):
        raise NotImplementedError("qpdf returns compressed")
        #return memoryview(self._data.inline_image_bytes())


def page_to_svg(page):
    pdf = Pdf.new()
    pdf.pages.append(page)
    with NamedTemporaryFile(suffix='.pdf') as tmp_in, \
            NamedTemporaryFile(mode='w+b', suffix='.svg') as tmp_out:
        pdf.save(tmp_in)
        tmp_in.seek(0)

        try:
            proc = run(['mudraw', '-F', 'svg', '-o', tmp_out.name, tmp_in.name], stderr=PIPE)
        except FileNotFoundError:
            raise DependencyError("Could not find the required executable 'mutool'")

        if proc.stderr:
            print(proc.stderr.decode())
        tmp_out.flush()
        tmp_out2 = open(tmp_out.name, 'rb')  # Not sure why re-opening is need, but it is
        svg = tmp_out2.read()
        return svg.decode()
