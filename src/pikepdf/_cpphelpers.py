# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
#
# Copyright (C) 2017, James R. Barlow (https://github.com/jbarlow83/)

"""
Support functions called by the C++ library binding layer. Not intended to be
called from Python, and subject to change at any time.
"""

import os
import sys
from tempfile import NamedTemporaryFile
from subprocess import run, PIPE
from io import BytesIO

from . import Pdf


# Provide os.fspath equivalent for Python <3.6
if sys.version_info[0:2] <= (3, 5):  # pragma: no cover
    def fspath(path):
        '''https://www.python.org/dev/peps/pep-0519/#os'''
        import pathlib
        if isinstance(path, (str, bytes)):
            return path

        # Work from the object's type to match method resolution of other magic
        # methods.
        path_type = type(path)
        try:
            path = path_type.__fspath__(path)
        except AttributeError:
            # Added for Python 3.5 support.
            if isinstance(path, pathlib.Path):
                return str(path)
            elif hasattr(path_type, '__fspath__'):
                raise
        else:
            if isinstance(path, (str, bytes)):
                return path
            else:
                raise TypeError("expected __fspath__() to return str or bytes, "
                                "not " + type(path).__name__)

        raise TypeError(
            "expected str, bytes, pathlib.Path or os.PathLike object, not "
            + path_type.__name__)

else:
    fspath = os.fspath


def _single_page_pdf(page):
    """
    Construct a single page PDF from the provided page in memory
    """
    pdf = Pdf.new()
    pdf.pages.append(page)
    bio = BytesIO()
    pdf.save(bio)
    bio.seek(0)
    return bio.read()


def _mudraw(buffer, fmt):
    """
    Use mupdf draw to rasterize the PDF in the memory buffer
    """
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


def object_repr_mimebundle(obj, **kwargs):
    """
    Present options to IPython for rich display of this object

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
