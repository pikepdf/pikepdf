# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
#
# Copyright (C) 2017, James R. Barlow (https://github.com/jbarlow83/)

"""
In several cases the implementation of some higher levels features might as
well be in Python. Fortunately we can attach Python methods to C++ class
bindings after the fact.

We can also move the implementation to C++ if desired.
"""

import inspect
import shutil
from collections.abc import KeysView
from decimal import Decimal
from io import BytesIO
from os import replace
from pathlib import Path
from subprocess import PIPE, run
from tempfile import NamedTemporaryFile
from typing import Any, BinaryIO, Callable, List, Optional, Tuple, Type, TypeVar, Union
from warnings import warn

from . import Array, Dictionary, Name, Object, Page, Pdf, Stream
from ._qpdf import (
    AccessMode,
    ObjectStreamMode,
    PdfError,
    StreamDecodeLevel,
    StreamParser,
    Token,
    _ObjectMapping,
)
from .models import Encryption, EncryptionInfo, Outline, PdfMetadata, Permissions

# pylint: disable=no-member,unsupported-membership-test,unsubscriptable-object
# mypy: ignore-errors

__all__ = []

Numeric = TypeVar('Numeric', int, float, Decimal)


def augments(cls_cpp: Type[Any]):
    """Attach methods of a Python support class to an existing class

    This monkeypatches all methods defined in the support class onto an
    existing class. Example:

    .. code-block:: python

        @augments(ClassDefinedInCpp)
        class SupportClass:
            def foo(self):
                pass

    The Python method 'foo' will be monkeypatched on ClassDefinedInCpp. SupportClass
    has no meaning on its own and should not be used, but gets returned from
    this function so IDE code inspection doesn't get too confused.

    We don't subclass because it's much more convenient to monkeypatch Python
    methods onto the existing Python binding of the C++ class. For one thing,
    this allows the implementation to be moved from Python to C++ or vice
    versa. It saves having to implement an intermediate Python subclass and then
    ensures that the C++ superclass never 'leaks' to pikepdf users. Finally,
    wrapper classes and subclasses can become problematic if the call stack
    crosses the C++/Python boundary multiple times.

    Any existing methods may be used, regardless of whether they are defined
    elsewhere in the support class or in the target class.

    For data fields to work, including @property accessors, the target class must be
    tagged ``py::dynamic_attr`` in pybind11.

    Strictly, the target class does not have to be C++ or derived from pybind11.
    This works on pure Python classes too.

    THIS DOES NOT work for class methods.

    (Alternative ideas: https://github.com/pybind/pybind11/issues/1074)
    """
    ATTR_WHITELIST = {'__repr__', '__enter__', '__exit__'}

    def class_augment(cls, cls_cpp=cls_cpp):
        for name, member in inspect.getmembers(cls):
            # Don't replace existing methods except those in our whitelist
            if hasattr(cls_cpp, name) and name not in ATTR_WHITELIST:
                continue
            if inspect.isfunction(member):
                if member.__qualname__.startswith('object.'):
                    continue  # To avoid breaking PyPy
                member.__qualname__ = member.__qualname__.replace(
                    cls.__name__, cls_cpp.__name__
                )
                setattr(cls_cpp, name, member)
            elif inspect.isdatadescriptor(member):
                setattr(cls_cpp, name, member)

        def disable_init(self):
            # Prevent initialization of the support class
            raise NotImplementedError(self.__class__.__name__ + '.__init__')

        cls.__init__ = disable_init
        return cls

    return class_augment


def _single_page_pdf(page) -> bytes:
    """Construct a single page PDF from the provided page in memory"""
    pdf = Pdf.new()
    pdf.pages.append(page)
    bio = BytesIO()
    pdf.save(bio)
    bio.seek(0)
    return bio.read()


def _mudraw(buffer, fmt) -> bytes:
    """Use mupdf draw to rasterize the PDF in the memory buffer"""
    # mudraw cannot read from stdin so NamedTemporaryFile is required
    with NamedTemporaryFile(suffix='.pdf') as tmp_in:
        tmp_in.write(buffer)
        tmp_in.seek(0)
        tmp_in.flush()

        proc = run(
            ['mudraw', '-F', fmt, '-o', '-', tmp_in.name],
            stdout=PIPE,
            stderr=PIPE,
            check=True,
        )
        return proc.stdout


@augments(Object)
class Extend_Object:
    def _repr_mimebundle_(self, include=None, exclude=None):
        """Present options to IPython for rich display of this object

        See https://ipython.readthedocs.io/en/stable/config/integrating.html#rich-display
        """

        if (
            isinstance(self, Dictionary)
            and Name.Type in self
            and self.Type == Name.Page
        ):
            return Page(self)._repr_mimebundle_(include, exclude)
        return None

    def _ipython_key_completions_(self):
        if isinstance(self, (Dictionary, Stream)):
            return self.keys()
        return None

    def emplace(self, other: Object, retain=(Name.Parent,)):
        """Copy all items from other without making a new object.

        Particularly when working with pages, it may be desirable to remove all
        of the existing page's contents and emplace (insert) a new page on top
        of it, in a way that preserves all links and references to the original
        page. (Or similarly, for other Dictionary objects in a PDF.)

        Any Dictionary keys in the iterable *retain* are preserved. By default,
        /Parent is retained.

        When a page is assigned (``pdf.pages[0] = new_page``), only the
        application knows if references to the original the original page are
        still valid. For example, a PDF optimizer might restructure a page
        object into another visually similar one, and references would be valid;
        but for a program that reorganizes page contents such as a N-up
        compositor, references may not be valid anymore.

        This method takes precautions to ensure that child objects in common
        with ``self`` and ``other`` are not inadvertently deleted.

        Example:
            >>> pdf.pages[0].objgen
            (16, 0)
            >>> pdf.pages[0].emplace(pdf.pages[1])
            >>> pdf.pages[0].objgen
            (16, 0)  # Same object

        .. versionchanged:: 2.11.1
            Added the *retain* argument.
        """
        if not self.same_owner_as(other):
            raise TypeError("Objects must have the same owner for emplace()")

        # .keys() returns strings, so make all strings
        retain = set(str(k) for k in retain)
        self_keys = set(self.keys())
        other_keys = set(other.keys())

        assert all(isinstance(k, str) for k in (retain | self_keys | other_keys))

        del_keys = self_keys - other_keys - retain
        for k in (k for k in other_keys if k not in retain):
            self[k] = other[k]  # pylint: disable=unsupported-assignment-operation
        for k in del_keys:
            del self[k]  # pylint: disable=unsupported-delete-operation

    def write(
        self,
        data: bytes,
        *,
        filter: Union[Name, Array, None] = None,
        decode_parms: Union[Dictionary, Array, None] = None,
        type_check: bool = True,
    ):  # pylint: disable=redefined-builtin
        """
        Replace stream object's data with new (possibly compressed) `data`.

        `filter` and `decode_parms` specify that compression that is present on
        the input `data`.

        When writing the PDF in :meth:`pikepdf.Pdf.save`,
        pikepdf may change the compression or apply compression to data that was
        not compressed, depending on the parameters given to that function. It
        will never change lossless to lossy encoding.

        PNG and TIFF images, even if compressed, cannot be directly inserted
        into a PDF and displayed as images.

        Args:
            data: the new data to use for replacement
            filter: The filter(s) with which the
                data is (already) encoded
            decode_parms: Parameters for the
                filters with which the object is encode
            type_check: Check arguments; use False only if you want to
                intentionally create malformed PDFs.

        If only one `filter` is specified, it may be a name such as
        `Name('/FlateDecode')`. If there are multiple filters, then array
        of names should be given.

        If there is only one filter, `decode_parms` is a Dictionary of
        parameters for that filter. If there are multiple filters, then
        `decode_parms` is an Array of Dictionary, where each array index
        is corresponds to the filter.
        """

        if type_check and filter is not None:
            if isinstance(filter, list):
                filter = Array(filter)
            filter = filter.wrap_in_array()

            if isinstance(decode_parms, list):
                decode_parms = Array(decode_parms)
            elif decode_parms is None:
                decode_parms = Array([])
            else:
                decode_parms = decode_parms.wrap_in_array()

            if not all(isinstance(item, Name) for item in filter):
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
            if len(decode_parms) != 0:
                if len(filter) != len(decode_parms):
                    raise ValueError(
                        f"filter ({repr(filter)}) and decode_parms "
                        f"({repr(decode_parms)}) must be arrays of same length"
                    )
            if len(filter) == 1:
                filter = filter[0]
            if len(decode_parms) == 0:
                decode_parms = None
            elif len(decode_parms) == 1:
                decode_parms = decode_parms[0]
        self._write(data, filter=filter, decode_parms=decode_parms)


@augments(Pdf)
class Extend_Pdf:
    @property
    def root(self):
        """
        Deprecated alias for .Root, the /Root object of the PDF.

        .. deprecated:: 2.0
            Use ``.Root``.
        """
        warn("Pdf.root is deprecated; use Pdf.Root", category=DeprecationWarning)
        return self.Root

    def _repr_mimebundle_(self, include=None, exclude=None):
        """
        Present options to IPython or Jupyter for rich display of this object

        See https://ipython.readthedocs.io/en/stable/config/integrating.html#rich-display
        """

        bio = BytesIO()
        self.save(bio)
        bio.seek(0)

        data = {'application/pdf': bio.read()}
        return data

    @property
    def docinfo(self) -> Dictionary:
        """
        Access the (deprecated) document information dictionary.

        The document information dictionary is a brief metadata record that can
        store some information about the origin of a PDF. It is deprecated and
        removed in the PDF 2.0 specification (not deprecated from the
        perspective of pikepdf). Use the ``.open_metadata()`` API instead, which
        will edit the modern (and unfortunately, more complicated) XMP metadata
        object and synchronize changes to the document information dictionary.

        This property simplifies access to the actual document information
        dictionary and ensures that it is created correctly if it needs to be
        created.

        A new, empty dictionary will be created if this property is accessed
        and dictionary does not exist. (This is to ensure that convenient code
        like ``pdf.docinfo[Name.Title] = "Title"`` will work when the dictionary
        does not exist at all.)

        You can delete the document information dictionary by deleting this property,
        ``del pdf.docinfo``. Note that accessing the property after deleting it
        will re-create with a new, empty dictionary.

        .. versionchanged: 2.4
            Added support for ``del pdf.docinfo``.
        """
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
        """
        Open the PDF's XMP metadata for editing.

        There is no ``.close()`` function on the metadata object, since this is
        intended to be used inside a ``with`` block only.

        For historical reasons, certain parts of PDF metadata are stored in
        two different locations and formats. This feature coordinates edits so
        that both types of metadata are updated consistently and "atomically"
        (assuming single threaded access). It operates on the ``Pdf`` in memory,
        not any file on disk. To persist metadata changes, you must still use
        ``Pdf.save()``.

        Example:
            >>> with pdf.open_metadata() as meta:
                    meta['dc:title'] = 'Set the Dublic Core Title'
                    meta['dc:description'] = 'Put the Abstract here'

        Args:
            set_pikepdf_as_editor: Automatically update the metadata ``pdf:Producer``
                to show that this version of pikepdf is the most recent software to
                modify the metadata, and ``xmp:MetadataDate`` to timestamp the update.
                Recommended, except for testing.

            update_docinfo: Update the standard fields of DocumentInfo
                (the old PDF metadata dictionary) to match the corresponding
                XMP fields. The mapping is described in
                :attr:`PdfMetadata.DOCINFO_MAPPING`. Nonstandard DocumentInfo
                fields and XMP metadata fields with no DocumentInfo equivalent
                are ignored.

            strict: If ``False`` (the default), we aggressively attempt
                to recover from any parse errors in XMP, and if that fails we
                overwrite the XMP with an empty XMP record.  If ``True``, raise
                errors when either metadata bytes are not valid and well-formed
                XMP (and thus, XML). Some trivial cases that are equivalent to
                empty or incomplete "XMP skeletons" are never treated as errors,
                and always replaced with a proper empty XMP block. Certain
                errors may be logged.
        """
        return PdfMetadata(
            self,
            pikepdf_mark=set_pikepdf_as_editor,
            sync_docinfo=update_docinfo,
            overwrite_invalid_xml=not strict,
        )

    def open_outline(self, max_depth: int = 15, strict: bool = False) -> Outline:
        """
        Open the PDF outline ("bookmarks") for editing.

        Recommend for use in a ``with`` block. Changes are committed to the
        PDF when the block exits. (The ``Pdf`` must still be opened.)

        Example:
            >>> with pdf.open_outline() as outline:
                    outline.root.insert(0, OutlineItem('Intro', 0))

        Args:
            max_depth: Maximum recursion depth of the outline to be
                imported and re-written to the document. ``0`` means only
                considering the root level, ``1`` the first-level
                sub-outline of each root element, and so on. Items beyond
                this depth will be silently ignored. Default is ``15``.
            strict: With the default behavior (set to ``False``),
                structural errors (e.g. reference loops) in the PDF document
                will only cancel processing further nodes on that particular
                level, recovering the valid parts of the document outline
                without raising an exception. When set to ``True``, any such
                error will raise an ``OutlineStructureError``, leaving the
                invalid parts in place.
                Similarly, outline objects that have been accidentally
                duplicated in the ``Outline`` container will be silently
                fixed (i.e. reproduced as new objects) or raise an
                ``OutlineStructureError``.
        """
        return Outline(self, max_depth=max_depth, strict=strict)

    def make_stream(self, data: bytes, d=None, **kwargs) -> Stream:
        """
        Create a new pikepdf.Stream object that is attached to this PDF.

        See:
            :meth:`pikepdf.Stream.__new__`

        """
        return Stream(self, data, d, **kwargs)

    def add_blank_page(
        self, *, page_size: Tuple[Numeric, Numeric] = (612.0, 792.0)
    ) -> Object:
        """
        Add a blank page to this PDF. If pages already exist, the page will be added to
        the end. Pages may be reordered using ``Pdf.pages``.

        The caller may add content to the page by modifying its objects after creating
        it.

        Args:
            page_size (tuple): The size of the page in PDF units (1/72 inch or 0.35mm).
                Default size is set to a US Letter 8.5" x 11" page.
        """
        for dim in page_size:
            if not (3 <= dim <= 14400):
                raise ValueError('Page size must be between 3 and 14400 PDF units')

        page_dict = Dictionary(
            Type=Name.Page,
            MediaBox=Array([0, 0, page_size[0], page_size[1]]),
            Contents=self.make_stream(b''),
            Resources=Dictionary(),
        )
        page = self.make_indirect(page_dict)
        self._add_page(page, first=False)
        return page

    def close(self) -> None:
        """
        Close a ``Pdf`` object and release resources acquired by pikepdf.

        If pikepdf opened the file handle it will close it (e.g. when opened with a file
        path). If the caller opened the file for pikepdf, the caller close the file.
        ``with`` blocks will call close when exit.

        pikepdf lazily loads data from PDFs, so some :class:`pikepdf.Object` may
        implicitly depend on the :class:`pikepdf.Pdf` being open. This is always the
        case for :class:`pikepdf.Stream` but can be true for any object. Do not close
        the `Pdf` object if you might still be accessing content from it.

        When an ``Object`` is copied from one ``Pdf`` to another, the ``Object`` is copied into
        the destination ``Pdf`` immediately, so after accessing all desired information
        from the source ``Pdf`` it may be closed.

        Caution:
            Closing the ``Pdf`` is currently implemented by resetting it to an empty
            sentinel. It is currently possible to edit the sentinel as if it were a live
            object. This behavior should not be relied on and is subject to change.
        """

        # We could use QPDF::closeInputSource(), but many functions like
        # QPDF::getFilename() will segfault if called without an open file, so it's
        # best to use a sentinel empty file.
        EMPTY_PDF = (
            b"%PDF-1.3\n"
            b"1 0 obj\n"
            b"<< /Type /Catalog /Pages 2 0 R >>\n"
            b"endobj\n"
            b"2 0 obj\n"
            b"<< /Type /Pages /Kids [] /Count 0 >>\n"
            b"endobj\n"
            b"xref\n"
            b"0 3\n"
            b"0000000000 65535 f \n"
            b"0000000009 00000 n \n"
            b"0000000058 00000 n \n"
            b"trailer << /Size 3 /Root 1 0 R >>\n"
            b"startxref\n"
            b"110\n"
            b"%%EOF\n"
        )

        description = "closed file: " + self.filename
        self._process(description, EMPTY_PDF)
        if getattr(self, '_tmp_stream', None):
            self._tmp_stream.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()

    @property
    def allow(self) -> Permissions:
        """
        Report permissions associated with this PDF.

        By default these permissions will be replicated when the PDF is
        saved. Permissions may also only be changed when a PDF is being saved,
        and are only available for encrypted PDFs. If a PDF is not encrypted,
        all operations are reported as allowed.

        pikepdf has no way of enforcing permissions.
        """
        results = {}
        for field in Permissions._fields:
            results[field] = getattr(self, '_allow_' + field)
        return Permissions(**results)

    @property
    def encryption(self) -> EncryptionInfo:
        """
        Report encryption information for this PDF.

        Encryption settings may only be changed when a PDF is saved.
        """
        return EncryptionInfo(self._encryption_data)

    def check(self) -> List[str]:
        """
        Check if PDF is well-formed.  Similar to ``qpdf --check``.
        """

        class DiscardingParser(StreamParser):
            def __init__(self):  # pylint: disable=useless-super-delegation
                super().__init__()  # required for C++

            def handle_object(self, obj):
                pass

            def handle_eof(self):
                pass

        problems: List[str] = []

        self._decode_all_streams_and_discard()

        discarding_parser = DiscardingParser()
        for basic_page in self.pages:
            page = Page(basic_page)
            page.parse_contents(discarding_parser)

        for warning in self.get_warnings():
            problems.append("WARNING: " + warning)

        return problems

    def _attach(
        self,
        *,
        basename: str,
        filebytes: bytes,
        mime: Optional[str] = None,
        desc: str = '',
    ):  # pragma: no cover
        """
        Attach a file to this PDF

        Args:
            basename (str): The basename (filename withouth path) to name the
                file. Not necessarily the name of the file on disk. Will be s
                hown to the user by the PDF viewer. filebytes (bytes): The file
                contents.

            mime (str or None): A MIME type for the filebytes. If omitted, we try
                to guess based on the standard library's
                :func:`mimetypes.guess_type`. If this cannot be determined, the
                generic value `application/octet-stream` is used. This value is
                used by PDF viewers to decide how to present the information to
                the user.

            desc (str): A extended description of the file contents. PDF viewers
                also display this information to the user. In Acrobat DC this is
                hidden in a context menu.

        The PDF will also be modified to request the PDF viewer to display the
        list of attachments when opened, as opposed to other viewing modes. Some
        PDF viewers will not make it obvious to the user that attachments are
        present unless this is done. This behavior may be overridden by changing
        ``pdf.Root.PageMode`` to some other valid value.

        """

        if '/Names' not in self.Root:
            self.Root.Names = self.make_indirect(Dictionary())
        if '/EmbeddedFiles' not in self.Root:
            self.Root.Names.EmbeddedFiles = self.make_indirect(Dictionary())
        if '/Names' not in self.Root.Names.EmbeddedFiles:
            self.Root.Names.EmbeddedFiles.Names = Array()

        if '/' in basename or '\\' in basename:
            raise ValueError("basename should be a basename (no / or \\)")

        if not mime:
            from mimetypes import guess_type

            mime, _encoding = guess_type(basename)
            if not mime:
                mime = 'application/octet-stream'

        filestream = Stream(self, filebytes)
        filestream.Subtype = Name('/' + mime)

        filespec = Dictionary(
            {
                '/Type': Name.Filespec,
                '/F': basename,
                '/UF': basename,
                '/Desc': desc,
                '/EF': Dictionary({'/F': filestream}),
            }
        )

        # names = self.Root.Names.EmbeddedFiles.Names.as_list()
        # names.append(filename)  # Key
        # names.append(self.make_indirect(filespec))
        self.Root.Names.EmbeddedFiles.Names = Array(
            [basename, self.make_indirect(filespec)]  # key
        )

        if '/PageMode' not in self.Root:
            self.Root.PageMode = Name.UseAttachments

    def save(
        self,  # TODO mandatory kwargs
        filename_or_stream: Union[Path, str, BinaryIO, None] = None,
        static_id: bool = False,
        preserve_pdfa: bool = True,
        min_version: Union[str, Tuple[str, int]] = "",
        force_version: Union[str, Tuple[str, int]] = "",
        fix_metadata_version: bool = True,
        compress_streams: bool = True,
        stream_decode_level: Optional[StreamDecodeLevel] = None,
        object_stream_mode: ObjectStreamMode = ObjectStreamMode.preserve,
        normalize_content: bool = False,
        linearize: bool = False,
        qdf: bool = False,
        progress: Callable[[int], None] = None,
        encryption: Optional[Union[Encryption, bool]] = None,
        recompress_flate: bool = False,
    ) -> None:
        """
        Save all modifications to this :class:`pikepdf.Pdf`.

        Args:
            filename_or_stream: Where to write the output. If a file
                exists in this location it will be overwritten.
                If the file was opened with ``allow_overwriting_input=True``,
                then it is permitted to overwrite the original file, and
                this parameter may be omitted to implicitly use the original
                filename. Otherwise, the filename may not be the same as the
                input file, as overwriting the input file would corrupt data
                since pikepdf using lazy loading.

            static_id: Indicates that the ``/ID`` metadata, normally
                calculated as a hash of certain PDF contents and metadata
                including the current time, should instead be generated
                deterministically. Normally for debugging.
            preserve_pdfa: Ensures that the file is generated in a
                manner compliant with PDF/A and other stricter variants.
                This should be True, the default, in most cases.

            min_version: Sets the minimum version of PDF
                specification that should be required. If left alone QPDF
                will decide. If a tuple, the second element is an integer, the
                extension level. If the version number is not a valid format,
                QPDF will decide what to do.
            force_version: Override the version recommend by QPDF,
                potentially creating an invalid file that does not display
                in old versions. See QPDF manual for details. If a tuple, the
                second element is an integer, the extension level.
            fix_metadata_version: If ``True`` (default) and the XMP metadata
                contains the optional PDF version field, ensure the version in
                metadata is correct. If the XMP metadata does not contain a PDF
                version field, none will be added. To ensure that the field is
                added, edit the metadata and insert a placeholder value in
                ``pdf:PDFVersion``. If XMP metadata does not exist, it will
                not be created regardless of the value of this argument.

            object_stream_mode:
                ``disable`` prevents the use of object streams.
                ``preserve`` keeps object streams from the input file.
                ``generate`` uses object streams wherever possible,
                creating the smallest files but requiring PDF 1.5+.

            compress_streams: Enables or disables the compression of
                stream objects in the PDF that are created without specifying
                any compression setting. Metadata is never compressed.
                By default this is set to ``True``, and should be except
                for debugging. Existing streams in the PDF or streams will not
                be modified. To decompress existing streams, you must set
                both ``compress_streams=False`` and ``stream_decode_level``
                to the desired decode level (e.g. ``.generalized`` will
                decompress most non-image content).

            stream_decode_level: Specifies how
                to encode stream objects. See documentation for
                ``StreamDecodeLevel``.

            recompress_flate: When disabled (the default), qpdf does not
                uncompress and recompress streams compressed with the Flate
                compression algorithm. If True, pikepdf will instruct qpdf to
                do this, which may be useful if recompressing streams to a
                higher compression level.

            normalize_content: Enables parsing and reformatting the
                content stream within PDFs. This may debugging PDFs easier.

            linearize: Enables creating linear or "fast web view",
                where the file's contents are organized sequentially so that
                a viewer can begin rendering before it has the whole file.
                As a drawback, it tends to make files larger.

            qdf: Save output QDF mode.  QDF mode is a special output
                mode in QPDF to allow editing of PDFs in a text editor. Use
                the program ``fix-qdf`` to fix convert back to a standard
                PDF.

            progress: Specify a callback function that is called
                as the PDF is written. The function will be called with an
                integer between 0-100 as the sole parameter, the progress
                percentage. This function may not access or modify the PDF
                while it is being written, or data corruption will almost
                certainly occur.

            encryption: If ``False``
                or omitted, existing encryption will be removed. If ``True``
                encryption settings are copied from the originating PDF.
                Alternately, an ``Encryption`` object may be provided that
                sets the parameters for new encryption.

        Raises:
            PdfError
            ForeignObjectError

        You may call ``.save()`` multiple times with different parameters
        to generate different versions of a file, and you *may* continue
        to modify the file after saving it. ``.save()`` does not modify
        the ``Pdf`` object in memory, except possibly by updating the XMP
        metadata version with ``fix_metadata_version``.

        .. note::

            :meth:`pikepdf.Pdf.remove_unreferenced_resources` before saving
            may eliminate unnecessary resources from the output file if there
            are any objects (such as images) that are referenced in a page's
            Resources dictionary but never called in the page's content stream.

        .. note::

            pikepdf can read PDFs with incremental updates, but always
            coalesces any incremental updates into a single non-incremental
            PDF file when saving.

        .. versionchanged:: 2.7
            Added *recompress_flate*.
        """
        if not filename_or_stream and self._original_filename:
            filename_or_stream = self._original_filename
        self._save(
            filename_or_stream,
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
        )

    @staticmethod
    def open(  # TODO mandatory kwargs
        filename_or_stream: Union[Path, str, BinaryIO],
        password: Union[str, bytes] = "",
        hex_password: bool = False,
        ignore_xref_streams: bool = False,
        suppress_warnings: bool = True,
        attempt_recovery: bool = True,
        inherit_page_attributes: bool = True,
        access_mode: AccessMode = AccessMode.default,
        allow_overwriting_input: bool = False,
    ) -> Pdf:
        """
        Open an existing file at *filename_or_stream*.

        If *filename_or_stream* is path-like, the file will be opened for reading.
        The file should not be modified by another process while it is open in
        pikepdf, or undefined behavior may occur. This is because the file may be
        lazily loaded. Despite this restriction, pikepdf does not try to use any OS
        services to obtain an exclusive lock on the file. Some applications may
        want to attempt this or copy the file to a temporary location before
        editing. This behaviour changes if *allow_overwriting_input* is set: the whole
        file is then read and copied to memory, so that pikepdf can overwrite it
        when calling ``.save()``.

        When this function is called with a stream-like object, you must ensure
        that the data it returns cannot be modified, or undefined behavior will
        occur.

        Any changes to the file must be persisted by using ``.save()``.

        If *filename_or_stream* has ``.read()`` and ``.seek()`` methods, the file
        will be accessed as a readable binary stream. pikepdf will read the
        entire stream into a private buffer.

        ``.open()`` may be used in a ``with``-block; ``.close()`` will be called when
        the block exits, if applicable.

        Whenever pikepdf opens a file, it will close it. If you open the file
        for pikepdf or give it a stream-like object to read from, you must
        release that object when appropriate.

        Examples:

            >>> with Pdf.open("test.pdf") as pdf:
                    ...

            >>> pdf = Pdf.open("test.pdf", password="rosebud")

        Args:
            filename_or_stream: Filename or Python readable and seekable file
                stream of PDF to open.
            password: User or owner password to open an
                encrypted PDF. If the type of this parameter is ``str``
                it will be encoded as UTF-8. If the type is ``bytes`` it will
                be saved verbatim. Passwords are always padded or
                truncated to 32 bytes internally. Use ASCII passwords for
                maximum compatibility.
            hex_password: If True, interpret the password as a
                hex-encoded version of the exact encryption key to use, without
                performing the normal key computation. Useful in forensics.
            ignore_xref_streams: If True, ignore cross-reference
                streams. See qpdf documentation.
            suppress_warnings: If True (default), warnings are not
                printed to stderr. Use :meth:`pikepdf.Pdf.get_warnings()` to
                retrieve warnings.
            attempt_recovery: If True (default), attempt to recover
                from PDF parsing errors.
            inherit_page_attributes: If True (default), push attributes
                set on a group of pages to individual pages
            access_mode: If ``.default``, pikepdf will
                decide how to access the file. Currently, it will always
                selected stream access. To attempt memory mapping and fallback
                to stream if memory mapping failed, use ``.mmap``.  Use
                ``.mmap_only`` to require memory mapping or fail
                (this is expected to only be useful for testing). Applications
                should be prepared to handle the SIGBUS signal on POSIX in
                the event that the file is successfully mapped but later goes
                away.
            allow_overwriting_input: If True, allows calling ``.save()``
                to overwrite the input file. This is performed by loading the
                entire input file into memory at open time; this will use more
                memory and may recent performance especially when the opened
                file will not be modified.
        Raises:
            pikepdf.PasswordError: If the password failed to open the
                file.
            pikepdf.PdfError: If for other reasons we could not open
                the file.
            TypeError: If the type of ``filename_or_stream`` is not
                usable.
            FileNotFoundError: If the file was not found.

        Note:
            When *filename_or_stream* is a stream and the stream is located on a
            network, pikepdf assumes that the stream using buffering and read caches
            to achieve reasonable performance. Streams that fetch data over a network
            in response to every read or seek request, no matter how small, will
            perform poorly. It may be easier to download a PDF from network to
            temporary local storage (such as ``io.BytesIO``), manipulate it, and
            then re-upload it.
        """
        if isinstance(filename_or_stream, bytes) and filename_or_stream.startswith(
            b'%PDF-'
        ):
            warn(
                "It looks like you called with Pdf.open(data) with a bytes-like object "
                "containing a PDF. This will probably fail because this function "
                "expects a filename or opened file-like object. Instead, please use "
                "Pdf.open(BytesIO(data))."
            )

        tmp_stream, original_filename = None, False
        if allow_overwriting_input:
            try:
                Path(filename_or_stream)
            except TypeError as error:
                raise ValueError(
                    '"allow_overwriting_input=True" requires "open" first argument '
                    'to be a file path'
                ) from error
            original_filename = str(filename_or_stream)
            with open(original_filename, 'rb') as pdf_file:
                tmp_stream = BytesIO()
                shutil.copyfileobj(pdf_file, tmp_stream)
        pdf = Pdf._open(
            tmp_stream or filename_or_stream,
            password=password,
            hex_password=hex_password,
            ignore_xref_streams=ignore_xref_streams,
            suppress_warnings=suppress_warnings,
            attempt_recovery=attempt_recovery,
            inherit_page_attributes=inherit_page_attributes,
            access_mode=access_mode,
        )
        setattr(pdf, '_tmp_stream', tmp_stream)
        setattr(pdf, '_original_filename', original_filename)
        return pdf


@augments(_ObjectMapping)
class Extend_ObjectMapping:
    def get(self, key, default=None) -> Object:
        try:
            return self[key]
        except KeyError:
            return default

    def keys(self):
        return KeysView(self)

    def values(self):
        return (v for _k, v in self.items())


def check_is_box(obj) -> bool:
    try:
        if obj.is_rectangle:
            return True
    except AttributeError:
        pass

    try:
        pdfobj = Array(obj)
        if pdfobj.is_rectangle:
            return True
    except Exception:
        pass

    raise ValueError("object is not a rectangle")


@augments(Page)
class Extend_Page:
    @property
    def mediabox(self):
        return self._get_mediabox(True)

    @mediabox.setter
    def mediabox(self, value):
        check_is_box(value)
        self.obj['/MediaBox'] = value

    @property
    def cropbox(self):
        return self._get_cropbox(True)

    @cropbox.setter
    def cropbox(self, value):
        check_is_box(value)
        self.obj['/CropBox'] = value

    @property
    def trimbox(self):
        return self._get_trimbox(True)

    @trimbox.setter
    def trimbox(self, value):
        check_is_box(value)
        self.obj['/TrimBox'] = value

    @property
    def resources(self):
        return self.obj['/Resources']

    def add_resource(
        self,
        res: Object,
        res_type: Name,
        name: Optional[Name] = None,
        *,
        prefix: str = '',
        replace_existing: bool = True,
    ) -> str:
        """Adds a new resource to the page's Resources dictionary.

        If the Resources dictionaries do not exist, they will be created.

        Args:
            self: The object to add to the resources dictionary.
            res: The resource dictionary object to add.
            res_type: Should be one of the following Resource dictionary types:
                ExtGState, ColorSpace, Pattern, Shading, XObject, Font, Properties.
            name: The name of the object. If omitted, a random name will be
                generated with enough randomness to be globally unique.
            prefix: A prefix for the name of the object. Allows conveniently
                namespacing when using random names, e.g. prefix="Im" for images.
                Mutually exclusive with name parameter.
            replace_existing: If the name already exists in one of the resource
                dictionaries, remove it.
        Returns:
            The name of the object.

        Example:
            >>> resource_name = Page(pdf.pages[0]).add_resource(formxobj, Name.XObject)

        .. versionadded: 2.3
        """
        if not Name.Resources in self.obj:
            self.obj.Resources = Dictionary()
        elif not isinstance(self.obj.Resources, Dictionary):
            raise TypeError("Page /Resources exists but is not a dictionary")
        resources = self.obj.Resources

        if not res_type in resources:
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

        resources[res_type][name] = res
        return name

    def __repr__(self):
        return repr(self.obj).replace('Dictionary', 'Page', 1)

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
