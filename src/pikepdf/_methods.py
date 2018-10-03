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

from . import Pdf, Dictionary, Array, Name, Stream, Object


def bind(cls, name):
    """Install a Python method on a C++ class"""

    def real_bind(fn, cls=cls, name=name):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            return fn(*args, **kwargs)
        setattr(cls, name, fn)
        return wrapper
    return real_bind


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


@bind(Object, '_repr_mimebundle_')
def object_repr_mimebundle(obj, **kwargs):
    """Present options to IPython for rich display of this object

    See https://ipython.readthedocs.io/en/stable/config/integrating.html#rich-display
    """

    include = kwargs['include']
    exclude = kwargs['exclude']
    include = set() if include else include
    exclude = set() if exclude is None else exclude

    data = {}
    if '/Type' not in obj:
        return data

    if obj.Type == '/Page':
        bundle = {'application/pdf', 'image/png'}
        if include:
            bundle = bundle & include
        bundle = bundle - exclude
        pagedata = _single_page_pdf(obj)
        if 'application/pdf' in bundle:
            data['application/pdf'] = pagedata
        if 'image/png' in bundle:
            try:
                data['image/png'] = _mudraw(pagedata, 'png')
            except (FileNotFoundError, RuntimeError):
                pass

    return data


@bind(Pdf, '_repr_mimebundle_')
def pdf_repr_mimebundle(pdf, **kwargs):
    """
    Present options to IPython for rich display of this object

    See https://ipython.readthedocs.io/en/stable/config/integrating.html#rich-display
    """

    bio = BytesIO()
    pdf.save(bio)
    bio.seek(0)

    data = {'application/pdf': bio.read()}
    return data


@bind(Pdf, 'attach')
def pdf_attach(pdf, *, basename, filebytes, mime=None, desc=''):
    """
    Attach a file to this PDF

    Args:
        basename (str): The basename (filename withouth path) to name the file.
            Not necessarily the name of the file on disk. Will be shown to the
            user by the PDF viewer.
        filebytes (bytes): The file contents.

        mime (str or None): A MIME type for the filebytes. If omitted, we try
            to guess based on the standard library's
            :func:`mimetypes.guess_type`. If this cannot be determined, the
            generic value `application/octet-stream` is used. This value is
            used by PDF viewers to decide how to present the information to
            the user.

        desc (str): A extended description of the file contents. PDF viewers
            also display this information to the user. In Acrobat DC this is
            hidden in a context menu.

    The PDF will also be modified to request the PDF viewer to display the list
    of attachments when opened, as opposed to other viewing modes. Some PDF
    viewers will not make it obvious to the user that attachments are present
    unless this is done. This behavior may be overridden by changing
    ``pdf.Root.PageMode`` to some other valid value.

    """

    if '/Names' not in pdf.Root:
        pdf.Root.Names = pdf.make_indirect(Dictionary())
    if '/EmbeddedFiles' not in pdf.Root:
        pdf.Root.Names.EmbeddedFiles = pdf.make_indirect(Dictionary())
    if '/Names' not in pdf.Root.Names.EmbeddedFiles:
        pdf.Root.Names.EmbeddedFiles.Names = Array()

    if '/' in basename or '\\' in basename:
        raise ValueError("basename should be a basename (no / or \\)")

    if not mime:
        from mimetypes import guess_type
        mime, _encoding = guess_type(basename)
        if not mime:
            mime = 'application/octet-stream'

    filestream = Stream(pdf, filebytes)
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

    # names = pdf.Root.Names.EmbeddedFiles.Names.as_list()
    # names.append(filename)  # Key
    # names.append(pdf.make_indirect(filespec))
    pdf.Root.Names.EmbeddedFiles.Names = Array([
        basename, # key
        pdf.make_indirect(filespec)
    ])

    if '/PageMode' not in pdf.Root:
        pdf.Root.PageMode = Name.UseAttachments
