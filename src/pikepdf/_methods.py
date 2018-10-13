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

from tempfile import NamedTemporaryFile
from subprocess import run, PIPE
from io import BytesIO
from functools import wraps

from collections.abc import KeysView

import inspect

from . import Pdf, Dictionary, Array, Name, Stream, Object
from ._qpdf import _ObjectMapping


# pylint: disable=no-member,unsupported-membership-test,unsubscriptable-object

def extends(cls_cpp):
    """Attach methods of a Python support class to an existing class

    This monkeypatches all methods defined in the support class onto an
    existing class. Example:

    .. code-block:: python

        @extends(ClassDefinedInCpp)
        class SupportClass:
            def foo(self):
                pass

    ClassDefinedInCpp.foo will now be defined.

    Subclassing is not used, because the intention is to extend a C++ class
    specification with Python methods, rather than creating a new class.

    Any existing methods may be used, regardless of whether they defined
    elsewhere in the support class or in the target class.

    The support class is not intended to be usable on its own. The support
    class may not define new attributes.
    """

    def real_class_extend(cls, cls_cpp=cls_cpp):
        for name, fn in inspect.getmembers(cls, inspect.isfunction):
            fn.__qualname__ = fn.__qualname__.replace(
                    cls.__name__, cls_cpp.__name__)
            setattr(cls_cpp, name, fn)
        return cls
    return real_class_extend


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
            ['mudraw', '-F', fmt, '-o', '-', tmp_in.name],
            stdout=PIPE, stderr=PIPE
        )
        if proc.stderr:
            raise RuntimeError(proc.stderr.decode())
        return proc.stdout


@extends(Object)
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


@extends(Pdf)
class Extend_Pdf:

    def _repr_mimebundle_(self, **kwargs):
        """
        Present options to IPython for rich display of this object

        See https://ipython.readthedocs.io/en/stable/config/integrating.html#rich-display
        """

        bio = BytesIO()
        self.save(bio)
        bio.seek(0)

        data = {'application/pdf': bio.read()}
        return data

    def attach(self, *, basename, filebytes, mime=None, desc=''):
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

        filespec = Dictionary({
            '/Type': Name.Filespec,
            '/F': basename,
            '/UF': basename,
            '/Desc': desc,
            '/EF': Dictionary({
                '/F': filestream
            })
        })

        # names = self.Root.Names.EmbeddedFiles.Names.as_list()
        # names.append(filename)  # Key
        # names.append(self.make_indirect(filespec))
        self.Root.Names.EmbeddedFiles.Names = Array([
            basename, # key
            self.make_indirect(filespec)
        ])

        if '/PageMode' not in self.Root:
            self.Root.PageMode = Name.UseAttachments

@extends(_ObjectMapping)
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
