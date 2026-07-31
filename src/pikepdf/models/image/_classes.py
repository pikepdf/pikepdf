# SPDX-FileCopyrightText: 2022 James R. Barlow
# SPDX-License-Identifier: MPL-2.0

"""The public image facade classes.

:class:`PdfImageBase` defines the metadata interface; :class:`PdfImage` (and its
:class:`PdfJpxImage` JPEG 2000 specialization) and :class:`PdfInlineImage` are
the concrete images. The classes are thin: metadata is exposed as properties
that delegate to :mod:`pikepdf.models.image._colorspace`, and the extraction
pipeline delegates to :mod:`pikepdf.models.image._extract` and
:mod:`pikepdf.models.image._postprocess`. Pillow is imported lazily so that
``import pikepdf`` does not import Pillow.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from decimal import Decimal
from io import BytesIO
from itertools import zip_longest
from pathlib import Path
from shutil import copyfileobj
from typing import TYPE_CHECKING, Any, BinaryIO, cast

from pikepdf._core import Buffer, Pdf, PdfError, StreamDecodeLevel
from pikepdf.models._image_exceptions import (
    InvalidPdfImageError,
    UnsupportedImageTypeError,
)

# _PdfImageMeta is imported from the package __init__, which defines it (with the
# bomb-limit globals the tests poke directly) before importing this module. This
# is the base-before-subclass circular-import pattern and is load-order safe.
from pikepdf.models.image import (
    _colorspace,
    _extract,
    _PdfImageMeta,
    _postprocess,
)
from pikepdf.models.image._bomb import _pillow_pixel_limit, check_pixels
from pikepdf.models.image._shared import (
    DecodeArray,
    PaletteData,
    T,
    _array_str,
    _ensure_list,
    _metadata_from_obj,
)
from pikepdf.objects import (
    Dictionary,
    Name,
    Object,
    Stream,
)

if TYPE_CHECKING:
    from PIL import Image
    from PIL.ImageCms import ImageCmsProfile


class PdfImageBase(ABC, metaclass=_PdfImageMeta):
    """Abstract base class for images."""

    SIMPLE_COLORSPACES = {'/DeviceRGB', '/DeviceGray', '/CalRGB', '/CalGray'}
    MAIN_COLORSPACES = SIMPLE_COLORSPACES | {
        '/DeviceCMYK',
        '/CalCMYK',
        '/ICCBased',
        '/Lab',
    }
    PRINT_COLORSPACES = {'/Separation', '/DeviceN'}

    #: The underlying PDF object: a Stream (image XObject) or a Dictionary
    #: (inline image). Set by each concrete subclass.
    obj: Object

    @abstractmethod
    def _metadata(self, name: str, type_: Callable[[Any], T], default: Any) -> T:
        """Get metadata for this image type.

        *default* is the fallback value passed to ``getattr``; its type is
        independent of the converted result type *T* (which comes from *type_*).
        """

    @property
    def width(self) -> int:
        """Width of the image data in pixels."""
        return self._metadata('Width', int, 0)

    @property
    def height(self) -> int:
        """Height of the image data in pixels."""
        return self._metadata('Height', int, 0)

    @property
    def image_mask(self) -> bool:
        """Return ``True`` if this is an image mask."""
        return self._metadata('ImageMask', bool, False)

    @property
    def _bpc(self) -> int | None:
        """Bits per component for this image (low-level)."""
        return self._metadata('BitsPerComponent', int, 0)

    @property
    def _colorspaces(self) -> list:
        """Colorspace (low-level)."""
        return self._metadata('ColorSpace', _array_str, [])

    @property
    def filters(self) -> list:
        """List of names of the filters that we applied to encode this image."""
        return self._metadata('Filter', _array_str, [])

    @property
    def _decode_array(self) -> DecodeArray:
        """Extract the /Decode array."""
        return _colorspace.decode_array(self)

    @property
    def decode_parms(self) -> list:
        """List of the /DecodeParms, arguments to filters."""
        return self._metadata('DecodeParms', _ensure_list, [])

    def _lab_range(self) -> tuple[float, float, float, float]:
        """Return the /Lab colour space's (amin, amax, bmin, bmax) Range.

        Defaults to (-100, 100, -100, 100) per ISO 32000-2 Table 64 when the
        colour space does not specify a /Range.
        """
        return _colorspace.lab_range(self)

    @property
    def colorspace(self) -> str | None:
        """PDF name of the colorspace that best describes this image."""
        return _colorspace.colorspace(self)

    @property
    def bits_per_component(self) -> int:
        """Bits per component of this image."""
        if self._bpc is None or self._bpc == 0:
            return 1 if self.image_mask else 8
        return self._bpc

    @property
    @abstractmethod
    def icc(self) -> ImageCmsProfile | None:
        """Return ICC profile for this image if one is defined."""

    @property
    def indexed(self) -> bool:
        """Check if the image has a defined color palette."""
        return '/Indexed' in self._colorspaces

    def _colorspace_has_name(self, name: str) -> bool:
        return _colorspace.colorspace_has_name(self, name)

    @property
    def is_device_n(self) -> bool:
        """Check if image has a /DeviceN (complex printing) colorspace."""
        return self._colorspace_has_name('/DeviceN')

    @property
    def is_separation(self) -> bool:
        """Check if image has a /DeviceN (complex printing) colorspace."""
        return self._colorspace_has_name('/Separation')

    @property
    def size(self) -> tuple[int, int]:
        """Size of image as (width, height)."""
        return self.width, self.height

    def _approx_mode_from_icc(self) -> str:
        return _colorspace.approx_mode_from_icc(self)

    @property
    def mode(self) -> str:
        """``PIL.Image.mode`` equivalent for this image, where possible.

        If an ICC profile is attached to the image, we still attempt to resolve a Pillow
        mode.
        """
        return _colorspace.mode(self)

    @property
    def filter_decodeparms(self) -> list:
        """Return normalized the Filter and DecodeParms data.

        PDF has a lot of possible data structures concerning /Filter and
        /DecodeParms. /Filter can be absent or a name or an array, /DecodeParms
        can be absent or a dictionary (if /Filter is a name) or an array (if
        /Filter is an array). When both are arrays the lengths match.

        Normalize this into:
        [(/FilterName, {/DecodeParmName: Value, ...}), ...]

        The order of /Filter matters as indicates the encoding/decoding sequence.
        """
        return list(zip_longest(self.filters, self.decode_parms, fillvalue={}))

    @property
    def palette(self) -> PaletteData | None:
        """Retrieve the color palette for this image if applicable."""
        return _colorspace.palette(self)

    def _check_pixels(self, width: int, height: int) -> None:
        """Guard against decompression-bomb images (issue #733).

        Mirrors :func:`PIL.Image._decompression_bomb_check`, but uses pikepdf's
        :attr:`MAX_IMAGE_PIXELS` and raises pikepdf's exception types.
        """
        check_pixels(self, width, height)

    @abstractmethod
    def as_pil_image(
        self, apply_decode_array: bool = True, apply_mask: bool = True
    ) -> Image.Image:
        """Convert this PDF image to a Python PIL (Pillow) image."""

    def _repr_png_(self) -> bytes:
        """Display hook for IPython/Jupyter."""
        b = BytesIO()
        with self.as_pil_image() as im:
            im.save(b, 'PNG')
            return b.getvalue()


class PdfImage(PdfImageBase):
    """Support class to provide a consistent API for manipulating PDF images.

    The data structure for images inside PDFs is irregular and complex,
    making it difficult to use without introducing errors for less
    typical cases. This class addresses these difficulties by providing a
    regular, Pythonic API similar in spirit (and convertible to) the Python
    Pillow imaging library.
    """

    _icc: ImageCmsProfile | None
    _pdf_source: Pdf | None

    def __new__(cls, obj: Stream) -> PdfImage:
        """Construct a PdfImage... or a PdfJpxImage if that is what we really are."""
        try:
            # Check if JPXDecode is called for and initialize as PdfJpxImage
            filters = _ensure_list(obj.Filter)
            if Name.JPXDecode in filters:
                return super().__new__(PdfJpxImage)
        except (AttributeError, KeyError):
            # __init__ will deal with any other errors
            pass
        return super().__new__(PdfImage)

    def __init__(self, obj: Stream) -> None:
        """Construct a PDF image from a Image XObject inside a PDF.

        ``pim = PdfImage(page.Resources.XObject['/ImageNN'])``

        Args:
            obj: an Image XObject
        """
        if isinstance(obj, Stream) and obj.stream_dict.get("/Subtype") != "/Image":
            raise TypeError("can't construct PdfImage from non-image")
        self.obj = obj
        self._icc = None

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, PdfImageBase):
            return NotImplemented
        return self.obj == other.obj

    @classmethod
    def _from_pil_image(
        cls,
        *,
        pdf: Pdf,
        page: Object,
        name: str | Name,
        image: Image.Image,
    ) -> PdfImage:  # pragma: no cover
        """Insert a PIL image into a PDF (rudimentary).

        Args:
            pdf: the PDF to attach the image to
            page: the page to attach the image to
            name: the name to set the image
            image: the image to insert
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

    def _metadata(self, name: str, type_: Callable[[Any], T], default: Any) -> T:
        return cast(T, _metadata_from_obj(self.obj, name, type_, default))

    @property
    def _iccstream(self) -> Object:
        return _colorspace.iccstream(self)

    @property
    def icc(self) -> ImageCmsProfile | None:
        """If an ICC profile is attached, return a Pillow object that describe it.

        Most of the information may be found in ``icc.profile``.
        """
        return _colorspace.icc(self)

    def _synthesize_cal_icc(self) -> bytes | None:
        """Build an ICC profile from CalRGB/CalGray parameters, if possible.

        The Cal* parameters (WhitePoint, Gamma, Matrix) describe a calibrated
        colour space. pikepdf decodes the samples as the device equivalent and
        attaches this profile so the calibration is preserved for downstream
        consumers. Returns None for non-Cal*, indexed, or malformed (no
        WhitePoint) images.
        """
        return _colorspace.synthesize_cal_icc(self)

    def _remove_simple_filters(self) -> tuple[bytes, list]:
        """Strip generalized/specialized filters, leaving the terminal codec.

        See :func:`pikepdf.models.image._extract.remove_simple_filters`.
        """
        return _extract.remove_simple_filters(self)

    def _extract_direct(
        self, *, stream: BinaryIO, apply_decode_array: bool = True
    ) -> str | None:
        """Attempt to extract the image directly to a usable image file.

        See :func:`pikepdf.models.image._extract.extract_direct`.
        """
        return _extract.extract_direct(
            self, stream=stream, apply_decode_array=apply_decode_array
        )

    def _apply_decode_array(self, im: Image.Image) -> Image.Image:
        """Apply the /Decode array to a decoded image, in pixel space.

        See :func:`pikepdf.models.image._postprocess.apply_decode_array`.
        """
        return _postprocess.apply_decode_array(self, im)

    def _extract_transcoded(self) -> Image.Image:
        """Decode the image to pixels and build a Pillow image.

        See :func:`pikepdf.models.image._extract.extract_transcoded`.
        """
        return _extract.extract_transcoded(self)

    def _has_alpha_mask(self) -> bool:
        """Return True if a /SMask or /Mask would contribute an alpha channel."""
        return isinstance(self.obj.get('/SMask'), Stream) or (
            self.obj.get('/Mask') is not None
        )

    def _extract_to_stream(
        self,
        *,
        stream: BinaryIO,
        apply_decode_array: bool = True,
        apply_mask: bool = True,
    ) -> str:
        """Extract the image to a stream.

        If possible, the compressed data is extracted and inserted into
        a compressed image file format without transcoding the compressed
        content. If this is not possible, the data will be decompressed
        and extracted to an appropriate format.

        Args:
            stream: Writable stream to write data to
            apply_decode_array: Whether the extracted image should reflect the
                image's /Decode array.
            apply_mask: Whether an attached soft/explicit mask should be applied
                as an alpha channel.

        Returns:
            The file format extension.
        """
        # A direct copy of the compressed stream cannot carry an alpha channel,
        # so skip it when a mask must be composited.
        if not (apply_mask and self._has_alpha_mask()):
            direct_extraction = self._extract_direct(
                stream=stream, apply_decode_array=apply_decode_array
            )
            if direct_extraction:
                return direct_extraction

        im = None
        try:
            im = self.as_pil_image(
                apply_decode_array=apply_decode_array, apply_mask=apply_mask
            )
            if im.mode in ('CMYK', 'LAB'):
                im.save(stream, format='tiff', compression='tiff_adobe_deflate')
                return '.tiff'
            if im:
                im.save(stream, format='png')
                return '.png'
        except PdfError as e:
            if 'called on unfilterable stream' in str(e):
                raise UnsupportedImageTypeError(repr(self)) from e
            raise
        finally:
            if im:
                im.close()

        raise UnsupportedImageTypeError(repr(self))

    def extract_to(
        self,
        *,
        stream: BinaryIO | None = None,
        fileprefix: str = '',
        apply_decode_array: bool = True,
        apply_mask: bool = True,
    ) -> str:
        """Extract the image directly to a usable image file.

        If possible, the compressed data is extracted and inserted into
        a compressed image file format without transcoding the compressed
        content. If this is not possible, the data will be decompressed
        and extracted to an appropriate format.

        Because it is not known until attempted what image format will be
        extracted, users should not assume what format they are getting back.
        When saving the image to a file, use a temporary filename, and then
        rename the file to its final name based on the returned file extension.

        Images might be saved as any of .png, .jpg, or .tiff.

        Examples:
            >>> im.extract_to(stream=bytes_io)  # doctest: +SKIP
            '.png'

            >>> im.extract_to(fileprefix='/tmp/image00')  # doctest: +SKIP
            '/tmp/image00.jpg'

        Args:
            stream: Writable stream to write data to.
            fileprefix (str or Path): The path to write the extracted image to,
                without the file extension.
            apply_decode_array: If True (default), the extracted image reflects
                the image's /Decode array, matching how a PDF viewer renders it.
                Note that for a JPEG/JPX image carrying a non-identity /Decode,
                honoring it requires transcoding, so the result is a .png/.tiff
                rather than the original .jpg/.jp2. Set to False to copy the
                stored image data with the least processing (the raw, possibly
                inverted, samples), e.g. for forensic use.
            apply_mask: If True (default), an attached soft/explicit mask is
                composited into an alpha channel, forcing a transparency-capable
                format (.png) instead of a direct .jpg/.jp2 copy. Set to False to
                extract the opaque base image only.

        Returns:
            If *fileprefix* was provided, then the fileprefix with the
            appropriate extension. If no *fileprefix*, then an extension
            indicating the file type.
        """
        if bool(stream) == bool(fileprefix):
            raise ValueError("Cannot set both stream and fileprefix")
        if stream:
            return self._extract_to_stream(
                stream=stream,
                apply_decode_array=apply_decode_array,
                apply_mask=apply_mask,
            )

        bio = BytesIO()
        extension = self._extract_to_stream(
            stream=bio, apply_decode_array=apply_decode_array, apply_mask=apply_mask
        )
        bio.seek(0)
        filepath = Path(str(Path(fileprefix)) + extension)
        with filepath.open('wb') as target:
            copyfileobj(bio, target)
        return str(filepath)

    def read_bytes(
        self, decode_level: StreamDecodeLevel = StreamDecodeLevel.specialized
    ) -> bytes:
        """Decompress this image and return it as unencoded bytes."""
        return self.obj.read_bytes(decode_level=decode_level)

    def get_stream_buffer(
        self, decode_level: StreamDecodeLevel = StreamDecodeLevel.specialized
    ) -> Buffer:
        """Access this image with the buffer protocol."""
        return self.obj.get_stream_buffer(decode_level=decode_level)

    def as_pil_image(
        self, apply_decode_array: bool = True, apply_mask: bool = True
    ) -> Image.Image:
        """Extract the image as a Pillow Image, using decompression as necessary.

        Args:
            apply_decode_array: If True (default), the image's /Decode array is
                applied so the result matches how a PDF viewer would render the
                image. Set to False to obtain the raw sample values as stored,
                e.g. for forensic inspection of the underlying image data.
            apply_mask: If True (default), an attached soft mask (/SMask),
                explicit mask or colour-key mask (/Mask) is composited into an
                alpha channel, so an image with transparency is returned as
                ``LA``/``RGBA``. Set to False to obtain the opaque base image
                only. Images without a mask are unaffected.

        Caller must close the image.
        """
        from PIL import Image

        # Always request a raw (un-decoded) direct extraction; /Decode is applied
        # below in pixel space so that it is applied exactly once.
        bio = BytesIO()
        direct_extraction = self._extract_direct(stream=bio, apply_decode_array=False)
        if direct_extraction:
            bio.seek(0)
            # Let Pillow decode, but make pikepdf's limit (not Pillow's default)
            # govern. Pillow checks the size inside Image.open before decoding
            # any pixels; we suppress its own gate and apply our equivalent check
            # against the real decoded dimensions, raising pikepdf's types.
            with _pillow_pixel_limit(None):
                im = Image.open(bio)
            self._check_pixels(im.width, im.height)
        else:
            # The transcoding path allocates buffers sized from the declared
            # /Width and /Height before reading the stream, so check those
            # dimensions before extracting.
            self._check_pixels(self.width, self.height)
            im = self._extract_transcoded()
            if not im:
                raise UnsupportedImageTypeError(repr(self))

        if apply_decode_array:
            im = self._apply_decode_array(im)

        if apply_mask:
            im = self._apply_mask(im)

        return im

    def _apply_mask(self, im: Image.Image) -> Image.Image:
        """Composite an attached /SMask or /Mask into an alpha channel.

        See :func:`pikepdf.models.image._postprocess.apply_mask`.
        """
        return _postprocess.apply_mask(self, im)

    def _generate_ccitt_header(
        self,
        data: bytes,
        icc: bytes | None = None,
        *,
        apply_decode_array: bool = True,
    ) -> bytes:
        """Construct a CCITT G3 or G4 header from the PDF metadata.

        See :func:`pikepdf.models.image._extract.generate_ccitt_header_from_image`.
        """
        return _extract.generate_ccitt_header_from_image(
            self, data, icc=icc, apply_decode_array=apply_decode_array
        )

    def show(self) -> None:  # pragma: no cover
        """Show the image however PIL wants to."""
        self.as_pil_image().show()

    def _set_pdf_source(self, pdf: Pdf) -> None:
        self._pdf_source = pdf

    def __repr__(self) -> str:
        try:
            mode = self.mode
        except NotImplementedError:
            mode = '?'
        return (
            f'<pikepdf.PdfImage image mode={mode} '
            f'size={self.width}x{self.height} at {hex(id(self))}>'
        )


class PdfJpxImage(PdfImage):
    """Support class for JPEG 2000 images. Implements the same API as :class:`PdfImage`.

    If you call PdfImage(object_that_is_actually_jpeg2000_image), pikepdf will return
    this class instead, due to the check in PdfImage.__new__.
    """

    def __init__(self, obj: Stream) -> None:
        """Initialize a JPEG 2000 image."""
        super().__init__(obj)
        # Intrinsic decoded image for colorspace/equality introspection; the
        # /Decode remap is a presentation concern and intentionally excluded.
        self._jpxpil = self.as_pil_image(apply_decode_array=False, apply_mask=False)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, PdfImageBase):
            return NotImplemented
        return (
            self.obj == other.obj
            and isinstance(other, PdfJpxImage)
            and self._jpxpil == other._jpxpil
        )

    def _extract_direct(
        self, *, stream: BinaryIO, apply_decode_array: bool = True
    ) -> str | None:
        # apply_decode_array is accepted for signature compatibility; /Decode is
        # deferred to the JPEG 2000 codec (see _postprocess.apply_decode_array).
        return _extract.extract_direct_jpx(
            self, stream=stream, apply_decode_array=apply_decode_array
        )

    def _extract_transcoded(self) -> Image.Image:
        return super()._extract_transcoded()

    @property
    def _colorspaces(self) -> list:
        """Return the effective colorspace of a JPEG 2000 image.

        If the ColorSpace dictionary is present, the colorspace embedded in the
        JPEG 2000 data will be ignored, as required by the specification.
        """
        # (PDF 1.7 Table 89) If ColorSpace is present, any colour space
        # specifications in the JPEG2000 data shall be ignored.
        super_colorspaces = super()._colorspaces
        if super_colorspaces:
            return super_colorspaces
        if self._jpxpil.mode == 'L':
            return ['/DeviceGray']
        if self._jpxpil.mode == 'RGB':
            return ['/DeviceRGB']
        raise NotImplementedError('Complex JP2 colorspace')

    @property
    def _bpc(self) -> int:
        """Return 8, since bpc is not meaningful for JPEG 2000 encoding."""
        # (PDF 1.7 Table 89) If the image stream uses the JPXDecode filter, this
        # entry is optional and shall be ignored if present. The bit depth is
        # determined by the conforming reader in the process of decoding the
        # JPEG2000 image.
        return 8

    @property
    def indexed(self) -> bool:
        """Return False, since JPEG 2000 should not be indexed."""
        # Nothing in the spec precludes an Indexed JPXDecode image, except for
        # the fact that doing so is madness. Let's assume it no one is that
        # insane.
        return False

    def __repr__(self) -> str:
        return (
            f'<pikepdf.PdfJpxImage JPEG2000 image mode={self.mode} '
            f'size={self.width}x{self.height} at {hex(id(self))}>'
        )


class PdfInlineImage(PdfImageBase):
    """Support class for PDF inline images."""

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
    REVERSE_ABBREVS = {v: k for k, v in ABBREVS.items()}

    _data: Object
    _image_object: tuple[Object, ...]
    _resources: Object | None

    def __init__(
        self,
        *,
        image_data: Object,
        image_object: tuple,
        resources: Object | None = None,
    ):
        """Construct wrapper for inline image.

        Args:
            image_data: data stream for image, extracted from content stream
            image_object: the metadata for image, also from content stream
            resources: the /Resources dictionary in scope where the inline image
                appears, used to resolve a named colour space referenced by the
                image's /CS. Supplied automatically by
                :func:`pikepdf.parse_content_stream`; ``None`` when unavailable.
        """
        # Convert the sequence of pikepdf.Object from the content stream into
        # a dictionary object by unparsing it (to bytes), eliminating inline
        # image abbreviations, and constructing a bytes string equivalent to
        # what an image XObject would look like. Then retrieve data from there

        self._data = image_data
        self._image_object = image_object
        self._resources = resources

        reparse = b' '.join(
            self._unparse_obj(obj, remap_names=self.ABBREVS) for obj in image_object
        )
        try:
            reparsed_obj = Object.parse(b'<< ' + reparse + b' >>')
        except PdfError as e:
            raise PdfError("parsing inline " + reparse.decode('unicode_escape')) from e
        self.obj = reparsed_obj

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, PdfImageBase):
            return NotImplemented
        return (
            self.obj == other.obj
            and isinstance(other, PdfInlineImage)
            and (
                self._data._inline_image_raw_bytes()
                == other._data._inline_image_raw_bytes()
            )
        )

    @classmethod
    def _unparse_obj(
        cls, obj: Object | bool | int | Decimal | float, remap_names: dict[bytes, bytes]
    ) -> bytes:
        if isinstance(obj, Object):
            if isinstance(obj, Name):
                name = obj.unparse(resolved=True)
                assert isinstance(name, bytes)
                return remap_names.get(name, name)
            return obj.unparse(resolved=True)
        if isinstance(obj, bool):
            return b'true' if obj else b'false'  # Lower case for PDF spec
        if isinstance(obj, int | Decimal | float):
            return str(obj).encode('ascii')
        raise NotImplementedError(repr(obj))

    def _metadata(self, name: str, type_: Callable[[Any], T], default: Any) -> T:
        return cast(T, _metadata_from_obj(self.obj, name, type_, default))

    def _resolve_named_colorspace(self, name: str) -> Object | None:
        """Resolve a named colour space against the in-scope /Resources.

        An inline image may name its colour space (e.g. ``/CS /CS0``); the name
        is a key in the ``/ColorSpace`` subdictionary of the resources in scope
        (ISO 32000-2 §8.9.7). Returns the colour space object, or None when there
        are no resources or the name is not defined there.
        """
        if self._resources is None:
            return None
        try:
            cs_resources = self._resources.get('/ColorSpace')
            if cs_resources is None:
                return None
            return cs_resources.get(name)
        except (AttributeError, TypeError):
            return None

    @property
    def _colorspaces(self) -> list:
        """Colorspace, resolving a named colour space from /Resources if needed.

        Device-space abbreviations (/G, /RGB, /CMYK) and /I are already expanded
        during construction; any other first entry is a name to resolve against
        the in-scope resources, so all downstream logic sees a real colour space.
        """
        cs = super()._colorspaces
        if (
            cs
            and isinstance(cs[0], str)
            and cs[0] not in self.MAIN_COLORSPACES
            and cs[0] not in ('/Indexed', '/DeviceN', '/Separation')
        ):
            resolved = self._resolve_named_colorspace(cs[0])
            if resolved is not None:
                return _array_str(resolved)
        return cs

    def unparse(self) -> bytes:
        """Create the content stream bytes that reproduce this inline image."""

        def metadata_tokens():
            for metadata_obj in self._image_object:
                unparsed = self._unparse_obj(
                    metadata_obj, remap_names=self.REVERSE_ABBREVS
                )
                assert isinstance(unparsed, bytes)
                yield unparsed

        def inline_image_tokens():
            yield b'BI\n'
            yield b' '.join(m for m in metadata_tokens())
            yield b'\nID\n'
            yield self._data._inline_image_raw_bytes()
            yield b'EI'

        return b''.join(inline_image_tokens())

    @property
    def icc(self) -> ImageCmsProfile | None:  # pragma: no cover
        """Raise an exception since ICC profiles are not supported on inline images."""
        raise InvalidPdfImageError(
            "Inline images with ICC profiles are not supported in the PDF specification"
        )

    def __repr__(self) -> str:
        try:
            mode = self.mode
        except NotImplementedError:
            mode = '?'
        return (
            f'<pikepdf.PdfInlineImage image mode={mode} '
            f'size={self.width}x{self.height} at {hex(id(self))}>'
        )

    def _convert_to_pdfimage(self) -> PdfImage:
        # Construct a temporary PDF that holds this inline image, and...
        tmppdf = Pdf.new()
        tmppdf.add_blank_page(page_size=(self.width, self.height))
        tmppdf.pages[0].contents_add(
            f'{self.width} 0 0 {self.height} 0 0 cm'.encode('ascii'), prepend=True
        )
        tmppdf.pages[0].contents_add(self.unparse())

        # If the inline image names a colour space defined in the in-scope
        # /Resources, copy that definition into the temporary page's resources so
        # externalization (which emits /ColorSpace <name>) can resolve it.
        self._copy_named_colorspace_into(tmppdf)

        # ...externalize it,
        tmppdf.pages[0].externalize_inline_images()
        raw_img = cast(
            Stream,
            next(im for im in tmppdf.pages[0].get_images(recursive=False).values()),
        )

        # ...then use the regular PdfImage API to extract it.
        img = PdfImage(raw_img)
        img._set_pdf_source(tmppdf)  # Hold tmppdf open while PdfImage exists
        return img

    def _copy_named_colorspace_into(self, tmppdf: Pdf) -> None:
        """Copy a named colour space definition into *tmppdf*'s page resources."""
        cs = super()._colorspaces
        if not (cs and isinstance(cs[0], str)):
            return
        name = cs[0]
        if name in self.MAIN_COLORSPACES or name in (
            '/Indexed',
            '/DeviceN',
            '/Separation',
        ):
            return
        resolved = self._resolve_named_colorspace(name)
        if resolved is None:
            return
        if resolved.is_indirect:
            resolved = tmppdf.copy_foreign(resolved)
        page = tmppdf.pages[0]
        if '/Resources' not in page:
            page.Resources = Dictionary()
        if '/ColorSpace' not in page.Resources:
            page.Resources.ColorSpace = Dictionary()
        page.Resources.ColorSpace[name] = resolved

    def as_pil_image(
        self, apply_decode_array: bool = True, apply_mask: bool = True
    ) -> Image.Image:
        """Return inline image as a Pillow Image."""
        return self._convert_to_pdfimage().as_pil_image(
            apply_decode_array=apply_decode_array, apply_mask=apply_mask
        )

    def extract_to(
        self,
        *,
        stream: BinaryIO | None = None,
        fileprefix: str = '',
        apply_decode_array: bool = True,
        apply_mask: bool = True,
    ) -> str:
        """Extract the inline image directly to a usable image file.

        See:
            :meth:`PdfImage.extract_to`
        """
        return self._convert_to_pdfimage().extract_to(
            stream=stream,
            fileprefix=fileprefix,
            apply_decode_array=apply_decode_array,
            apply_mask=apply_mask,
        )

    def read_bytes(self) -> bytes:
        """Return decompressed image bytes."""
        # qpdf does not have an API to return this directly, so convert it.
        return self._convert_to_pdfimage().read_bytes()

    def get_stream_buffer(self) -> Buffer:
        """Return decompressed stream buffer."""
        # qpdf does not have an API to return this directly, so convert it.
        return self._convert_to_pdfimage().get_stream_buffer()
