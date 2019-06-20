# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
#
# Copyright (C) 2017, James R. Barlow (https://github.com/jbarlow83/)

import collections
import types

from pikepdf import Object, ObjectType, PdfError
from .matrix import PdfMatrix
from .image import PdfImage, PdfInlineImage, UnsupportedImageTypeError
from .metadata import PdfMetadata


class Permissions(types.SimpleNamespace):
    """
    Stores the permissions for an encrypted PDF.

    Unencrypted PDFs implicitly have all permissions allowed.
    pikepdf does not enforce the restrictions in any way. Permissions
    can only be changed when a PDF is saved.
    """

    def __init__(
        self,
        accessibility=True,
        extract=True,
        modify_annotation=True,
        modify_assembly=False,
        modify_form=True,
        modify_other=True,
        print_lowres=True,
        print_highres=True,
    ):
        kvs = locals()
        del kvs['self']
        super().__init__(**kvs)

    def _readonly(self, *args):
        raise TypeError("object is read-only")

    __setattr__ = _readonly

    __delattr__ = _readonly

    def keys(self):
        yield from (k for k in self.__dict__ if not k.startswith('_'))

    def values(self):
        yield from (v for k, v in self.__dict__.items() if not k.startswith('_'))

    @classmethod
    def fields(cls):
        yield from (k for k in cls().__dict__ if not k.startswith('_'))


class EncryptionInfo:
    """
    Reports encryption information for an encrypted PDF.

    This information may not be changed, except when a PDF is saved.
    This object is not used to specify the encryption settings to save
    a PDF, due to non-overlapping information requirements.
    """

    def __init__(self, encdict):
        self._encdict = encdict

    @property
    def R(self):
        """Revision number of the security handler."""
        return self._encdict['R']

    @property
    def V(self):
        """Version of PDF password algorithm."""
        return self._encdict['V']

    @property
    def P(self):
        """Encoded permission bits.

        See :meth:`Pdf.allow` instead.
        """
        return self._encdict['P']

    @property
    def stream_method(self):
        """Encryption method used to encode streams."""
        return self._encdict['stream']

    @property
    def string_method(self):
        """Encryption method used to encode strings."""
        return self._encdict['string']

    @property
    def file_method(self):
        """Encryption method used to encode the whole file."""
        return self._encdict['file']

    @property
    def user_password(self):
        """If possible, return the user password.

        The user password can only be retrieved when a PDF is opened
        with the owner password and when older versions of the
        encryption algorithm are used.

        The password is always returned as ``bytes`` even if it has
        a clear Unicode representation.
        """
        return self._encdict['user_passwd']

    @property
    def encryption_key(self):
        """The RC4 or AES encryption key used for this file."""
        return self._encdict['encryption_key']

    @property
    def bits(self):
        """The number of encryption bits."""
        return len(self._encdict['encryption_key']) * 8


class Encryption(dict):
    """
    Specify the encryption settings to apply when a PDF is saved.

    Args:
        owner (str): The owner password to use. This allows full control
            of the file. If blank, the PDF will be encrypted and
            present as "(SECURED)" in PDF viewers. If the owner password
            is blank, the user password should be as well.
        user (str): The user password to use. With this password, some
            restrictions will be imposed by a typical PDF reader.
            If blank, the PDF can be opened by anyone, but only modified
            as allowed by the permissions in ``allow``.
        R (int): Select the security handler algorithm to use. Choose from:
            ``2``, ``3``, ``4`` or ``6``. By default, the highest version of
            is selected (``6``). ``5`` is a deprecated algorithm that should
            not be used.
        allow (pikepdf.Permissions): The permissions to set.
            If omitted, all permissions are granted to the user.
        aes (bool): If True, request the AES algorithm. If False, use RC4.
            If omitted, AES is selected whenever possible (R >= 4).
        metadata (bool): If True, also encrypt the PDF metadata. If False,
            metadata is not encrypted. Reading document metadata without
            decryption may be desirable in some cases. Requires ``aes=True``.
            If omitted, metadata is encrypted whenever possible.
    """

    def __init__(
        self, *, owner, user, R=6, allow=Permissions(), aes=True, metadata=True
    ):
        self.update(
            dict(R=R, owner=owner, user=user, allow=allow, aes=aes, metadata=metadata)
        )


def parse_content_stream(page_or_stream, operators=''):
    """
    Parse a PDF content stream into a sequence of instructions.

    A PDF content stream is list of instructions that describe where to render
    the text and graphics in a PDF. This is the starting point for analyzing
    PDFs.

    If the input is a page and page.Contents is an array, then the content
    stream is automatically treated as one coalesced stream.

    Each instruction contains at least one operator and zero or more operands.

    Args:
        page_or_stream (pikepdf.Object): A page object, or the content
            stream attached to another object such as a Form XObject.
        operators (str): A space-separated string of operators to whitelist.
            For example 'q Q cm Do' will return only operators
            that pertain to drawing images. Use 'BI ID EI' for inline images.
            All other operators and associated tokens are ignored. If blank,
            all tokens are accepted.

    Returns:
        list: List of ``(operands, command)`` tuples where ``command`` is an
            operator (str) and ``operands`` is a tuple of str; the PDF drawing
            command and the command's operands, respectively.

    Example:

        >>> pdf = pikepdf.Pdf.open(input_pdf)
        >>> page = pdf.pages[0]
        >>> for operands, command in parse_content_stream(page):
        >>>     print(command)

    """

    if not isinstance(page_or_stream, Object):
        raise TypeError("stream must a PDF object")

    if (
        page_or_stream._type_code != ObjectType.stream
        and page_or_stream.get('/Type') != '/Page'
    ):
        raise TypeError("parse_content_stream called on page or stream object")

    try:
        if page_or_stream.get('/Type') == '/Page':
            page = page_or_stream
            instructions = page._parse_page_contents_grouped(operators)
        else:
            stream = page_or_stream
            instructions = Object._parse_stream_grouped(stream, operators)
    except PdfError as e:
        # This is the error message for qpdf >= 7.0. It was different in 6.x
        # but we no longer support 6.x
        if 'ignoring non-stream while parsing' in str(e):
            raise TypeError("parse_content_stream called on non-stream Object")
        raise e from e

    return instructions


class _Page:
    def __init__(self, obj):
        self.obj = obj

    def __getattr__(self, item):
        return getattr(self.obj, item)

    def __setattr__(self, item, value):
        if item == 'obj':
            object.__setattr__(self, item, value)
        elif hasattr(self.obj, item):
            setattr(self.obj, item, value)
        else:
            raise AttributeError(item)

    def __repr__(self):
        return repr(self.obj).replace('pikepdf.Dictionary', 'pikepdf.Page', 1)

    @property
    def mediabox(self):
        return self.obj.MediaBox

    def has_text(self):
        """Check if this page print text

        Search the content stream for any of the four text showing operators.
        We ignore text positioning operators because some editors might
        generate maintain these even if text is deleted etc.

        This cannot detect raster text (text in a bitmap), text rendered as
        curves. It also cannot determine if the text is visible to the user.

        :return: True if there is text
        """
        text_showing_operators = """TJ " ' Tj"""
        text_showing_insts = parse_content_stream(self.obj, text_showing_operators)
        if len(text_showing_insts) > 0:
            return True
        return False
