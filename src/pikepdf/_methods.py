# SPDX-FileCopyrightText: 2022 James R. Barlow
# SPDX-License-Identifier: MPL-2.0

"""Implement some features in Python and monkey-patch them onto C++ classes.

In several cases the implementation of some higher levels features might as
well be in Python. Fortunately we can attach Python methods to C++ class
bindings after the fact.

We can also move the implementation to C++ if desired.
"""

from __future__ import annotations

import datetime
import mimetypes
import shutil
from collections.abc import KeysView, MutableMapping
from contextlib import ExitStack
from decimal import Decimal
from io import BytesIO, RawIOBase
from pathlib import Path
from subprocess import run
from tempfile import NamedTemporaryFile
from typing import BinaryIO, Callable, ItemsView, Iterator, TypeVar, ValuesView
from warnings import warn

from pikepdf._augments import augment_override_cpp, augments
from pikepdf._core import (
    AccessMode,
    AttachedFile,
    AttachedFileSpec,
    Attachments,
    NameTree,
    NumberTree,
    ObjectStreamMode,
    Page,
    Pdf,
    Rectangle,
    StreamDecodeLevel,
    StreamParser,
    Token,
    _ObjectMapping,
)
from pikepdf._io import atomic_overwrite, check_different_files, check_stream_is_usable
from pikepdf.models import Encryption, EncryptionInfo, Outline, Permissions
from pikepdf.models.metadata import PdfMetadata, decode_pdf_date, encode_pdf_date
from pikepdf.objects import Array, Dictionary, Name, Object, Stream

# pylint: disable=no-member,unsupported-membership-test,unsubscriptable-object
# mypy: ignore-errors

__all__ = []

Numeric = TypeVar('Numeric', int, float, Decimal)


def _single_page_pdf(page) -> bytes:
    """Construct a single page PDF from the provided page in memory."""
    pdf = Pdf.new()
    pdf.pages.append(page)
    bio = BytesIO()
    pdf.save(bio)
    bio.seek(0)
    return bio.read()


def _mudraw(buffer, fmt) -> bytes:
    """Use mupdf draw to rasterize the PDF in the memory buffer."""
    # mudraw cannot read from stdin so NamedTemporaryFile is required
    with NamedTemporaryFile(suffix='.pdf') as tmp_in:
        tmp_in.write(buffer)
        tmp_in.seek(0)
        tmp_in.flush()

        proc = run(
            ['mudraw', '-F', fmt, '-o', '-', tmp_in.name],
            capture_output=True,
            check=True,
        )
        return proc.stdout


@augments(Object)
class Extend_Object:
    def _ipython_key_completions_(self):
        if isinstance(self, (Dictionary, Stream)):
            return self.keys()
        return None

    def emplace(self, other: Object, retain=(Name.Parent,)):
        if not self.same_owner_as(other):
            raise TypeError("Objects must have the same owner for emplace()")

        # .keys() returns strings, so make all strings
        retain = {str(k) for k in retain}
        self_keys = set(self.keys())
        other_keys = set(other.keys())

        assert all(isinstance(k, str) for k in (retain | self_keys | other_keys))

        del_keys = self_keys - other_keys - retain
        for k in (k for k in other_keys if k not in retain):
            self[k] = other[k]  # pylint: disable=unsupported-assignment-operation
        for k in del_keys:
            del self[k]  # pylint: disable=unsupported-delete-operation

    def _type_check_write(self, filter_, decode_parms):
        if isinstance(filter_, list):
            filter_ = Array(filter_)
        filter_ = filter_.wrap_in_array()

        if isinstance(decode_parms, list):
            decode_parms = Array(decode_parms)
        elif decode_parms is None:
            decode_parms = Array([])
        else:
            decode_parms = decode_parms.wrap_in_array()

        if not all(isinstance(item, Name) for item in filter_):
            raise TypeError(
                "filter must be: pikepdf.Name or pikepdf.Array([pikepdf.Name])"
            )
        if not all(
            (isinstance(item, Dictionary) or item is None) for item in decode_parms
        ):
            raise TypeError(
                "decode_parms must be: pikepdf.Dictionary or "
                "pikepdf.Array([pikepdf.Dictionary])"
            )
        if len(decode_parms) != 0 and len(filter_) != len(decode_parms):
            raise ValueError(
                f"filter ({repr(filter_)}) and decode_parms "
                f"({repr(decode_parms)}) must be arrays of same length"
            )
        if len(filter_) == 1:
            filter_ = filter_[0]
        if len(decode_parms) == 0:
            decode_parms = None
        elif len(decode_parms) == 1:
            decode_parms = decode_parms[0]
        return filter_, decode_parms

    def write(
        self,
        data: bytes,
        *,
        filter: Name | Array | None = None,
        decode_parms: Dictionary | Array | None = None,
        type_check: bool = True,
    ):  # pylint: disable=redefined-builtin
        if type_check and filter is not None:
            filter, decode_parms = self._type_check_write(filter, decode_parms)

        self._write(data, filter=filter, decode_parms=decode_parms)


@augments(Pdf)
class Extend_Pdf:
    def _repr_mimebundle_(
        self, include=None, exclude=None
    ):  # pylint: disable=unused-argument
        bio = BytesIO()
        self.save(bio)
        bio.seek(0)

        data = {'application/pdf': bio.read()}
        return data

    @property
    def docinfo(self) -> Dictionary:
        if Name.Info not in self.trailer:
            self.trailer.Info = self.make_indirect(Dictionary())
        return self.trailer.Info

    @docinfo.setter
    def docinfo(self, new_docinfo: Dictionary):
        if not new_docinfo.is_indirect:
            raise ValueError(
                "docinfo must be an indirect object - use Pdf.make_indirect"
            )
        self.trailer.Info = new_docinfo

    @docinfo.deleter
    def docinfo(self):
        if Name.Info in self.trailer:
            del self.trailer.Info

    def open_metadata(
        self,
        set_pikepdf_as_editor: bool = True,
        update_docinfo: bool = True,
        strict: bool = False,
    ) -> PdfMetadata:
        return PdfMetadata(
            self,
            pikepdf_mark=set_pikepdf_as_editor,
            sync_docinfo=update_docinfo,
            overwrite_invalid_xml=not strict,
        )

    def open_outline(self, max_depth: int = 15, strict: bool = False) -> Outline:
        return Outline(self, max_depth=max_depth, strict=strict)

    def make_stream(self, data: bytes, d=None, **kwargs) -> Stream:
        return Stream(self, data, d, **kwargs)

    def add_blank_page(
        self, *, page_size: tuple[Numeric, Numeric] = (612.0, 792.0)
    ) -> Page:
        for dim in page_size:
            if not (3 <= dim <= 14400):
                raise ValueError('Page size must be between 3 and 14400 PDF units')

        page_dict = Dictionary(
            Type=Name.Page,
            MediaBox=Array([0, 0, page_size[0], page_size[1]]),
            Contents=self.make_stream(b''),
            Resources=Dictionary(),
        )
        page_obj = self.make_indirect(page_dict)
        self._add_page(page_obj, first=False)
        return Page(page_obj)

    def close(self) -> None:
        self._close()
        if getattr(self, '_tmp_stream', None):
            self._tmp_stream.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()

    @property
    def allow(self) -> Permissions:
        results = {}
        for field in Permissions._fields:
            results[field] = getattr(self, '_allow_' + field)
        return Permissions(**results)

    @property
    def encryption(self) -> EncryptionInfo:
        return EncryptionInfo(self._encryption_data)

    def check(self) -> list[str]:
        class DiscardingParser(StreamParser):
            def __init__(self):  # pylint: disable=useless-super-delegation
                super().__init__()  # required for C++

            def handle_object(self, *_args):
                pass

            def handle_eof(self):
                pass

        problems: list[str] = []

        self._decode_all_streams_and_discard()

        discarding_parser = DiscardingParser()
        for page in self.pages:
            page.parse_contents(discarding_parser)

        for warning in self.get_warnings():
            problems.append("WARNING: " + warning)

        return problems

    def save(
        self,
        filename_or_stream: Path | str | BinaryIO | None = None,
        *,
        static_id: bool = False,
        preserve_pdfa: bool = True,
        min_version: str | tuple[str, int] = "",
        force_version: str | tuple[str, int] = "",
        fix_metadata_version: bool = True,
        compress_streams: bool = True,
        stream_decode_level: StreamDecodeLevel | None = None,
        object_stream_mode: ObjectStreamMode = ObjectStreamMode.preserve,
        normalize_content: bool = False,
        linearize: bool = False,
        qdf: bool = False,
        progress: Callable[[int], None] = None,
        encryption: Encryption | bool | None = None,
        recompress_flate: bool = False,
        deterministic_id: bool = False,
    ) -> None:
        if not filename_or_stream and getattr(self, '_original_filename', None):
            filename_or_stream = self._original_filename
        if not filename_or_stream:
            raise ValueError(
                "Cannot save to original filename because the original file was "
                "not opening using Pdf.open(..., allow_overwriting_input=True). "
                "Either specify a new destination filename/file stream or open "
                "with allow_overwriting_input=True. If this Pdf was created using "
                "Pdf.new(), you must specify a destination object since there is "
                "no original filename to save to."
            )
        with ExitStack() as stack:
            if hasattr(filename_or_stream, 'seek'):
                stream = filename_or_stream
                check_stream_is_usable(filename_or_stream)
            else:
                if not isinstance(filename_or_stream, (str, bytes, Path)):
                    raise TypeError("expected str, bytes or os.PathLike object")
                filename = Path(filename_or_stream)
                if (
                    not getattr(self, '_tmp_stream', None)
                    and getattr(self, '_original_filename', None) is not None
                ):
                    check_different_files(self._original_filename, filename)
                stream = stack.enter_context(atomic_overwrite(filename))
            self._save(
                stream,
                static_id=static_id,
                preserve_pdfa=preserve_pdfa,
                min_version=min_version,
                force_version=force_version,
                fix_metadata_version=fix_metadata_version,
                compress_streams=compress_streams,
                stream_decode_level=stream_decode_level,
                object_stream_mode=object_stream_mode,
                normalize_content=normalize_content,
                linearize=linearize,
                qdf=qdf,
                progress=progress,
                encryption=encryption,
                samefile_check=getattr(self, '_tmp_stream', None) is None,
                recompress_flate=recompress_flate,
                deterministic_id=deterministic_id,
            )

    @staticmethod
    def open(
        filename_or_stream: Path | str | BinaryIO,
        *,
        password: str | bytes = "",
        hex_password: bool = False,
        ignore_xref_streams: bool = False,
        suppress_warnings: bool = True,
        attempt_recovery: bool = True,
        inherit_page_attributes: bool = True,
        access_mode: AccessMode = AccessMode.default,
        allow_overwriting_input: bool = False,
    ) -> Pdf:
        if isinstance(filename_or_stream, bytes) and filename_or_stream.startswith(
            b'%PDF-'
        ):
            warn(
                "It looks like you called with Pdf.open(data) with a bytes-like object "
                "containing a PDF. This will probably fail because this function "
                "expects a filename or opened file-like object. Instead, please use "
                "Pdf.open(BytesIO(data))."
            )
        if isinstance(filename_or_stream, int):
            # Attempted to open with integer file descriptor?
            # TODO improve error
            raise TypeError("expected str, bytes or os.PathLike object")

        stream: RawIOBase | None = None
        closing_stream: bool = False
        original_filename: Path | None = None

        if allow_overwriting_input:
            try:
                Path(filename_or_stream)
            except TypeError as error:
                raise ValueError(
                    '"allow_overwriting_input=True" requires "open" first argument '
                    'to be a file path'
                ) from error
            original_filename = Path(filename_or_stream)
            with open(original_filename, 'rb') as pdf_file:
                stream = BytesIO()
                shutil.copyfileobj(pdf_file, stream)
                stream.seek(0)
            # description = f"memory copy of {original_filename}"
            description = str(original_filename)
        elif hasattr(filename_or_stream, 'read') and hasattr(
            filename_or_stream, 'seek'
        ):
            stream = filename_or_stream
            description = f"stream {stream}"
        else:
            stream = open(filename_or_stream, 'rb')
            original_filename = Path(filename_or_stream)
            description = str(filename_or_stream)
            closing_stream = True

        check_stream_is_usable(stream)
        pdf = Pdf._open(
            stream,
            password=password,
            hex_password=hex_password,
            ignore_xref_streams=ignore_xref_streams,
            suppress_warnings=suppress_warnings,
            attempt_recovery=attempt_recovery,
            inherit_page_attributes=inherit_page_attributes,
            access_mode=access_mode,
            description=description,
            closing_stream=closing_stream,
        )
        pdf._tmp_stream = stream if allow_overwriting_input else None
        pdf._original_filename = original_filename
        return pdf


@augments(_ObjectMapping)
class Extend_ObjectMapping:
    def get(self, key, default=None) -> Object:
        try:
            return self[key]
        except KeyError:
            return default

    @augment_override_cpp
    def __contains__(self, key: Name | str) -> bool:
        if isinstance(key, Name):
            key = str(key)
        return _ObjectMapping._cpp__contains__(self, key)

    @augment_override_cpp
    def __getitem__(self, key: Name | str) -> Object:
        if isinstance(key, Name):
            key = str(key)
        return _ObjectMapping._cpp__getitem__(self, key)


def check_is_box(obj) -> None:
    try:
        if obj.is_rectangle:
            return
    except AttributeError:
        pass

    try:
        pdfobj = Array(obj)
        if pdfobj.is_rectangle:
            return
    except Exception as e:
        raise ValueError("object is not a rectangle") from e

    raise ValueError("object is not a rectangle")


@augments(Page)
class Extend_Page:
    @property
    def mediabox(self):
        """Return page's /MediaBox, in PDF units.

        According to the PDF specification:
        "The media box defines the boundaries of the physical medium on which
        the page is to be printed."
        """
        return self._get_mediabox(True)

    @mediabox.setter
    def mediabox(self, value):
        check_is_box(value)
        self.obj['/MediaBox'] = value

    @property
    def artbox(self):
        """Return page's effective /ArtBox, in PDF units.

        According to the PDF specification:
        "The art box defines the page's meaningful content area, including
        white space."

        If the /ArtBox is not defined, the /CropBox is returned.
        """
        return self._get_artbox(True, False)

    @artbox.setter
    def artbox(self, value):
        check_is_box(value)
        self.obj['/ArtBox'] = value

    @property
    def bleedbox(self):
        """Return page's effective /BleedBox, in PDF units.

        According to the PDF specification:
        "The bleed box defines the region to which the contents of the page
        should be clipped when output in a print production environment."

        If the /BleedBox is not defined, the /CropBox is returned.
        """
        return self._get_bleedbox(True, False)

    @bleedbox.setter
    def bleedbox(self, value):
        check_is_box(value)
        self.obj['/BleedBox'] = value

    @property
    def cropbox(self):
        """Return page's effective /CropBox, in PDF units.

        According to the PDF specification:
        "The crop box defines the region to which the contents of the page
        shall be clipped (cropped) when displayed or printed. It has no
        defined meaning in the context of the PDF imaging model; it merely
        imposes clipping on the page contents."

        If the /CropBox is not defined, the /MediaBox is returned.
        """
        return self._get_cropbox(True, False)

    @cropbox.setter
    def cropbox(self, value):
        check_is_box(value)
        self.obj['/CropBox'] = value

    @property
    def trimbox(self):
        """Return page's effective /TrimBox, in PDF units.

        According to the PDF specification:
        "The trim box defines the intended dimensions of the finished page
        after trimming. It may be smaller than the media box to allow for
        production-related content, such as printing instructions, cut marks,
        or color bars."

        If the /TrimBox is not defined, the /CropBox is returned (and if
        /CropBox is not defined, /MediaBox is returned).
        """
        return self._get_trimbox(True, False)

    @trimbox.setter
    def trimbox(self, value):
        check_is_box(value)
        self.obj['/TrimBox'] = value

    @property
    def images(self) -> _ObjectMapping:
        """Return all regular images associated with this page.

        This method does not search for Form XObjects that contain images,
        and does not attempt to find inline images.
        """
        return self._images

    @property
    def form_xobjects(self) -> _ObjectMapping:
        """Return all Form XObjects associated with this page.

        This method does not recurse into nested Form XObjects.

        .. versionadded:: 7.0.0
        """
        return self._form_xobjects

    @property
    def resources(self) -> Dictionary:
        """Return this page's resources dictionary.

        .. versionchanged:: 7.0.0
            If the resources dictionary does not exist, an empty one will be created.
            A TypeError is raised if a page has a /Resources key but it is not a
            dictionary.
        """
        if Name.Resources not in self.obj:
            self.obj.Resources = Dictionary()
        elif not isinstance(self.obj.Resources, Dictionary):
            raise TypeError("Page /Resources exists but is not a dictionary")
        return self.obj.Resources

    def add_resource(
        self,
        res: Object,
        res_type: Name,
        name: Name | None = None,
        *,
        prefix: str = '',
        replace_existing: bool = True,
    ) -> Name:
        """Add a new resource to the page's Resources dictionary.

        If the Resources dictionaries do not exist, they will be created.

        Args:
            self: The object to add to the resources dictionary.
            res: The dictionary object to insert into the resources
                dictionary.
            res_type: Should be one of the following Resource dictionary types:
                ExtGState, ColorSpace, Pattern, Shading, XObject, Font, Properties.
            name: The name of the object. If omitted, a random name will be
                generated with enough randomness to be globally unique.
            prefix: A prefix for the name of the object. Allows conveniently
                namespacing when using random names, e.g. prefix="Im" for images.
                Mutually exclusive with name parameter.
            replace_existing: If the name already exists in one of the resource
                dictionaries, remove it.

        Example:
            >>> resource_name = pdf.pages[0].add_resource(formxobj, Name.XObject)

        .. versionadded:: 2.3

        .. versionchanged:: 2.14
            If *res* does not belong to the same `Pdf` that owns this page,
            a copy of *res* is automatically created and added instead. In previous
            versions, it was necessary to change for this case manually.

        .. versionchanged:: 4.3.0
            Returns the name of the overlay in the resources dictionary instead
            of returning None.
        """
        resources = self.resources
        if res_type not in resources:
            resources[res_type] = Dictionary()

        if name is not None and prefix:
            raise ValueError("Must specify one of name= or prefix=")
        if name is None:
            name = Name.random(prefix=prefix)

        for res_dict in resources.as_dict().values():
            if not isinstance(res_dict, Dictionary):
                continue
            if name in res_dict:
                if replace_existing:
                    del res_dict[name]
                else:
                    raise ValueError(f"Name {name} already exists in page /Resources")

        resources[res_type][name] = res.with_same_owner_as(self.obj)
        return name

    def _over_underlay(
        self,
        other,
        rect: Rectangle | None,
        under: bool,
        push_stack: bool,
        shrink: bool,
        expand: bool,
    ) -> Name:
        formx = None
        if isinstance(other, Page):
            formx = other.as_form_xobject()
        elif isinstance(other, Dictionary) and other.get(Name.Type) == Name.Page:
            formx = Page(other).as_form_xobject()
        elif (
            isinstance(other, Stream)
            and other.get(Name.Type) == Name.XObject
            and other.get(Name.Subtype) == Name.Form
        ):
            formx = other

        if formx is None:
            raise TypeError(
                "other object is not something we can convert to Form XObject"
            )

        if rect is None:
            rect = Rectangle(self.trimbox)

        formx_placed_name = self.add_resource(formx, Name.XObject)
        cs = self.calc_form_xobject_placement(
            formx, formx_placed_name, rect, allow_shrink=shrink, allow_expand=expand
        )

        if push_stack:
            self.contents_add(b'q\n', prepend=True)  # prepend q
            self.contents_add(b'Q\n', prepend=False)  # i.e. append Q

        self.contents_add(cs, prepend=under)
        self.contents_coalesce()
        return formx_placed_name

    def add_overlay(
        self,
        other: Object | Page,
        rect: Rectangle | None = None,
        *,
        push_stack: bool = True,
        shrink: bool = True,
        expand: bool = True,
    ) -> Name:
        """Overlay another object on this page.

        Overlays will be drawn after all previous content, potentially drawing on top
        of existing content.

        Args:
            other: A Page or Form XObject to render as an overlay on top of this
                page.
            rect: The PDF rectangle (in PDF units) in which to draw the overlay.
                If omitted, this page's trimbox, cropbox or mediabox (in that order)
                will be used.
            push_stack: If True (default), push the graphics stack of the existing
                content stream to ensure that the overlay is rendered correctly.
                Officially PDF limits the graphics stack depth to 32. Most
                viewers will tolerate more, but excessive pushes may cause problems.
                Multiple content streams may also be coalesced into a single content
                stream where this parameter is True, since the PDF specification
                permits PDF writers to coalesce streams as they see fit.
            shrink: If True (default), allow the object to shrink to fit inside the
                rectangle. The aspect ratio will be preserved.
            expand: If True (default), allow the object to expand to fit inside the
                rectangle. The aspect ratio will be preserved.

        Returns:
            The name of the Form XObject that contains the overlay.

        .. versionadded:: 2.14

        .. versionchanged:: 4.0.0
            Added the *push_stack* parameter. Previously, this method behaved
            as if *push_stack* were False.

        .. versionchanged:: 4.2.0
            Added the *shrink* and *expand* parameters. Previously, this method
            behaved as if ``shrink=True, expand=False``.

        .. versionchanged:: 4.3.0
            Returns the name of the overlay in the resources dictionary instead
            of returning None.
        """
        return self._over_underlay(
            other,
            rect,
            under=False,
            push_stack=push_stack,
            expand=expand,
            shrink=shrink,
        )

    def add_underlay(
        self,
        other: Object | Page,
        rect: Rectangle | None = None,
        *,
        shrink: bool = True,
        expand: bool = True,
    ) -> Name:
        """Underlay another object beneath this page.

        Underlays will be drawn before all other content, so they may be overdrawn
        partially or completely.

        There is no *push_stack* parameter for this function, since adding an
        underlay can be done without manipulating the graphics stack.

        Args:
            other: A Page or Form XObject to render as an underlay underneath this
                page.
            rect: The PDF rectangle (in PDF units) in which to draw the underlay.
                If omitted, this page's trimbox, cropbox or mediabox (in that order)
                will be used.
            shrink: If True (default), allow the object to shrink to fit inside the
                rectangle. The aspect ratio will be preserved.
            expand: If True (default), allow the object to expand to fit inside the
                rectangle. The aspect ratio will be preserved.

        Returns:
            The name of the Form XObject that contains the underlay.

        .. versionadded:: 2.14

        .. versionchanged:: 4.2.0
            Added the *shrink* and *expand* parameters. Previously, this method
            behaved as if ``shrink=True, expand=False``. Fixed issue with wrong
            page rect being selected.
        """
        return self._over_underlay(
            other, rect, under=True, push_stack=False, expand=expand, shrink=shrink
        )

    def contents_add(self, contents: Stream | bytes, *, prepend: bool = False):
        """Append or prepend to an existing page's content stream.

        Args:
            contents: An existing content stream to append or prepend.
            prepend: Prepend if true, append if false (default).

        .. versionadded:: 2.14
        """
        return self._contents_add(contents, prepend=prepend)

    def __getattr__(self, name):
        return getattr(self.obj, name)

    @augment_override_cpp
    def __setattr__(self, name, value):
        if hasattr(self.__class__, name):
            object.__setattr__(self, name, value)
        else:
            setattr(self.obj, name, value)

    @augment_override_cpp
    def __delattr__(self, name):
        if hasattr(self.__class__, name):
            object.__delattr__(self, name)
        else:
            delattr(self.obj, name)

    def __getitem__(self, key):
        return self.obj[key]

    def __setitem__(self, key, value):
        self.obj[key] = value

    def __delitem__(self, key):
        del self.obj[key]

    def __contains__(self, key):
        return key in self.obj

    def get(self, key, default=None):
        try:
            return self[key]
        except KeyError:
            return default

    def emplace(self, other: Page, retain=(Name.Parent,)):
        return self.obj.emplace(other.obj, retain=retain)

    def __repr__(self):
        return (
            repr(self.obj)
            .replace('Dictionary', 'Page', 1)
            .replace('(Type="/Page")', '', 1)
        )

    def _repr_mimebundle_(self, include=None, exclude=None):
        data = {}
        bundle = {'application/pdf', 'image/png'}
        if include:
            bundle = {k for k in bundle if k in include}
        if exclude:
            bundle = {k for k in bundle if k not in exclude}
        pagedata = _single_page_pdf(self.obj)
        if 'application/pdf' in bundle:
            data['application/pdf'] = pagedata
        if 'image/png' in bundle:
            try:
                data['image/png'] = _mudraw(pagedata, 'png')
            except (FileNotFoundError, RuntimeError):
                pass
        return data


@augments(Token)
class Extend_Token:
    def __repr__(self):
        return f'pikepdf.Token({self.type_}, {self.raw_value})'


@augments(Rectangle)
class Extend_Rectangle:
    def __repr__(self):
        return f'pikepdf.Rectangle({self.llx}, {self.lly}, {self.urx}, {self.ury})'

    def __hash__(self):
        return hash((self.llx, self.lly, self.urx, self.ury))


@augments(Attachments)
class Extend_Attachments(MutableMapping):
    def __getitem__(self, k: str) -> AttachedFileSpec:
        filespec = self._get_filespec(k)
        if filespec is None:
            raise KeyError(k)
        return filespec

    def __setitem__(self, k: str, v: AttachedFileSpec) -> None:
        if not v.filename:
            v.filename = k
        return self._add_replace_filespec(k, v)

    def __delitem__(self, k: str) -> None:
        return self._remove_filespec(k)

    def __len__(self):
        return len(self._get_all_filespecs())

    def __iter__(self) -> Iterator[str]:
        yield from self._get_all_filespecs()

    def __repr__(self):
        return f"<pikepdf._core.Attachments with {len(self)} attached files>"


@augments(AttachedFileSpec)
class Extend_AttachedFileSpec:
    @staticmethod
    def from_filepath(
        pdf: Pdf,
        path: Path | str,
        *,
        description: str = '',
        relationship: Name | None = Name.Unspecified,
    ):
        mime, _ = mimetypes.guess_type(str(path))
        if mime is None:
            mime = ''
        if not isinstance(path, Path):
            path = Path(path)

        stat = path.stat()
        return AttachedFileSpec(
            pdf,
            path.read_bytes(),
            description=description,
            filename=str(path.name),
            mime_type=mime,
            creation_date=encode_pdf_date(
                datetime.datetime.fromtimestamp(stat.st_ctime)
            ),
            mod_date=encode_pdf_date(datetime.datetime.fromtimestamp(stat.st_mtime)),
            relationship=relationship,
        )

    @property
    def relationship(self) -> Name | None:
        return self.obj.get(Name.AFRelationship)

    @relationship.setter
    def relationship(self, value: Name | None):
        if value is None:
            del self.obj[Name.AFRelationship]
        else:
            self.obj[Name.AFRelationship] = value

    def __repr__(self):
        if self.filename:
            return (
                f"<pikepdf._core.AttachedFileSpec for {self.filename!r}, "
                f"description {self.description!r}>"
            )
        return f"<pikepdf._core.AttachedFileSpec description {self.description!r}>"


@augments(AttachedFile)
class Extend_AttachedFile:
    @property
    def creation_date(self) -> datetime.datetime | None:
        if not self._creation_date:
            return None
        return decode_pdf_date(self._creation_date)

    @creation_date.setter
    def creation_date(self, value: datetime.datetime):
        self._creation_date = encode_pdf_date(value)

    @property
    def mod_date(self) -> datetime.datetime | None:
        if not self._mod_date:
            return None
        return decode_pdf_date(self._mod_date)

    @mod_date.setter
    def mod_date(self, value: datetime.datetime):
        self._mod_date = encode_pdf_date(value)

    def read_bytes(self) -> bytes:
        return self.obj.read_bytes()

    def __repr__(self):
        return (
            f'<pikepdf._core.AttachedFile objid={self.obj.objgen} size={self.size} '
            f'mime_type={self.mime_type} creation_date={self.creation_date} '
            f'mod_date={self.mod_date}>'
        )


@augments(NameTree)
class Extend_NameTree:
    def keys(self):
        return KeysView(self._as_map())

    def values(self):
        return ValuesView(self._as_map())

    def items(self):
        return ItemsView(self._as_map())

    get = MutableMapping.get
    pop = MutableMapping.pop
    popitem = MutableMapping.popitem
    clear = MutableMapping.clear
    update = MutableMapping.update
    setdefault = MutableMapping.setdefault


MutableMapping.register(NameTree)


@augments(NumberTree)
class Extend_NumberTree:
    def keys(self):
        return KeysView(self._as_map())

    def values(self):
        return ValuesView(self._as_map())

    def items(self):
        return ItemsView(self._as_map())

    get = MutableMapping.get
    pop = MutableMapping.pop
    popitem = MutableMapping.popitem
    clear = MutableMapping.clear
    update = MutableMapping.update
    setdefault = MutableMapping.setdefault


MutableMapping.register(NumberTree)
