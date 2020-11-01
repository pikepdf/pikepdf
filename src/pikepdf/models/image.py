# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
#
# Copyright (C) 2017, James R. Barlow (https://github.com/jbarlow83/)

import struct
from abc import ABC, abstractmethod
from decimal import Decimal
from io import BytesIO
from itertools import zip_longest
from pathlib import Path
from shutil import copyfileobj
from zlib import decompress
from zlib import error as ZlibError

from PIL import Image, ImageCms
from PIL.TiffTags import TAGS_V2 as TIFF_TAGS

from pikepdf import (
    Array,
    Dictionary,
    Name,
    Object,
    PdfError,
    Stream,
    StreamDecodeLevel,
    String,
    jbig2,
)


class DependencyError(Exception):
    pass


class UnsupportedImageTypeError(Exception):
    pass


class NotExtractableError(Exception):
    pass


def array_str(value):
    """Simplify pikepdf objects to array of str. Keep Streams intact."""

    def _array_str(item):
        if isinstance(item, (list, Array)):
            return [_array_str(subitem) for subitem in item]
        elif isinstance(item, (Stream, bytes, int)):
            return item
        elif isinstance(item, (Name, str)):
            return str(item)
        elif isinstance(item, (String)):
            return bytes(item)
        else:
            raise NotImplementedError(value)

    result = _array_str(value)
    if not isinstance(result, list):
        result = [result]
    return result


def dict_or_array_dict(value):
    if isinstance(value, list):
        return value
    if isinstance(value, Dictionary):
        return [value.as_dict()]
    if isinstance(value, Array):
        return [v.as_list() for v in value]
    raise NotImplementedError(value)


def metadata_from_obj(obj, name, type_, default):
    val = getattr(obj, name, default)
    try:
        return type_(val)
    except TypeError:
        if val is None:
            return None
    raise NotImplementedError('Metadata access for ' + name)


class PdfImageBase(ABC):

    SIMPLE_COLORSPACES = {'/DeviceRGB', '/DeviceGray', '/CalRGB', '/CalGray'}
    MAIN_COLORSPACES = SIMPLE_COLORSPACES | {'/DeviceCMYK', '/CalCMYK', '/ICCBased'}

    @abstractmethod
    def _metadata(self, name, type_, default):
        pass

    @property
    def width(self):
        """Width of the image data in pixels"""
        return self._metadata('Width', int, None)

    @property
    def height(self):
        """Height of the image data in pixels"""
        return self._metadata('Height', int, None)

    @property
    def image_mask(self):
        """``True`` if this is an image mask"""
        return self._metadata('ImageMask', bool, False)

    @property
    def _bpc(self):
        """Bits per component for this image (low-level)"""
        return self._metadata('BitsPerComponent', int, None)

    @property
    def _colorspaces(self):
        """Colorspace (low-level)"""
        return self._metadata('ColorSpace', array_str, [])

    @property
    def filters(self):
        """List of names of the filters that we applied to encode this image"""
        return self._metadata('Filter', array_str, [])

    @property
    def decode_parms(self):
        """List of the /DecodeParms, arguments to filters"""
        return self._metadata('DecodeParms', dict_or_array_dict, [])

    @property
    def colorspace(self):
        """PDF name of the colorspace that best describes this image"""
        if self.image_mask:
            return None  # Undefined for image masks
        if self._colorspaces:
            if self._colorspaces[0] in self.MAIN_COLORSPACES:
                return self._colorspaces[0]
            if self._colorspaces[0] == '/Indexed':
                subspace = self._colorspaces[1]
                if isinstance(subspace, str) and subspace in self.MAIN_COLORSPACES:
                    return subspace
                if isinstance(subspace, list) and subspace[0] == '/ICCBased':
                    return subspace[0]
        raise NotImplementedError(
            "not sure how to get colorspace: " + repr(self._colorspaces)
        )

    @property
    def bits_per_component(self):
        """Bits per component of this image"""
        if self._bpc is None:
            return 1 if self.image_mask else 8
        return self._bpc

    @property
    @abstractmethod
    def is_inline(self):
        pass

    @property
    @abstractmethod
    def icc(self):
        pass

    @property
    def indexed(self):
        """``True`` if the image has a defined color palette"""
        return '/Indexed' in self._colorspaces

    @property
    def size(self):
        """Size of image as (width, height)"""
        return self.width, self.height

    @property
    def mode(self):
        """``PIL.Image.mode`` equivalent for this image, where possible

        If an ICC profile is attached to the image, we still attempt to resolve a Pillow
        mode.
        """

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
            elif self.colorspace == '/DeviceCMYK':
                m = 'CMYK'
            elif self.colorspace == '/ICCBased':
                try:
                    icc_profile = self._colorspaces[1]
                    icc_profile_nchannels = int(icc_profile['/N'])
                    if icc_profile_nchannels == 1:
                        m = 'L'
                    elif icc_profile_nchannels == 3:
                        m = 'RGB'
                    elif icc_profile_nchannels == 4:
                        m = 'CMYK'
                except (ValueError, TypeError):
                    pass
        if m == '':
            raise NotImplementedError("Not sure how to handle PDF image of this type")
        return m

    @property
    def filter_decodeparms(self):
        """PDF has a lot of optional data structures concerning /Filter and
        /DecodeParms. /Filter can be absent or a name or an array, /DecodeParms
        can be absent or a dictionary (if /Filter is a name) or an array (if
        /Filter is an array). When both are arrays the lengths match.

        Normalize this into:
        [(/FilterName, {/DecodeParmName: Value, ...}), ...]

        The order of /Filter matters as indicates the encoding/decoding sequence.
        """
        return list(zip_longest(self.filters, self.decode_parms, fillvalue={}))

    @property
    def palette(self):
        """Retrieves the color palette for this image

        Returns:
            tuple (base_colorspace: str, palette: bytes)
        """

        if not self.indexed:
            return None
        try:
            _idx, base, _hival, lookup = self._colorspaces
        except ValueError as e:
            raise ValueError('Not sure how to interpret this palette') from e
        iccobj = None
        if self.icc:
            iccobj = base[1]
            base = str(base[0])
        else:
            base = str(base)
        lookup = bytes(lookup)
        if not base in self.MAIN_COLORSPACES:
            raise NotImplementedError("not sure how to interpret this palette")
        if base == '/DeviceRGB':
            base = 'RGB'
        elif base == '/DeviceGray':
            base = 'L'
        elif base == '/DeviceCMYK':
            base = 'CMYK'
        elif base == '/ICCBased':
            if iccobj['/N'] == 3:
                base = 'RGB'
            elif iccobj['/N'] == 4:
                base = 'CMYK'
            elif iccobj['/N'] == 1:
                base = 'L'
        return base, lookup

    @abstractmethod
    def as_pil_image(self):
        pass

    @staticmethod
    def _unstack_compression(buffer, filters):
        """Remove stacked compression where it appears.

        Stacked compression means when an image is set to:
            ``[/FlateDecode /DCTDecode]``
        for example.

        Only Flate can be stripped off the front currently.

        Args:
            buffer (pikepdf._qpdf.Buffer): the compressed image data
            filters (list of str): all files on the data
        """
        data = memoryview(buffer)
        while len(filters) > 1 and filters[0] == '/FlateDecode':
            try:
                data = decompress(data)
            except ZlibError as e:
                raise UnsupportedImageTypeError() from e
            filters = filters[1:]
        return data, filters


class PdfImage(PdfImageBase):
    """Support class to provide a consistent API for manipulating PDF images

    The data structure for images inside PDFs is irregular and flexible,
    making it difficult to work with without introducing errors for less
    typical cases. This class addresses these difficulties by providing a
    regular, Pythonic API similar in spirit (and convertible to) the Python
    Pillow imaging library.
    """

    def __new__(cls, obj):
        instance = super().__new__(cls)
        instance.__init__(obj)
        if '/JPXDecode' in instance.filters:
            instance = super().__new__(PdfJpxImage)
            instance.__init__(obj)
        return instance

    def __init__(self, obj):
        """Construct a PDF image from a Image XObject inside a PDF

        ``pim = PdfImage(page.Resources.XObject['/ImageNN'])``

        Args:
            obj (pikepdf.Object): an Image XObject

        """
        if isinstance(obj, Stream) and obj.stream_dict.get("/Subtype") != "/Image":
            raise TypeError("can't construct PdfImage from non-image")
        self.obj = obj
        self._icc = None

    def __eq__(self, other):
        return self.obj == other.obj

    @classmethod
    def _from_pil_image(cls, *, pdf, page, name, image):  # pragma: no cover
        """Insert a PIL image into a PDF (rudimentary)

        Args:
            pdf (pikepdf.Pdf): the PDF to attach the image to
            page (pikepdf.Object): the page to attach the image to
            name (str or pikepdf.Name): the name to set the image
            image (PIL.Image.Image): the image to insert
        """

        data = image.tobytes()

        imstream = Stream(pdf, data)
        imstream.Type = Name('/XObject')
        imstream.Subtype = Name('/Image')
        if image.mode == 'RGB':
            imstream.ColorSpace = Name('/DeviceRGB')
        elif image.mode in ('1', 'L'):
            imstream.ColorSpace = Name('/DeviceGray')
        imstream.BitsPerComponent = 1 if image.mode == '1' else 8
        imstream.Width = image.width
        imstream.Height = image.height

        page.Resources.XObject[name] = imstream

        return cls(imstream)

    def _metadata(self, name, type_, default):
        return metadata_from_obj(self.obj, name, type_, default)

    @property
    def is_inline(self):
        """``False`` for image XObject"""
        return False

    @property
    def _iccstream(self):
        if self.colorspace == '/ICCBased':
            if not self.indexed:
                return self._colorspaces[1]
            assert isinstance(self._colorspaces[1], list)
            return self._colorspaces[1][1]
        raise NotImplementedError("Don't know how to find ICC stream for image")

    @property
    def icc(self):
        """If an ICC profile is attached, return a Pillow object that describe it.

        Most of the information may be found in ``icc.profile``.

        Returns:
            PIL.ImageCms.ImageCmsProfile
        """
        if self.colorspace not in ('/ICCBased', '/Indexed'):
            return None
        if not self._icc:
            iccstream = self._iccstream
            iccbuffer = iccstream.get_stream_buffer()
            iccbytesio = BytesIO(iccbuffer)
            self._icc = ImageCms.ImageCmsProfile(iccbytesio)
        return self._icc

    def _extract_direct(self, *, stream):
        """Attempt to extract the image directly to a usable image file

        If there is no way to extract the image without decompressing or
        transcoding then raise an exception. The type and format of image
        generated will vary.

        Args:
            stream: Writable stream to write data to
        """

        def normal_dct_rgb():
            # Normal DCTDecode RGB images have the default value of
            # /ColorTransform 1 and are actually in YUV. Such a file can be
            # saved as a standard JPEG. RGB JPEGs without YUV conversion can't
            # be saved as JPEGs, and are probably bugs. Some software in the
            # wild actually produces RGB JPEGs in PDFs (probably a bug).
            DEFAULT_CT_RGB = 1
            ct = self.filter_decodeparms[0][1].get('/ColorTransform', DEFAULT_CT_RGB)
            return self.mode == 'RGB' and ct == DEFAULT_CT_RGB

        def normal_dct_cmyk():
            # Normal DCTDecode CMYKs have /ColorTransform 0 and can be saved.
            # There is a YUVK colorspace but CMYK JPEGs don't generally use it
            DEFAULT_CT_CMYK = 0
            ct = self.filter_decodeparms[0][1].get('/ColorTransform', DEFAULT_CT_CMYK)
            return self.mode == 'CMYK' and ct == DEFAULT_CT_CMYK

        data, filters = self._unstack_compression(
            self.obj.get_raw_stream_buffer(), self.filters
        )

        if filters == ['/CCITTFaxDecode']:
            if self.colorspace == '/ICCBased':
                icc = self._iccstream.read_bytes()
            else:
                icc = None
            stream.write(self._generate_ccitt_header(data, icc=icc))
            stream.write(data)
            return '.tif'
        elif filters == ['/DCTDecode'] and (
            self.mode == 'L' or normal_dct_rgb() or normal_dct_cmyk()
        ):
            stream.write(data)
            return '.jpg'

        raise NotExtractableError()

    def _extract_transcoded(self):
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
            im = Image.frombuffer('L', self.size, buffer, "raw", 'L', stride, ystep)
            if self.mode == 'P':
                base_mode, palette = self.palette
                if base_mode in ('RGB', 'L'):
                    im.putpalette(palette, rawmode=base_mode)
                else:
                    raise NotImplementedError('palette with ' + base_mode)
        elif self.bits_per_component == 1:
            if self.filters and self.filters[0] == '/JBIG2Decode':
                if not jbig2.jbig2dec_available():
                    raise DependencyError("jbig2dec - not installed")
                jbig2_globals_obj = self.filter_decodeparms[0][1].get('/JBIG2Globals')
                im = jbig2.extract_jbig2(self.obj, jbig2_globals_obj)
            else:
                data = self.read_bytes()
                im = Image.frombytes('1', self.size, data)
        else:
            raise UnsupportedImageTypeError(repr(self))

        if self.mode == 'P' and self.bits_per_component == 1:
            # Fix paletted 1-bit images
            base_mode, palette = self.palette
            if base_mode == 'RGB' and palette != b'\x00\x00\x00\xff\xff\xff':
                im = im.convert('P')
                im.putpalette(palette, rawmode=base_mode)
                gp = im.getpalette()
                gp[765:768] = gp[3:6]  # work around Pillow bug
                im.putpalette(gp)
            elif base_mode == 'L' and palette != b'\x00\xff':
                im = im.convert('P')
                im.putpalette(palette, rawmode=base_mode)
                gp = im.getpalette()
                gp[255] = gp[1]  # work around Pillow bug
                im.putpalette(gp)

        if self.colorspace == '/ICCBased':
            im.info['icc_profile'] = self.icc.tobytes()

        return im

    def _extract_to_stream(self, *, stream):
        """Attempt to extract the image to a stream

        If possible, the compressed data is extracted and inserted into
        a compressed image file format without transcoding the compressed
        content. If this is not possible, the data will be decompressed
        and extracted to an appropriate format.

        Args:
            stream: Writable stream to write data to

        Returns:
            str: The file format extension
        """

        try:
            return self._extract_direct(stream=stream)
        except NotExtractableError:
            pass

        try:
            im = self._extract_transcoded()
            if im:
                im.save(stream, format='png')
                return '.png'
        except PdfError as e:
            if 'getStreamData called on unfilterable stream' in str(e):
                raise UnsupportedImageTypeError(repr(self)) from e
            raise

        raise UnsupportedImageTypeError(repr(self))

    def extract_to(self, *, stream=None, fileprefix=''):
        """Attempt to extract the image directly to a usable image file

        If possible, the compressed data is extracted and inserted into
        a compressed image file format without transcoding the compressed
        content. If this is not possible, the data will be decompressed
        and extracted to an appropriate format.

        Because it is not known until attempted what image format will be
        extracted, users should not assume what format they are getting back.
        When saving the image to a file, use a temporary filename, and then
        rename the file to its final name based on the returned file extension.

        Examples:

            >>> im.extract_to(stream=bytes_io)
            '.png'

            >>> im.extract_to(fileprefix='/tmp/image00')
            '/tmp/image00.jpg'

        Args:
            stream: Writable stream to write data to.
            fileprefix (str or Path): The path to write the extracted image to,
                without the file extension.

        Returns:
            If *fileprefix* was provided, then the fileprefix with the
            appropriate extension. If no *fileprefix*, then an extension
            indicating the file type.

        Return type:
            str
        """

        if bool(stream) == bool(fileprefix):
            raise ValueError("Cannot set both stream and fileprefix")
        if stream:
            return self._extract_to_stream(stream=stream)

        bio = BytesIO()
        extension = self._extract_to_stream(stream=bio)
        bio.seek(0)
        filepath = Path(str(Path(fileprefix)) + extension)
        with filepath.open('wb') as target:
            copyfileobj(bio, target)
        return str(filepath)

    def read_bytes(self, decode_level=StreamDecodeLevel.specialized):
        """Decompress this image and return it as unencoded bytes"""
        return self.obj.read_bytes(decode_level=decode_level)

    def get_stream_buffer(self, decode_level=StreamDecodeLevel.specialized):
        """Access this image with the buffer protocol"""
        return self.obj.get_stream_buffer(decode_level=decode_level)

    def as_pil_image(self):
        """Extract the image as a Pillow Image, using decompression as necessary

        Returns:
            PIL.Image.Image
        """
        try:
            bio = BytesIO()
            self._extract_direct(stream=bio)
            bio.seek(0)
            return Image.open(bio)
        except NotExtractableError:
            pass

        im = self._extract_transcoded()
        if not im:
            raise UnsupportedImageTypeError(repr(self))

        return im

    def _generate_ccitt_header(self, data, icc=None):
        """Construct a CCITT G3 or G4 header from the PDF metadata"""
        # https://stackoverflow.com/questions/2641770/
        # https://www.itu.int/itudoc/itu-t/com16/tiff-fx/docs/tiff6.pdf

        if not self.decode_parms:
            raise ValueError("/CCITTFaxDecode without /DecodeParms")

        if self.decode_parms[0].get("/EncodedByteAlign", False):
            raise UnsupportedImageTypeError(
                "/CCITTFaxDecode with /EncodedByteAlign true"
            )

        k = self.decode_parms[0].get("/K", 0)
        if k < 0:
            ccitt_group = 4  # Pure two-dimensional encoding (Group 4)
        elif k > 0:
            ccitt_group = 3  # Group 3 2-D
        else:
            ccitt_group = 2  # CCITT 1-D
        black_is_one = self.decode_parms[0].get("/BlackIs1", False)
        # TIFF spec says:
        # use 0 for white_is_zero (=> black is 1)
        # use 1 for black_is_zero (=> white is 1)
        # In practice, do the opposite of what the TIFF spec says.
        photometry = 1 if black_is_one else 0

        img_size = len(data)
        tiff_header_struct = '<' + '2s' + 'H' + 'L' + 'H'

        tag_keys = {tag.name: key for key, tag in TIFF_TAGS.items()}
        ifd_struct = '<HHLL'

        if icc is None:
            icc = b''

        ifds = []

        def header_length(ifd_count):
            return (
                struct.calcsize(tiff_header_struct)
                + struct.calcsize(ifd_struct) * ifd_count
                + 4
            )

        def add_ifd(tag_name, data, count=1):
            key = tag_keys[tag_name]
            typecode = TIFF_TAGS[key].type
            ifds.append((key, typecode, count, data))

        image_offset = None
        add_ifd('ImageWidth', self.width)
        add_ifd('ImageLength', self.height)
        add_ifd('BitsPerSample', 1)
        add_ifd('Compression', ccitt_group)
        add_ifd('PhotometricInterpretation', int(photometry))
        add_ifd('StripOffsets', lambda: image_offset)
        add_ifd('RowsPerStrip', self.height)
        add_ifd('StripByteCounts', img_size)

        icc_offset = 0
        if icc:
            add_ifd('ICCProfile', lambda: icc_offset, count=len(icc))

        icc_offset = header_length(len(ifds))
        image_offset = icc_offset + len(icc)

        ifd_args = [(arg() if callable(arg) else arg) for ifd in ifds for arg in ifd]
        tiff_header = struct.pack(
            (tiff_header_struct + ifd_struct[1:] * len(ifds) + 'L'),
            b'II',  # Byte order indication: Little endian
            42,  # Version number (always 42)
            8,  # Offset to first IFD
            len(ifds),  # Number of tags in IFD
            *ifd_args,
            0,  # Last IFD
        )

        if icc:
            tiff_header += icc

        return tiff_header

    def show(self):
        """Show the image however PIL wants to"""
        self.as_pil_image().show()

    def __repr__(self):
        return '<pikepdf.PdfImage image mode={} size={}x{} at {}>'.format(
            self.mode, self.width, self.height, hex(id(self))
        )

    def _repr_png_(self):
        """Display hook for IPython/Jupyter"""
        b = BytesIO()
        im = self.as_pil_image()
        im.save(b, 'PNG')
        return b.getvalue()


class PdfJpxImage(PdfImage):
    def __init__(self, obj):
        super().__init__(obj)
        self._jpxpil = self.as_pil_image()

    def __eq__(self, other):  # pylint: disable=useless-super-delegation
        # self._jpxpil is not relevant to equality
        return super().__eq__(other)

    def _extract_direct(self, *, stream):
        data, filters = self._unstack_compression(
            self.obj.get_raw_stream_buffer(), self.filters
        )
        if filters != ['/JPXDecode']:
            raise UnsupportedImageTypeError(self.filters)
        stream.write(data)
        return '.jp2'

    @property
    def _colorspaces(self):
        # (PDF 1.7 Table 89) If ColorSpace is present, any colour space
        # specifications in the JPEG2000 data shall be ignored.
        super_colorspaces = super()._colorspaces
        if super_colorspaces:
            return super_colorspaces
        if self._jpxpil.mode == 'L':
            return ['/DeviceGray']
        elif self._jpxpil.mode == 'RGB':
            return ['/DeviceRGB']
        raise NotImplementedError('Complex JP2 colorspace')

    @property
    def _bpc(self):
        # (PDF 1.7 Table 89) If the image stream uses the JPXDecode filter, this
        # entry is optional and shall be ignored if present. The bit depth is
        # determined by the conforming reader in the process of decoding the
        # JPEG2000 image.
        return 8

    @property
    def indexed(self):
        # Nothing in the spec precludes an Indexed JPXDecode image, except for
        # the fact that doing so is madness. Let's assume it no one is that
        # insane.
        return False

    def __repr__(self):
        return '<pikepdf.PdfJpxImage JPEG2000 image mode={} size={}x{} at {}>'.format(
            self.mode, self.width, self.height, hex(id(self))
        )


class PdfInlineImage(PdfImageBase):
    """Support class for PDF inline images"""

    # Inline images can contain abbreviations that we write automatically
    ABBREVS = {
        b'/W': b'/Width',
        b'/H': b'/Height',
        b'/BPC': b'/BitsPerComponent',
        b'/IM': b'/ImageMask',
        b'/CS': b'/ColorSpace',
        b'/F': b'/Filter',
        b'/DP': b'/DecodeParms',
        b'/G': b'/DeviceGray',
        b'/RGB': b'/DeviceRGB',
        b'/CMYK': b'/DeviceCMYK',
        b'/I': b'/Indexed',
        b'/AHx': b'/ASCIIHexDecode',
        b'/A85': b'/ASCII85Decode',
        b'/LZW': b'/LZWDecode',
        b'/RL': b'/RunLengthDecode',
        b'/CCF': b'/CCITTFaxDecode',
        b'/DCT': b'/DCTDecode',
    }

    def __init__(self, *, image_data, image_object: tuple):
        """
        Args:
            image_data: data stream for image, extracted from content stream
            image_object: the metadata for image, also from content stream
        """

        # Convert the sequence of pikepdf.Object from the content stream into
        # a dictionary object by unparsing it (to bytes), eliminating inline
        # image abbreviations, and constructing a bytes string equivalent to
        # what an image XObject would look like. Then retrieve data from there

        self._data = image_data
        self._image_object = image_object

        reparse = b' '.join(self._unparse_obj(obj) for obj in image_object)
        try:
            reparsed_obj = Object.parse(b'<< ' + reparse + b' >>')
        except PdfError as e:
            raise PdfError("parsing inline " + reparse.decode('unicode_escape')) from e
        self.obj = reparsed_obj
        self.pil = None

    def __eq__(self, other):
        if self.obj == other.obj and (
            self._data._inline_image_raw_bytes()
            == other._data._inline_image_raw_bytes()
        ):
            return True
        return False

    @classmethod
    def _unparse_obj(cls, obj):
        if isinstance(obj, Object):
            if isinstance(obj, Name):
                name = obj.unparse(resolved=True)
                assert isinstance(name, bytes)
                return cls.ABBREVS.get(name, name)
            else:
                return obj.unparse(resolved=True)
        elif isinstance(obj, bool):
            return b'true' if obj else b'false'  # Lower case for PDF spec
        elif isinstance(obj, (int, Decimal, float)):
            return str(obj).encode('ascii')
        else:
            raise NotImplementedError(repr(obj))

    def _metadata(self, name, type_, default):
        return metadata_from_obj(self.obj, name, type_, default)

    def unparse(self):
        tokens = []
        tokens.append(b'BI\n')
        metadata = []
        for metadata_obj in self._image_object:
            unparsed = self._unparse_obj(metadata_obj)
            assert isinstance(unparsed, bytes)
            metadata.append(unparsed)
        tokens.append(b' '.join(metadata))
        tokens.append(b'\nID\n')
        tokens.append(self._data._inline_image_raw_bytes())
        tokens.append(b'EI')
        return b''.join(tokens)

    @property
    def is_inline(self):
        return True

    @property
    def icc(self):
        raise NotImplementedError("Inline images with ICC profiles are not supported")

    def __repr__(self):
        mode = '?'
        try:
            mode = self.mode
        except Exception:
            pass
        return '<pikepdf.PdfInlineImage image mode={} size={}x{} at {}>'.format(
            mode, self.width, self.height, hex(id(self))
        )

    def as_pil_image(self):
        if self.pil:
            return self.pil

        raise NotImplementedError('not yet')

    def extract_to(
        self, *, stream=None, fileprefix=''
    ):  # pylint: disable=unused-argument
        raise UnsupportedImageTypeError("inline images don't support extract")

    def read_bytes(self):
        raise NotImplementedError("qpdf returns compressed")
        # return self._data._inline_image_bytes()

    def get_stream_buffer(self):
        raise NotImplementedError("qpdf returns compressed")
        # return memoryview(self._data.inline_image_bytes())
