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
from collections import namedtuple
from collections.abc import KeysView
from io import BytesIO
from subprocess import PIPE, run
from tempfile import NamedTemporaryFile

from . import Array, Dictionary, Name, Object, Page, Pdf, Stream
from ._qpdf import PdfError, StreamParser, Token, _ObjectMapping
from .models import EncryptionInfo, PdfMetadata, Permissions

# pylint: disable=no-member,unsupported-membership-test,unsubscriptable-object

__all__ = []


def augments(cls_cpp):
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

    Any existing methods may be used, regardless of whether they defined
    elsewhere in the support class or in the target class.

    The target class does not have to be C++ or derived from pybind11.

    THIS DOES NOT work for static methods or class methods. pybind11 does not seem
    to support this sort of runtime modification.
    """

    def class_augment(cls, cls_cpp=cls_cpp):
        for name, member in inspect.getmembers(cls):
            if inspect.isfunction(member):
                member.__qualname__ = member.__qualname__.replace(
                    cls.__name__, cls_cpp.__name__
                )
                setattr(cls_cpp, name, member)
            elif inspect.isdatadescriptor(member):
                setattr(cls_cpp, name, member)

        def block_init(self):
            # Prevent initialization of the support class
            raise NotImplementedError(self.__class__.__name__ + '.__init__')

        cls.__init__ = block_init
        return cls

    return class_augment


def _single_page_pdf(page):
    """Construct a single page PDF from the provided page in memory"""
    pdf = Pdf.new()
    pdf.pages.append(page)
    bio = BytesIO()
    pdf.save(bio)
    bio.seek(0)
    return bio.read()


def _mudraw(buffer, fmt):
    """Use mupdf draw to rasterize the PDF in the memory buffer"""
    with NamedTemporaryFile(suffix='.pdf') as tmp_in:
        tmp_in.write(buffer)
        tmp_in.seek(0)
        tmp_in.flush()

        proc = run(
            ['mudraw', '-F', fmt, '-o', '-', tmp_in.name], stdout=PIPE, stderr=PIPE
        )
        if proc.stderr:
            raise RuntimeError(proc.stderr.decode())
        return proc.stdout


@augments(Object)
class Extend_Object:
    def _repr_mimebundle_(self, include, exclude, **kwargs):
        """Present options to IPython for rich display of this object

        See https://ipython.readthedocs.io/en/stable/config/integrating.html#rich-display
        """

        if (
            isinstance(self, Dictionary)
            and Name.Type in self
            and self.Type == Name.Page
        ):
            return Page(self)._repr_mimebundle_(include, exclude, **kwargs)
        return None

    def _ipython_key_completions_(self):
        if isinstance(self, Dictionary):
            return self.keys()
        elif isinstance(self, Stream):
            return self.stream_dict.keys()
        return None

    def emplace(self, other):
        """Copy all items from other without making a new object.

        Particularly when working with pages, it may be desirable to remove all
        of the existing page's contents and emplace (insert) a new page on top
        of it, in a way that preserves all links and references to the original
        page. (Or similarly, for other Dictionary objects in a PDF.)

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
        """
        del_keys = set(self.keys()) - set(other.keys())
        for k in other.keys():
            self[k] = other[k]  # pylint: disable=unsupported-assignment-operation
        for k in del_keys:
            del self[k]  # pylint: disable=unsupported-delete-operation

    def write(self, data, *, filter=None, decode_parms=None, type_check=True):
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
            data (bytes): the new data to use for replacement
            filter (pikepdf.Name or pikepdf.Array): The filter(s) with which the
                data is (already) encoded
            decode_parms (pikepdf.Dictionary or pikepdf.Array): Parameters for the
                filters with which the object is encode
            type_check (bool): Check arguments; use False only if you want to
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
                        (
                            "filter ({}) and decode_parms ({}) must be arrays of "
                            " same length"
                        ).format(repr(filter), repr(decode_parms))
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
    def _repr_mimebundle_(self, **_kwargs):
        """
        Present options to IPython or Jupyter for rich display of this object

        See https://ipython.readthedocs.io/en/stable/config/integrating.html#rich-display
        """

        bio = BytesIO()
        self.save(bio)
        bio.seek(0)

        data = {'application/pdf': bio.read()}
        return data

    def open_metadata(
        self, set_pikepdf_as_editor=True, update_docinfo=True, strict=False
    ):
        """
        Open the PDF's XMP metadata for editing

        Recommend for use in a ``with`` block. Changes are committed to the
        PDF when the block exits. (The ``Pdf`` must still be opened.)

        Example:
            >>> with pdf.open_metadata() as meta:
                    meta['dc:title'] = 'Set the Dublic Core Title'
                    meta['dc:description'] = 'Put the Abstract here'

        Args:
            set_pikepdf_as_editor (bool): Update the metadata to show that this
                version of pikepdf is the most recent software to modify the metadata.
                Recommended, except for testing.

            update_docinfo (bool): Update the standard fields of DocumentInfo
                (the old PDF metadata dictionary) to match the corresponding
                XMP fields. The mapping is described in
                :attr:`PdfMetadata.DOCINFO_MAPPING`. Nonstandard DocumentInfo
                fields and XMP metadata fields with no DocumentInfo equivalent
                are ignored.

            strict (bool): If ``False`` (the default), we aggressively attempt
                to recover from any parse errors in XMP, and if that fails we
                overwrite the XMP with an empty XMP record.  If ``True``, raise
                errors when either metadata bytes are not valid and well-formed
                XMP (and thus, XML). Some trivial cases that are equivalent to
                empty or incomplete "XMP skeletons" are never treated as errors,
                and always replaced with a proper empty XMP block. Certain
                errors may be logged.

        Returns:
            pikepdf.models.PdfMetadata
        """
        return PdfMetadata(
            self,
            pikepdf_mark=set_pikepdf_as_editor,
            sync_docinfo=update_docinfo,
            overwrite_invalid_xml=not strict,
        )

    def make_stream(self, data):
        """
        Create a new pikepdf.Stream object that is attached to this PDF.

        Args:
            data (bytes): Binary data for the stream object
        """
        return Stream(self, data)

    def add_blank_page(self, *, page_size=(612, 792)):
        """
        Add a blank page to this PD. If pages already exist, the page will be added to
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

    def close(self):
        """
        Close a Pdf object and release resources acquired by pikepdf.

        If pikepdf opened the file handle it will close it (e.g. when opened with a file
        path). If the caller opened the file for pikepdf, the caller close the file.

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

        # Can use QPDF::closeInputSource() but that requires libqpdf 9.0.0

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

        if self.filename:
            description = "closed file: " + self.filename
        else:
            description = "closed object"
        self._process(description, EMPTY_PDF)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()

    @property
    def allow(self):
        """
        Report permissions associated with this PDF.

        By default these permissions will be replicated when the PDF is
        saved. Permissions may also only be changed when a PDF is being saved,
        and are only available for encrypted PDFs. If a PDF is not encrypted,
        all operations are reported as allowed.

        pikepdf has no way of enforcing permissions.

        Returns:
            pikepdf.models.Permissions
        """
        results = {}
        for field in Permissions.fields():
            results[field] = getattr(self, '_allow_' + field)
        return Permissions(**results)

    @property
    def encryption(self):
        """
        Report encryption information for this PDF.

        Encryption settings may only be changed when a PDF is saved.

        Returns: pikepdf.models.EncryptionInfo
        """
        return EncryptionInfo(self._encryption_data)

    def check(self):
        """
        Check if PDF is well-formed.  Similar to ``qpdf --check``.

        Returns:
            list of strings describing errors of warnings in the PDF
        """

        class DiscardingParser(StreamParser):
            def __init__(self):  # pylint: disable=useless-super-delegation
                super().__init__()  # required for C++

            def handle_object(self, obj):
                pass

            def handle_eof(self):
                pass

        problems = []

        try:
            self._decode_all_streams_and_discard()
        except PdfError as e:
            problems.append(str(e))

        discarding_parser = DiscardingParser()

        for basic_page in self.pages:
            page = Page(basic_page)
            try:
                page.parse_contents(discarding_parser)
            except PdfError as e:
                problems.append(str(e))

        for warning in self.get_warnings():
            problems.append("WARNING: " + warning)

        return problems

    def _attach(self, *, basename, filebytes, mime=None, desc=''):  # pragma: no cover
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


@augments(_ObjectMapping)
class Extend_ObjectMapping:
    def __contains__(self, key):
        try:
            self[key]
        except KeyError:
            return False
        else:
            return True

    def get(self, key, default=None):
        try:
            return self[key]
        except KeyError:
            return default

    def keys(self):
        return KeysView(self)

    def values(self):
        return (v for _k, v in self.items())


def check_is_box(obj):
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

    def __repr__(self):
        return repr(self.obj).replace('Dictionary', 'Page')

    def _repr_mimebundle_(self, include, exclude, **kwargs):
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
        return 'pikepdf.Token({}, {})'.format(self.type_, self.raw_value)
