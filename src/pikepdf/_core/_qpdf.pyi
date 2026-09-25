# SPDX-FileCopyrightText: 2022 James R. Barlow
# SPDX-License-Identifier: MPL-2.0

# Type stubs for the bindings in src/core/qpdf.cpp.
# See pikepdf/_core/__init__.pyi for how this stub package is laid out.

# pylint: disable=no-method-argument,unused-argument,no-self-use,too-many-public-methods
# ruff: noqa: D418
# mypy: disable-error-code="misc"

from __future__ import annotations

from collections.abc import Callable, Iterable
from contextlib import AbstractContextManager
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any, BinaryIO, Literal, Self, overload

from pikepdf._core._acroform import AcroForm
from pikepdf._core._embeddedfiles import Attachments
from pikepdf._core._object import Object, _ObjectList
from pikepdf._core._object_construct import Dictionary, Stream
from pikepdf._core._page import Page
from pikepdf._core._qpdf_pagelist import PageList
from pikepdf._core._typing import Numeric, TObj

if TYPE_CHECKING:
    from pikepdf._page_copy import PageCopyResult
    from pikepdf.models.encryption import Encryption, EncryptionInfo, Permissions
    from pikepdf.models.metadata import PdfMetadata
    from pikepdf.models.outlines import Outline

class AccessMode(Enum):
    default: ...
    mmap: ...
    mmap_only: ...
    stream: ...

class EncryptionMethod(Enum):
    """PDF encryption methods.

    Describes which encryption method was used on a particular part of a
    PDF. These values are returned by :class:`pikepdf.EncryptionInfo` but
    are not currently used to specify how encryption is requested.
    """

    none: ...
    """Data was not encrypted."""
    unknown: ...
    """An unknown algorithm was used."""
    rc4: ...
    """The RC4 encryption algorithm was used (obsolete)."""
    aes: ...
    """The AES-based algorithm was used as described in the {{ pdfrm }}."""
    aesv3: ...
    """An improved version of the AES-based algorithm was used as described in the
        :doc:`Adobe Supplement to the ISO 32000 </references/resources>`, requiring
        PDF 1.7 extension level 3. This algorithm still uses AES, but allows both
        AES-128 and AES-256, and improves how the key is derived from the password."""

class ObjectStreamMode(Enum):
    """Options for saving object streams within PDFs.

    Object streams are more a compact
    way of saving certain types of data that was added in PDF 1.5. All
    modern PDF viewers support object streams, but some third party tools
    and libraries cannot read them.
    """

    disable: ...
    """Disable the use of object streams.

    If any object streams exist in the file, remove them when the file is saved.
    """
    generate: ...
    """Preserve any existing object streams in the original file.

    This is the default behavior.
    """
    preserve: ...
    """Generate object streams."""

class StreamDecodeLevel(Enum):
    """Options for decoding streams within PDFs."""

    none: ...
    """Do not attempt to apply any filters. Streams
        remain as they appear in the original file. Note that
        uncompressed streams may still be compressed on output. You can
        disable that by saving with ``.save(..., compress_streams=False)``."""
    generalized: ...
    """This is the default. libqpdf will apply
        LZWDecode, ASCII85Decode, ASCIIHexDecode, and FlateDecode
        filters on the input. When saved with
        ``compress_streams=True``, the default, the effect of this
        is that streams filtered with these older and less efficient
        filters will be recompressed with the Flate filter. As a
        special case, if a stream is already compressed with
        FlateDecode and ``compress_streams=True``, the original
        compressed data will be preserved."""
    specialized: ...
    """        In addition to uncompressing the generalized
        compression formats, supported non-lossy specialized
        compression will also be decoded. At present, this includes the
        RunLengthDecode filter."""
    all: ...
    """In addition to generalized and non-lossy
        specialized filters, supported lossy compression filters will
        be applied. At present, this includes DCTDecode (JPEG)
        compression. Note that compressing the resulting data with
        DCTDecode again will accumulate loss, so avoid multiple
        compression and decompression cycles. This is mostly useful for
        (low-level) retrieving image data; see :class:`pikepdf.PdfImage` for
        the preferred method."""

class JSONStreamData(Enum):
    """How stream data is represented when writing a PDF as qpdf JSON.

    Used by :meth:`pikepdf.Pdf.write_qpdf_json`.
    """

    none: ...
    """Stream data is omitted from the JSON output."""
    inline: ...
    """Stream data is included inline in the JSON, base64-encoded."""
    file: ...
    """Stream data is written to external files. Each stream is written to a
        file named ``{file_prefix}-{object_number}``, where ``file_prefix`` is
        the argument given to :meth:`pikepdf.Pdf.write_qpdf_json`."""

class XrefEntry:
    """Represents one entry in a PDF's cross-reference (xref) table.

    Returned by :meth:`pikepdf.Pdf.get_xref_table`. The meaning of the other
    properties depends on :attr:`type`.
    """

    @property
    def type(self) -> int:
        """The entry type: 0 = free, 1 = uncompressed, 2 = compressed.

        For type 1 (uncompressed), :attr:`offset` is meaningful. For type 2
        (compressed, i.e. stored in an object stream), :attr:`obj_stream_number`
        and :attr:`obj_stream_index` are meaningful.
        """

    @property
    def offset(self) -> int | None:
        """Byte offset of the object in the file, or None unless ``type == 1``."""

    @property
    def obj_stream_number(self) -> int | None:
        """Object number of the containing object stream; None unless ``type == 2``."""

    @property
    def obj_stream_index(self) -> int | None:
        """Index of the object within its object stream; None unless ``type == 2``."""

class Pdf:
    """In-memory representation of a PDF."""

    def _repr_mimebundle_(self, include: Any = ..., exclude: Any = ...) -> Any:
        """Present options to IPython or Jupyter for rich display of this object.

        See:
        https://ipython.readthedocs.io/en/stable/config/integrating.html#rich-display
        """
    def add_blank_page(self, *, page_size: tuple[Numeric, Numeric] = ...) -> Page:
        """Add a blank page to this PDF.

        If pages already exist, the page will be added to the end. Pages may be
        reordered using ``Pdf.pages``.

        The caller may add content to the page by modifying its objects after creating
        it.

        Args:
            page_size (tuple): The size of the page in PDF units (1/72 inch or 0.35mm).
                Default size is set to a US Letter 8.5" x 11" page.
        """
    def __enter__(self) -> Self: ...
    def __exit__(self, exc_type, exc_value, traceback) -> None: ...
    def __init__(self, *args, **kwargs) -> None: ...
    def _add_page(self, page: Object, first: bool = ...) -> None:
        """Low-level private method to attach a page to this PDF.

        The page can be either be a newly constructed PDF object or it can
        be obtained from another PDF.

        Args:
            page: The page object to attach.
            first: If True, prepend this before the first page;
                if False append after last page.
        """
    def _count_orphaned_widgets(self) -> int: ...
    def _decode_all_streams_and_discard(self, progress) -> None: ...
    def _process(self, arg0: str, arg1: bytes) -> None: ...
    def _replace_object(self, arg0: tuple[int, int], arg1: Object) -> None: ...
    def _swap_objects(self, arg0: tuple[int, int], arg1: tuple[int, int]) -> None: ...
    def check_pdf_syntax(
        self, progress: Callable[[int], None] | None = ...
    ) -> list[str]:
        """Check if PDF is syntactically well-formed.

        Similar to ``qpdf --check``, checks for syntax
        or structural problems in the PDF. This is mainly useful to PDF
        developers and may not be informative to the average user. PDFs with
        these problems still render correctly, if PDF viewers are capable of
        working around the issues they contain. In many cases, pikepdf can
        also fix the problems.

        Unlike ``qpdf --check``, this function does not check for linearization
        issues (see ``check_linearization()``) and some other issues. To
        replicate the exact behavior of qpdf's check in pikepdf, use
        ``pikepdf.Job(['pikepdf', '--check', 'input.pdf']).run()``.

        An example problem found by this function is a xref table that is
        missing an object reference. A page dictionary with the wrong type of
        key, such as a string instead of an array of integers for its mediabox,
        is not the sort of issue checked for. If this were an XML checker, it
        would tell you if the XML is well-formed, but could not tell you if
        the XML is valid XHTML or if it can be rendered as a usable web page.

        This function also attempts to decompress all streams in the PDF.
        If no JBIG2 decoder is available and JBIG2 images are presented,
        a warning will occur that JBIG2 cannot be checked.

        This function returns a list of strings describing the issues. The
        text is subject to change and should not be treated as a stable API.

        Args:
            progress: A function to call with progress updates, from 0 to 100.
                If None (default), no progress will be reported.

        Returns:
            Empty list if no issues were found. List of issues as text strings
            if issues were found.
        """
    def check_linearization(self, stream: object = ...) -> bool:
        """Reports information on the PDF's linearization.

        Args:
            stream: A stream to write this information too; must
                implement ``.write()`` and ``.flush()`` method. Defaults to
                :data:`sys.stderr`.

        Returns:
            ``True`` if the file is correctly linearized, and ``False`` if
            the file is linearized but the linearization data contains errors
            or was incorrectly generated.

        Raises:
            RuntimeError: If the PDF in question is not linearized at all.
        """
    def lock(self) -> AbstractContextManager[None]:
        """Context manager to hold the per-Pdf lock for compound operations.

        Under free-threaded Python, individual C++ method calls are
        automatically serialized, but multi-step Python operations (e.g.
        read-modify-write on the same dictionary) are not atomic.  Wrap
        such sequences in ``with pdf.lock():`` to prevent interleaving.

        On GIL-enabled builds this is a no-op.
        """
    def close(self) -> None:
        """Close a ``Pdf`` object and release resources acquired by pikepdf.

        If pikepdf opened the file handle it will close it (e.g. when opened with a file
        path). If the caller opened the file for pikepdf, the caller close the file.
        ``with`` blocks will call close when exit.

        pikepdf lazily loads data from PDFs, so some :class:`pikepdf.Object` may
        implicitly depend on the :class:`pikepdf.Pdf` being open. This is always the
        case for :class:`pikepdf.Stream` but can be true for any object. Do not close
        the `Pdf` object if you might still be accessing content from it.

        When an ``Object`` is copied from one ``Pdf`` to another, the ``Object`` is
        copied into the destination ``Pdf`` immediately, so after accessing all desired
        information from the source ``Pdf`` it may be closed.

        .. versionchanged:: 3.0
            In pikepdf 2.x, this function actually worked by resetting to a very short
            empty PDF. Code that relied on this quirk may not function correctly.
        """
    def copy_foreign(self, h: Object) -> Object:
        """Copy an ``Object`` from a foreign ``Pdf`` and return a copy.

        The object must be owned by a different ``Pdf`` from this one.

        If the object has previously been copied, return a reference to
        the existing copy, even if that copy has been modified in the meantime.

        If you want to copy a page from one PDF to another, use:
        ``pdf_b.pages[0] = pdf_a.pages[0]``. That interface accounts for the
        complexity of copying pages.

        This function is used to copy a :class:`pikepdf.Object` that is owned by
        some other ``Pdf`` into this one. This is performs a deep (recursive) copy
        and preserves all references that may exist in the foreign object. For
        example, if

            >>> object_a = pdf.copy_foreign(object_x)  # doctest: +SKIP
            >>> object_b = pdf.copy_foreign(object_y)  # doctest: +SKIP
            >>> object_c = pdf.copy_foreign(object_z)  # doctest: +SKIP

        and ``object_z`` is a shared descendant of both ``object_x`` and ``object_y``
        in the foreign PDF, then ``object_c`` is a shared descendant of both
        ``object_a`` and ``object_b`` in this PDF. If ``object_x`` and ``object_y``
        refer to the same object, then ``object_a`` and ``object_b`` are the
        same object.

        It also copies all :class:`pikepdf.Stream` objects. Since this may copy
        a large amount of data, it is not done implicitly. This function does
        not copy references to pages in the foreign PDF - it stops at page
        boundaries. Thus, if you use ``copy_foreign()`` on a table of contents
        (``/Outlines`` dictionary), you may have to update references to pages.

        Direct objects, including dictionaries, do not need ``copy_foreign()``.
        pikepdf will automatically convert and construct them.

        Note:
            pikepdf automatically treats incoming pages from a foreign PDF as
            foreign objects, so :attr:`Pdf.pages` does not require this treatment.

        See Also:
            `QPDF::copyForeignObject <https://qpdf.readthedocs.io/en/stable/design.html#copying-objects-from-other-pdf-files>`_

        .. versionchanged:: 2.1
            Error messages improved.
        """
    @overload
    def get_object(self, objgen: tuple[int, int]) -> Object: ...
    @overload
    def get_object(self, objgen: int, gen: int) -> Object: ...
    def get_object(
        self, objgen: tuple[int, int] | int, gen: int | None = None
    ) -> Object:
        """Retrieve an object from the PDF.

        Can be called with either a 2-tuple of (objid, gen) or
        two integers objid and gen.
        """
    def get_warnings(self) -> list: ...
    @overload
    def make_indirect(self, obj: TObj) -> TObj: ...
    def make_indirect(self, obj: Any) -> Object:
        """Attach an object to the Pdf as an indirect object.

        Direct objects appear inline in the binary encoding of the PDF.
        Indirect objects appear inline as references (in English, "look
        up object 4 generation 0") and then read from another location in
        the file. The PDF specification requires that certain objects
        are indirect - consult the PDF specification to confirm.

        Generally a resource that is shared should be attached as an
        indirect object. :class:`pikepdf.Stream` objects are always
        indirect, and creating them will automatically attach it to the
        Pdf.

        Args:
            obj: The object to attach. If this a :class:`pikepdf.Object`,
                it will be attached as an indirect object. If it is
                any other Python object, we attempt conversion to
                :class:`pikepdf.Object` attach the result. If the
                object is already an indirect object, a reference to
                the existing object is returned. If the ``pikepdf.Object``
                is owned by a different Pdf, an exception is raised; use
                :meth:`pikepdf.Object.copy_foreign` instead.

        Returns:
            The indirect object. An array, dictionary or stream is made
            indirect in place, so ``obj`` itself becomes that indirect object.
            A scalar such as a :class:`pikepdf.Name` is copied first, so
            ``obj`` stays direct and can still be hashed or reused in another
            Pdf; use the return value.

        .. versionchanged:: 10.14
            Scalars are copied rather than made indirect in place.

        See Also:
            :meth:`pikepdf.Object.is_indirect`
        """
    def make_stream(self, data: bytes, d=None, **kwargs) -> Stream:
        """Create a new pikepdf.Stream object that is attached to this PDF.

        See:
            :meth:`pikepdf.Stream.__new__`
        """
    @classmethod
    def new(
        cls, *, conversion_mode: Literal['implicit', 'explicit'] | None = None
    ) -> Pdf:
        """Create a new, empty PDF.

        This is best when you are constructing a PDF from scratch.

        In most cases, if you are working from an existing PDF, you should open the
        PDF using :meth:`pikepdf.Pdf.open` and transform it, instead of a creating
        a new one, to preserve metadata and structural information. For example,
        if you want to split a PDF into two parts, you should open the PDF and
        transform it into the desired parts, rather than creating a new PDF and
        copying pages into it.
        """
    @staticmethod
    def open(
        filename_or_stream: Path | str | BinaryIO,
        *,
        password: str | bytes = '',
        hex_password: bool = False,
        ignore_xref_streams: bool = False,
        suppress_warnings: bool = True,
        attempt_recovery: bool = True,
        inherit_page_attributes: bool = True,
        access_mode: AccessMode = AccessMode.default,
        allow_overwriting_input: bool = False,
        conversion_mode: Literal['implicit', 'explicit'] | None = None,
    ) -> Pdf:
        """Open an existing file at *filename_or_stream*.

        If *filename_or_stream* is path-like, the file will be opened for reading. The
        file should not be modified by another process while it is open in pikepdf, or
        undefined behavior may occur. This is because the file may be lazily loaded.
        When ``.close()`` is called, the file handle that pikepdf opened will be closed.

        If *filename_or_stream* is stream, the data will be accessed as a readable
        binary stream, from the current position in that stream.  When ``pdf =
        Pdf.open(stream)`` is called on a stream, pikepdf will not call
        ``stream.close()``; the caller must call both ``pdf.close()`` and
        ``stream.close()``, in that order, when the Pdf and stream are no longer needed.
        Use with-blocks will call ``.close()`` automatically.

        Whether a file or stream is opened, you must ensure that the data is not
        modified by another thread or process, or undefined behavior will occur. You
        also may not overwrite the input file using ``.save()``, unless
        ``allow_overwriting_input=True``. This is because data may be lazily loaded.

        If you intend to edit the file in place, or want to protect the file against
        modification by another process, use ``allow_overwriting_input=True``. This
        tells pikepdf to make a private copy of the file.

        Any changes to the file must be persisted by using ``.save()``.

        Examples:
            >>> with Pdf.open("test.pdf") as pdf:  # doctest: +SKIP
            ...     pass

            >>> pdf = Pdf.open("test.pdf", password="rosebud")  # doctest: +SKIP

        Args:
            filename_or_stream: Filename or Python readable and seekable file
                stream of PDF to open.
            password: User or owner password to open an
                encrypted PDF. If the type of this parameter is ``str`` it will be
                encoded as UTF-8. If the type is ``bytes`` it will be saved verbatim.
                Passwords are always padded or truncated to 32 bytes internally. Use
                ASCII passwords for maximum compatibility.
            hex_password: If True, interpret the password as a
                hex-encoded version of the exact encryption key to use, without
                performing the normal key computation. Useful in forensics.
            ignore_xref_streams: If True, ignore cross-reference
                streams. See qpdf documentation.
            suppress_warnings: If True (default), warnings are not
                printed to stderr. Use :meth:`pikepdf.Pdf.get_warnings()` to retrieve
                warnings.
            attempt_recovery: If True (default), attempt to recover
                from PDF parsing errors.
            inherit_page_attributes: If True (the default), push attributes
                that are set on a group of pages in the ``/Pages`` tree
                (``/MediaBox``, ``/CropBox``, ``/Resources`` and ``/Rotate``)
                down onto each individual page, so that every page carries its
                own copy. This simplifies most PDF work, since these attributes
                can then be read directly from a page. If False, pikepdf leaves
                the page tree as stored and does not push inherited attributes
                down, so a page may lack these keys on its own dictionary; in
                that case use the managed accessors
                (:attr:`~pikepdf.Page.mediabox`, :attr:`~pikepdf.Page.rotation`,
                etc.), which resolve inheritance, rather than raw access, which
                may find the key absent. Disable this when you need to inspect or
                construct the page tree exactly as stored -- for example, when
                building a test fixture that exercises attribute inheritance.
            access_mode: If ``.default``, pikepdf will
                decide how to access the file. Currently, it will always selected stream
                access. To attempt memory mapping and fallback to stream if memory
                mapping failed, use ``.mmap``.  Use ``.mmap_only`` to require memory
                mapping or fail (this is expected to only be useful for testing).
                Applications should be prepared to handle the SIGBUS signal on POSIX in
                the event that the file is successfully mapped but later goes away.
            allow_overwriting_input: If True, allows calling ``.save()``
                to overwrite the input file. This is performed by loading the entire
                input file into memory at open time; this will use more memory and may
                recent performance especially when the opened file will not be modified.
            conversion_mode: If given, sets this document's object conversion
                mode to ``'implicit'`` or ``'explicit'``, overriding the global
                setting for objects owned by this ``Pdf``. See
                :attr:`pikepdf.Pdf.conversion_mode`.

                .. versionadded:: 10.14

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
            network, pikepdf assumes that the stream using buffering and read caches to
            achieve reasonable performance. Streams that fetch data over a network in
            response to every read or seek request, no matter how small, will perform
            poorly. It may be easier to download a PDF from network to temporary local
            storage (such as ``io.BytesIO``), manipulate it, and then re-upload it.

        .. versionchanged:: 3.0
            Keyword arguments now mandatory for everything except the first
            argument.
        """
    def open_metadata(
        self,
        set_pikepdf_as_editor: bool = True,
        update_docinfo: bool = True,
        strict: bool = False,
    ) -> PdfMetadata:
        """Open the PDF's XMP metadata for editing.

        There is no ``.close()`` function on the metadata object, since this is
        intended to be used inside a ``with`` block only.

        For historical reasons, certain parts of PDF metadata are stored in
        two different locations and formats. This feature coordinates edits so
        that both types of metadata are updated consistently and "atomically"
        (assuming single threaded access). It operates on the ``Pdf`` in memory,
        not any file on disk. To persist metadata changes, you must still use
        ``Pdf.save()``.

        Example:
            >>> pdf = pikepdf.Pdf.open("../tests/resources/graph.pdf")
            >>> with pdf.open_metadata() as meta:
            ...     meta['dc:title'] = 'Set the Dublic Core Title'
            ...     meta['dc:description'] = 'Put the Abstract here'

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
    def open_outline(self, max_depth: int = 15, strict: bool = False) -> Outline:
        """Open the PDF outline ("bookmarks") for editing.

        Recommend for use in a ``with`` block. Changes are committed to the
        PDF when the block exits. (The ``Pdf`` must still be opened.)

        Example:
            >>> pdf = pikepdf.open('../tests/resources/outlines.pdf')
            >>> with pdf.open_outline() as outline:
            ...     outline.root.insert(0, pikepdf.OutlineItem('Intro', 0))

        Args:
            max_depth: Maximum recursion depth of the outline to be
                imported and re-written to the document. ``0`` means only
                considering the root level, ``1`` the first-level
                sub-outline of each root element, and so on. Items beyond
                this depth will be silently ignored. Default is ``15``.
            strict: When ``False`` (the default), pikepdf quietly corrects
                minor structural problems in the outline where the correct
                repair is known, recovering the valid parts of the document
                outline without raising an exception. For example, a missing
                required ``/Title`` is treated as an empty string; a structural
                error such as a reference loop cancels processing of further
                nodes on that level; and outline objects that have been
                accidentally duplicated are reproduced as new objects. When set
                to ``True``, any such structural problem raises an
                ``OutlineStructureError``.
        """
    def remove_unreferenced_resources(self) -> None:
        """Remove from /Resources any object not referenced in page's contents.

        PDF pages may share resource dictionaries with other pages. If
        pikepdf is used for page splitting, pages may reference resources
        in their /Resources dictionary that are not actually required.
        This purges all unnecessary resource entries.

        For clarity, if all references to any type of object are removed, that
        object will be excluded from the output PDF on save. (Conversely, only
        objects that are discoverable from the PDF's root object are included.)
        This function removes objects that are referenced from the page /Resources
        dictionary, but never called for in the content stream, making them
        unnecessary.

        Suggested before saving, if content streams or /Resources dictionaries
        are edited.
        """
    def save(
        self,
        filename_or_stream: Path | str | BinaryIO | None = None,
        *,
        preserve_pdfa: bool = True,
        min_version: str | tuple[str, int] = '',
        force_version: str | tuple[str, int] = '',
        fix_metadata_version: bool = True,
        compress_streams: bool = True,
        stream_decode_level: StreamDecodeLevel | None = None,
        object_stream_mode: ObjectStreamMode = ObjectStreamMode.preserve,
        normalize_content: bool = False,
        linearize: bool = False,
        qdf: bool = False,
        progress: Callable[[int], None] | None = None,
        encryption: Encryption | bool | None = None,
        recompress_flate: bool = False,
        deterministic_id: bool = False,
        static_id: bool = False,
    ) -> None:
        """Save all modifications to this :class:`pikepdf.Pdf`.

        Args:
            filename_or_stream: Where to write the output. If a file
                exists in this location it will be overwritten.
                If the file was opened with ``allow_overwriting_input=True``,
                then it is permitted to overwrite the original file, and
                this parameter may be omitted to implicitly use the original
                filename. Otherwise, the filename may not be the same as the
                input file, as overwriting the input file would corrupt data
                since pikepdf using lazy loading.

            preserve_pdfa: Ensures that the file is generated in a
                manner compliant with PDF/A and other stricter variants.
                This should be True, the default, in most cases.

            min_version: Sets the minimum version of PDF
                specification that should be required. If left alone qpdf
                will decide. If a tuple, the second element is an integer, the
                extension level. If the version number is not a valid format,
                qpdf will decide what to do.
            force_version: Override the version recommend by qpdf,
                potentially creating an invalid file that does not display
                in old versions. See qpdf manual for details. If a tuple, the
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
                uncompressed stream objects. By default this is set to
                ``True``, and the only reason to set it to ``False`` is for
                debugging or inspecting PDF contents.

                When enabled, uncompressed stream objects will be compressed
                whether they were uncompressed in the PDF when it was opened,
                or when the user creates new :class:`pikepdf.Stream` objects
                attached to the PDF. Stream objects can also be created
                indirectly, such as when content from another PDF is merged
                into the one being saved.

                Only stream objects that have no compression will be
                compressed when this object is set. If the object is
                compressed, compression will be preserved.

                Setting compress_streams=False does not trigger decompression
                unless decompression is specifically requested by setting
                both ``compress_streams=False`` and ``stream_decode_level``
                to the desired decode level (e.g. ``.generalized`` will
                decompress most non-image content).

                This option does not trigger recompression of existing
                compressed streams. For that, use ``recompress_flate``.

                The XMP metadata stream object, if present, is never
                compressed, to facilitate metadata reading by parsers that
                don't understand the full structure of PDF.

            stream_decode_level: Specifies how
                to encode stream objects. See documentation for
                :class:`pikepdf.StreamDecodeLevel`.

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
                mode in qpdf to allow editing of PDFs in a text editor. Use
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

            deterministic_id: Compute the document ``/ID`` from a digest of
                the output file's contents and ``/Info`` strings, without the
                current time. Saving the same document the same way produces
                the same ``/ID`` (and, with the same qpdf version, the same
                bytes), which is useful for reproducible builds and for caching
                or deduplicating output without depending on the clock.
                Documents with different content still receive different
                ``/ID`` values, so this is safe for production use. At a small
                runtime cost. Cannot be combined with encryption. Different
                qpdf versions may produce slightly different output, and hence
                different ``/ID`` values, for the same input.

            static_id: Set the document ``/ID`` to a fixed dummy value that is
                identical in every PDF that pikepdf writes.

                .. warning::

                    For testing and debugging only. **Never use in
                    production.** The PDF specification expects ``/ID`` to
                    identify a document uniquely; with ``static_id`` every
                    document shares the same ``/ID``, which can confuse
                    software that uses it to track, cache or match documents.
                    For reproducible production output, use
                    ``deterministic_id`` instead.

                A typical use is a test suite that compares saved PDFs
                byte-for-byte. Takes precedence over ``deterministic_id``.

        When neither ``deterministic_id`` nor ``static_id`` is set, the
        ``/ID`` is generated the conventional way described in the PDF
        specification: a hash that incorporates the current time, so every
        save produces a new value. In all three modes, if the document already
        has an ``/ID``, its first element is preserved (as the specification
        requires) and only the second element is replaced.

        Raises:
            PdfError
            ForeignObjectError
            ValueError

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

        .. note::
            If filename_or_stream is a stream and the process is interrupted during
            writing, the stream may be left in a corrupt state. It is the
            responsibility of the caller to manage the stream in this case.

        .. versionchanged:: 2.7
            Added *recompress_flate*.

        .. versionchanged:: 3.0
            Keyword arguments now mandatory for everything except the first
            argument.

        .. versionchanged:: 8.1
            If filename_or_stream is a filename and that file exists, the new file
            is written to a temporary file in the same directory and then moved into
            place. This prevents the existing destination file from being corrupted
            if the process is interrupted during writing; previously, corrupting the
            destination file was possible. If no file exists at the destination, output
            is written directly to the destination, but the destination will be deleted
            if errors occur during writing. Prior to 8.1, the file was always written
            directly to the destination, which could result in a corrupt destination
            file if the process was interrupted during writing.

        .. versionchanged:: 9.1
            When opened with ``allow_overwriting_input=True``, we now attempt to
            restore the original file permissions, ownership and creation time.
            The modified time is always set to the time of saving. An unusual
            umask or other settings changes still cause a failure to restore
            permissions.
        """
    def add_pages_from(
        self,
        src: Pdf,
        pages: Iterable[int] | range | slice | None = None,
        *,
        forms: Literal['preserve', 'strip'] = 'preserve',
    ) -> PageCopyResult:
        """Append pages from another ``Pdf``, preserving interactive form fields.

        Unlike ``pdf.pages.extend(src.pages)``, this carries the document's
        AcroForm form fields so they remain functional in Adobe Acrobat. Fields
        whose fully-qualified names collide with existing fields are
        automatically renamed; the mapping is available on the returned
        :class:`pikepdf.PageCopyResult`. The original→new name mapping in
        ``renamed_fields`` is best-effort (it pairs source and destination
        page fields positionally).

        Independent top-level fields are only carried over when a widget is on a
        copied page, so unrelated forms on separate pages are not imported.
        However, a field sharing a top-level ancestor with a copied field is
        carried as an entire subtree; such partially-represented fields are
        listed in the result's ``partial_fields``. Use ``forms='strip'`` for a
        hard guarantee of no form data.

        Args:
            src: Source ``Pdf`` to copy pages from.
            pages: Zero-based indices (iterable, ``range``, or ``slice``) of
                pages in ``src`` to copy. ``None`` copies all pages.
                A ``slice`` is clamped to the document length; explicit indices
                (including ``range``) must be valid or ``IndexError`` is raised.
            forms: ``'preserve'`` (default) carries AcroForm fields along with
                the pages; ``'strip'`` removes widget annotations from the
                copied pages so no form data is imported.

        Returns:
            A :class:`pikepdf.PageCopyResult` describing the operation,
            including which fields were added and any automatic renames.
        """
    def show_xref_table(self) -> None:
        """Pretty-print the Pdf's xref (cross-reference table).

        The xref table will be written to the `pikepdf._core` module's logger
        with a logging level of ``logging.INFO``. You may need to adjust the
        logging level to see the output.

        This function is mainly for debugging or curiosity. In practice, pikepdf
        does not trust the xref table; it instead reads the PDF to determine
        the position of objects, and recalculates the xref table when a PDF is
        saved. One could use to locate objects within a PDF using a hex editor,
        assuming the PDF is well-formed.
        """
    def get_xref_table(self) -> dict[tuple[int, int], XrefEntry]:
        """Return the Pdf's cross-reference (xref) table.

        Returns a mapping from ``(object_number, generation)`` to an
        :class:`pikepdf.XrefEntry` describing where that object is stored. Unlike
        :meth:`show_xref_table`, which only prints the table, this returns it as
        structured data suitable for forensic or investigatory purposes.

        As with :meth:`show_xref_table`, pikepdf recalculates the xref table when
        saving, so this reflects the table as read from the input file.

        .. versionadded:: 10.9
        """
    def fix_dangling_references(self, force: bool = ...) -> None:
        """Remove or repair references to objects that do not exist.

        A dangling reference is an indirect reference to an object that is not
        present in the file; per the PDF specification these resolve to null.
        Calling this method replaces such references so that the document's
        object structure is internally consistent.

        Args:
            force: Normally this is a no-op if qpdf believes the references are
                already consistent. Pass True to force the check to run.

        .. versionadded:: 10.9
        """
    def write_qpdf_json(
        self,
        filename_or_stream: Path | str | BinaryIO,
        *,
        decode_level: StreamDecodeLevel = ...,
        json_stream_data: JSONStreamData = ...,
        file_prefix: str = ...,
    ) -> None:
        """Write this PDF as qpdf JSON (the ``qpdf --json-output`` format, v2).

        This is the whole-document JSON serialization, distinct from
        :meth:`pikepdf.Object.to_json` which serializes a single object. The
        output can be read back with :meth:`from_qpdf_json`.

        Args:
            filename_or_stream: A filename or writable binary stream.
            decode_level: How much to decode (uncompress) stream data in the
                JSON. Use :attr:`StreamDecodeLevel.none` to preserve stream data
                exactly.
            json_stream_data: How stream data is represented; see
                :class:`pikepdf.JSONStreamData`.
            file_prefix: Required when ``json_stream_data`` is
                :attr:`JSONStreamData.file`; each stream is written to a file
                named ``{file_prefix}-{object_number}``. If not given and a
                filename was supplied, the filename is used as the prefix.

        .. versionadded:: 10.9
        """
    @staticmethod
    def from_qpdf_json(filename_or_stream: Path | str | BinaryIO) -> Pdf:
        """Create a new Pdf from qpdf JSON, as written by :meth:`write_qpdf_json`.

        The JSON must be a complete representation of a PDF (``qpdf
        --json-output`` version 2 or higher). To merge JSON into an existing Pdf,
        use :meth:`update_from_qpdf_json` instead.

        Args:
            filename_or_stream: A filename or readable binary stream containing
                qpdf JSON.

        .. versionadded:: 10.9
        """
    def update_from_qpdf_json(self, filename_or_stream: Path | str | BinaryIO) -> None:
        """Update this Pdf from qpdf JSON, as written by :meth:`write_qpdf_json`.

        Objects present in this Pdf but absent from the JSON are left unchanged.
        See :meth:`from_qpdf_json` to create a new Pdf instead.

        Args:
            filename_or_stream: A filename or readable binary stream containing
                qpdf JSON.

        .. versionadded:: 10.9
        """
    @property
    def Root(self) -> Object: ...
    @property
    def _allow_accessibility(self) -> bool: ...
    @property
    def _allow_extract(self) -> bool: ...
    @property
    def _allow_modify_annotation(self) -> bool: ...
    @property
    def _allow_modify_assembly(self) -> bool: ...
    @property
    def _allow_modify_form(self) -> bool: ...
    @property
    def _allow_modify_other(self) -> bool: ...
    @property
    def _allow_print_highres(self) -> bool: ...
    @property
    def _allow_print_lowres(self) -> bool: ...
    @property
    def _encryption_data(self) -> dict: ...
    @property
    def allow(self) -> Permissions:
        """Report permissions associated with this PDF.

        By default these permissions will be replicated when the PDF is
        saved. Permissions may also only be changed when a PDF is being saved,
        and are only available for encrypted PDFs. If a PDF is not encrypted,
        all operations are reported as allowed.

        pikepdf has no way of enforcing permissions.
        """
    @property
    def docinfo(self) -> Dictionary:
        """Access the (deprecated) document information dictionary.

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
        and dictionary does not exist or the wrong object type exists at that
        location. (This is to ensure that convenient code
        like ``pdf.docinfo[Name.Title] = "Title"`` will work when the dictionary
        does not exist at all.) This dictionary is always indirect.

        You can delete the document information dictionary by deleting this property,
        ``del pdf.docinfo``. Note that accessing the property after deleting it
        will re-create with a new, empty dictionary.

        .. versionchanged:: 2.4
            Added support for ``del pdf.docinfo``.
        """
    @docinfo.setter
    def docinfo(self, val: Dictionary) -> None: ...
    @property
    def encryption(self) -> EncryptionInfo:
        """Report encryption information for this PDF.

        Encryption settings may only be changed when a PDF is saved.
        """
    @property
    def extension_level(self) -> int:
        """Returns the extension level of this PDF.

        If a developer has released multiple extensions of a PDF version against
        the same base version value, they shall increase the extension level
        by 1. To be interpreted with :attr:`pdf_version`.
        """
    conversion_mode: Literal['implicit', 'explicit'] | None
    """Object conversion mode for this PDF: 'implicit', 'explicit' or None.

    When set, this overrides the global mode set by
    :func:`pikepdf.set_object_conversion_mode` for objects owned by this
    ``Pdf``, in every thread. ``None`` (the default) means defer to the global
    setting. The :func:`pikepdf.explicit_conversion` and
    :func:`pikepdf.implicit_conversion` context managers take precedence over
    this setting in the thread where they are active.

    Objects copied into another ``Pdf`` take on that document's mode.
    Unowned objects, such as a bare ``pikepdf.Dictionary(...)``, are not
    attached to any document, so they follow the thread-local or global
    setting instead.

    .. versionadded:: 10.14
    """

    @property
    def filename(self) -> str:
        """The source filename of an existing PDF, when available.

        When the Pdf was created from scratch, this returns 'empty PDF'.
        When the Pdf was created from a stream, the return value is the
        word 'stream' followed by some information about the stream, if
        available.
        """
    @property
    def is_encrypted(self) -> bool:
        """Returns True if the PDF is encrypted.

        For information about the nature of the encryption, see
        :attr:`Pdf.encryption`.
        """
    @property
    def is_linearized(self) -> bool:
        """Returns True if the PDF is linearized.

        Specifically returns True iff the file starts with a linearization
        parameter dictionary.  Does no additional validation.
        """
    @property
    def objects(self) -> _ObjectList:
        """Return an iterable list of all objects in the PDF.

        After deleting content from a PDF such as pages, objects related
        to that page, such as images on the page, may still be present in
        this list.
        """
    @property
    def pages(self) -> PageList:
        """Returns the list of pages."""
    @property
    def pdf_version(self) -> str:
        """The version of the PDF specification used for this file, such as '1.7'.

        More precise information about the PDF version can be opened from the
        Pdf's XMP metadata.
        """
    @property
    def root(self) -> Object:
        """The /Root object of the PDF."""
    @property
    def trailer(self) -> Object:
        """Provides access to the PDF trailer object.

        See {{ pdfrm }} section 7.5.5. Generally speaking,
        the trailer should not be modified with pikepdf, and modifying it
        may not work. Some of the values in the trailer are automatically
        changed when a file is saved.
        """
    @property
    def user_password_matched(self) -> bool:
        """Returns True if the user password matched when the ``Pdf`` was opened.

        It is possible for both the user and owner passwords to match.

        .. versionadded:: 2.10
        """
    @property
    def owner_password_matched(self) -> bool:
        """Returns True if the owner password matched when the ``Pdf`` was opened.

        It is possible for both the user and owner passwords to match.

        .. versionadded:: 2.10
        """
    def generate_appearance_streams(self) -> None:
        """Generates appearance streams for AcroForm forms and form fields.

        Appearance streams describe exactly how annotations and form fields
        should appear to the user. If omitted, the PDF viewer is free to
        render the annotations and form fields according to its own settings,
        as needed.

        For every form field in the document, this generates appearance
        streams, subject to the limitations of qpdf's ability to create
        appearance streams.

        When invoked, this method will modify the ``Pdf`` in memory. It may be
        best to do this after the ``Pdf`` is opened, or before it is saved,
        because it may modify objects that the user does not expect to be
        modified.

        If ``Pdf.Root.AcroForm.NeedAppearances`` is ``False`` or not present, no
        action is taken (because no appearance streams need to be generated).
        If ``True``, the appearance streams are generated, and the NeedAppearances
        flag is set to ``False``.

        See:
            https://github.com/qpdf/qpdf/blob/bf6b9ba1c681a6fac6d585c6262fb2778d4bb9d2/include/qpdf/QPDFFormFieldObjectHelper.hh#L216

        .. versionadded:: 2.11
        """
    def flatten_annotations(self, mode: str) -> None:
        """Flattens all PDF annotations into regular PDF content.

        Annotations are markup such as review comments, highlights, proofreading
        marks. User data entered into interactive form fields also counts as an
        annotation.

        When annotations are flattened, they are "burned into" the regular
        content stream of the document and the fact that they were once annotations
        is deleted. This can be useful when preparing a document for printing,
        to ensure annotations are printed, or to finalize a form that should
        no longer be changed.

        Args:
            mode: One of the strings ``'all'``, ``'screen'``, ``'print'``. If
                omitted or  set to empty, treated as ``'all'``. ``'screen'``
                flattens all except those marked with the PDF flag /NoView.
                ``'print'`` flattens only those marked for printing.
                Default is ``'all'``.

        .. versionadded:: 2.11
        """
    @property
    def acroform(self) -> AcroForm:
        """Returns a helper object for working with interactive forms.

        .. tip::

            This creates a new AcroForm helper object each time this property is
            used. If you're planning on doing multiple form-related operations,
            keep a reference to this object. The helper has an internal cache
            that can speed up certain operations.
        """
    @property
    def attachments(self) -> Attachments:
        """Returns a mapping that provides access to all files attached to this PDF.

        PDF supports attaching (or embedding, if you prefer) any other type of file,
        including other PDFs. This property provides read and write access to
        these objects by filename.
        """
