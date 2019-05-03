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
from collections.abc import KeysView
from io import BytesIO
from subprocess import PIPE, run
from tempfile import NamedTemporaryFile

from . import Array, Dictionary, Name, Object, Pdf, Stream
from ._qpdf import _ObjectMapping
from .models import PdfMetadata

# pylint: disable=no-member,unsupported-membership-test,unsubscriptable-object


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
    """

    def class_augment(cls, cls_cpp=cls_cpp):
        for name, fn in inspect.getmembers(cls, inspect.isfunction):
            fn.__qualname__ = fn.__qualname__.replace(cls.__name__, cls_cpp.__name__)
            setattr(cls_cpp, name, fn)
        for name, fn in inspect.getmembers(cls, inspect.isdatadescriptor):
            setattr(cls_cpp, name, fn)

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
    def _repr_mimebundle_(self, **kwargs):
        """Present options to IPython for rich display of this object

        See https://ipython.readthedocs.io/en/stable/config/integrating.html#rich-display
        """

        include = kwargs['include']
        exclude = kwargs['exclude']
        include = set() if include else include
        exclude = set() if exclude is None else exclude

        data = {}
        if '/Type' not in self:
            return data

        if self.Type == '/Page':
            bundle = {'application/pdf', 'image/png'}
            if include:
                bundle = bundle & include
            bundle = bundle - exclude
            pagedata = _single_page_pdf(self)
            if 'application/pdf' in bundle:
                data['application/pdf'] = pagedata
            if 'image/png' in bundle:
                try:
                    data['image/png'] = _mudraw(pagedata, 'png')
                except (FileNotFoundError, RuntimeError):
                    pass
        return data

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

    def open_metadata(self, set_pikepdf_as_editor=True, update_docinfo=True):
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
                version of pikepdf is the most software to modify the metadata.
                Recommended, except for testing.

            update_docinfo (bool): Update the deprecated PDF DocumentInfo block
                to be consistent with XMP.

        Returns:
            pikepdf.models.PdfMetadata
        """
        return PdfMetadata(
            self, pikepdf_mark=set_pikepdf_as_editor, sync_docinfo=update_docinfo
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
        Close a Pdf object and release resources acquired by pikepdf

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

    def _attach(self, *, basename, filebytes, mime=None, desc=''):
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
